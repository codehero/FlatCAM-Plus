# ##########################################################
# FlatCAM PLUS: 2D Post-processing for Manufacturing       #
# File Updated By Sadri ERCAN - 2026                        #
# File Author: Sadri ERCAN                                 #
# Date:     05/01/2026                                     #
# License:  FlatCAM Plus CNC Control Module Non-Commercial License         #
# See:      appPlugins/cnc_control/LICENSE                  #
# ##########################################################

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, pyqtSignal

from appTool import AppTool
from appGUI.GUIElements import VerticalScrollArea
from appPlugins.cnc_control.dialogs import MachineProfileDialog, MacroDialog
from appPlugins.cnc_control.machine_profiles import normalize_machine_profile, normalize_machine_profiles
from appPlugins.cnc_control.profiles import CNC_PROFILES
from appPlugins.cnc_control.transports import HttpTransport, SerialTransport, TcpTransport
from appPlugins.cnc_control.ui import CNCControlUI

import builtins
import gettext
import logging
import math
import re
import threading
import time

import serial.tools.list_ports

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class ToolCNCControl(AppTool):
    update_status_sig = pyqtSignal(dict)
    append_console_sig = pyqtSignal(str, str)
    update_progress_sig = pyqtSignal(float, str)
    connection_state_sig = pyqtSignal(bool, str)
    files_update_sig = pyqtSignal(dict)
    sd_file_sig = pyqtSignal(str)
    clear_sd_files_sig = pyqtSignal()
    controller_info_sig = pyqtSignal(dict)
    busy_sig = pyqtSignal(bool, str)
    test_connection_sig = pyqtSignal(bool, str)
    queue_update_sig = pyqtSignal()
    preview_update_sig = pyqtSignal(dict)
    auto_level_update_sig = pyqtSignal(dict)

    def __init__(self, app):
        self.app = app
        AppTool.__init__(self, app)

        self.transport = None
        self.is_connected = False
        self.stop_thread = threading.Event()
        self.macros = []
        self.machine_profiles = []
        self.active_machine_profile_name = ""
        self.load_macros()
        self.load_machine_profiles()
        self.receiver_thread = None
        self.io_lock = threading.RLock()
        self.ok_received = threading.Event()
        self.last_controller_ack = ""
        self.last_status_query = 0
        self.status_interval = 0.25
        self.tcp_status_interval = 0.5
        self.http_status_interval = 1.0
        self.sd_collecting = False
        self.active_profile_key = "fluidnc"
        self.status_poll_enabled = True
        self.hide_status_reports = True
        self.active_limit_pins = ""

        self.is_streaming = False
        self.streaming_paused = False
        self.current_line_idx = 0
        self.gcode_lines = []
        self.job_queue = []
        self.current_queue_idx = -1
        self.is_auto_leveling = False
        self.auto_level_cancel = threading.Event()
        self.probe_result_event = threading.Event()
        self.last_probe_result = None
        self.auto_level_map = None
        self.work_offsets = {}
        self.g92_offset = [0.0, 0.0, 0.0]
        self.tool_length_offset = [0.0, 0.0, 0.0]
        self.last_wco = None
        self.probe_coordinate_mode = None

        self.ui = CNCControlUI(layout=self.layout, app=self.app)
        self.pluginName = self.ui.pluginName
        self.active_profile_key = self.ui.profile_combo.currentData() or "fluidnc"
        self.load_macros()
        self.load_machine_profiles()
        self.connect_signals_at_init()
        self.ui.set_connected(False)
        self.register_toolbar_connection_handler()
        self.update_toolbar_connection_status(False, "")

    def run(self, toggle=True):
        tab_exists = False
        for i in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(i) in [_("CNC Control"), _("CNC Settings")]:
                self.app.ui.plot_tab_area.setCurrentIndex(i)
                tab_exists = True
                break

        if not tab_exists:
            self.scroll_area = VerticalScrollArea()
            self.scroll_area.setWidget(self)
            self.scroll_area.setWidgetResizable(True)
            self.app.ui.plot_tab_area.addTab(self.scroll_area, _("CNC Control"))
            self.app.ui.plot_tab_area.setCurrentIndex(self.app.ui.plot_tab_area.count() - 1)

        self.on_refresh_ports()
        self.update_tool_list()
        self.load_macros()
        self.load_machine_profiles()

    def connect_signals_at_init(self):
        self.ui.connect_btn.clicked.connect(self.on_connect_clicked)
        self.ui.test_connection_btn.clicked.connect(self.on_test_connection_clicked)
        self.ui.disconnect_btn.clicked.connect(self.disconnect)
        self.ui.com_refresh.clicked.connect(self.on_refresh_ports)
        self.ui.connection_mode_combo.currentIndexChanged.connect(self.ui.on_connection_mode_changed)
        self.ui.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        self.ui.poll_status_cb.toggled.connect(self.on_poll_status_changed)
        self.ui.hide_status_reports_cb.toggled.connect(self.on_hide_status_reports_changed)

        self.ui.home_btn.clicked.connect(self.on_home_clicked)
        self.ui.unlock_btn.clicked.connect(lambda: self.send_profile_command("unlock"))
        self.ui.reset_btn.clicked.connect(lambda: self.send_profile_command("reset"))
        self.ui.estop_btn.clicked.connect(lambda: self.send_profile_command("hold"))
        self.ui.resume_btn.clicked.connect(lambda: self.send_profile_command("resume"))
        self.ui.info_btn.clicked.connect(self.on_info_clicked)
        self.ui.cfg_dump.clicked.connect(lambda: self.send_profile_command("config"))

        self.ui.zero_x.clicked.connect(lambda: self.send_zero("X"))
        self.ui.zero_y.clicked.connect(lambda: self.send_zero("Y"))
        self.ui.zero_z.clicked.connect(lambda: self.send_zero("Z"))
        self.ui.zero_all.clicked.connect(self.on_zero_all_clicked)

        self.ui.feed_plus.clicked.connect(lambda: self.send_profile_command("feed_plus"))
        self.ui.feed_minus.clicked.connect(lambda: self.send_profile_command("feed_minus"))
        self.ui.feed_reset.clicked.connect(lambda: self.send_profile_command("feed_reset"))
        self.ui.feed_set_btn.clicked.connect(lambda: self.on_set_override("feed_set", self.ui.feed_override_entry))
        self.ui.spindle_plus.clicked.connect(lambda: self.send_profile_command("spindle_plus"))
        self.ui.spindle_minus.clicked.connect(lambda: self.send_profile_command("spindle_minus"))
        self.ui.spindle_reset.clicked.connect(lambda: self.send_profile_command("spindle_reset"))
        self.ui.spindle_override_set_btn.clicked.connect(
            lambda: self.on_set_override("spindle_override_set", self.ui.spindle_override_entry)
        )
        self.ui.spindle_set_btn.clicked.connect(self.on_set_spindle_rpm)
        self.ui.spindle_stop_btn.clicked.connect(lambda: self.send_profile_command("spindle_stop"))

        self.ui.macro_laser.clicked.connect(self.on_toggle_laser)
        self.ui.set_xy_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("X", "Y")))
        self.ui.set_z_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("Z",)))
        self.ui.set_xyz_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("X", "Y", "Z")))

        self.ui.jog_up.clicked.connect(lambda: self.send_jog("Y", 1))
        self.ui.jog_down.clicked.connect(lambda: self.send_jog("Y", -1))
        self.ui.jog_left.clicked.connect(lambda: self.send_jog("X", -1))
        self.ui.jog_right.clicked.connect(lambda: self.send_jog("X", 1))
        self.ui.jog_z_up.clicked.connect(lambda: self.send_jog("Z", 1))
        self.ui.jog_z_down.clicked.connect(lambda: self.send_jog("Z", -1))

        self.ui.sd_list_btn.clicked.connect(self.on_sd_list)
        self.ui.run_sd_btn.clicked.connect(self.on_run_sd)
        self.ui.refresh_jobs_btn.clicked.connect(self.update_tool_list)
        self.ui.queue_add_btn.clicked.connect(self.on_queue_add)
        self.ui.queue_remove_btn.clicked.connect(self.on_queue_remove)
        self.ui.queue_up_btn.clicked.connect(lambda: self.on_queue_move(-1))
        self.ui.queue_down_btn.clicked.connect(lambda: self.on_queue_move(1))
        self.ui.preview_refresh_btn.clicked.connect(self.on_preview_clicked)
        self.ui.preview_verify_btn.clicked.connect(self.on_verify_clicked)
        self.ui.object_combo.currentIndexChanged.connect(
            lambda *_args: self.on_preview_refresh(refresh_jobs=False)
        )
        self.ui.job_origin_combo.currentIndexChanged.connect(
            lambda *_args: self.on_preview_refresh(refresh_jobs=False)
        )
        self.ui.job_placement_combo.currentIndexChanged.connect(
            lambda *_args: self.on_preview_refresh(refresh_jobs=False)
        )
        self.ui.job_size_x.valueChanged.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        self.ui.job_size_y.valueChanged.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        self.ui.job_margin_x.valueChanged.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        self.ui.job_margin_y.valueChanged.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        self.ui.fit_job_size_btn.clicked.connect(self.on_fit_job_size_clicked)
        self.ui.autolevel_fit_btn.clicked.connect(self.on_auto_level_fit_area)
        self.ui.autolevel_probe_btn.clicked.connect(self.on_auto_level_probe_clicked)
        self.ui.autolevel_stop_btn.clicked.connect(self.on_auto_level_stop)
        self.ui.autolevel_clear_btn.clicked.connect(self.on_auto_level_clear)
        self.ui.autolevel_3d_btn.clicked.connect(self.on_auto_level_3d_clicked)
        self.ui.autolevel_enable_cb.toggled.connect(
            lambda *_args: self.on_preview_refresh(refresh_jobs=False)
        )
        self.ui.queue_table.itemSelectionChanged.connect(
            lambda: self.on_preview_refresh(refresh_jobs=False)
        )

        self.ui.command_entry.returnPressed.connect(self.on_send_command)
        self.ui.play_btn.clicked.connect(self.on_stream_start)
        self.ui.pause_btn.clicked.connect(self.on_stream_pause)
        self.ui.stop_btn.clicked.connect(self.on_stream_stop)

        self.ui.files_refresh_btn.clicked.connect(self.on_refresh_files)
        self.ui.files_upload_btn.clicked.connect(self.on_upload_files)
        self.ui.files_mkdir_btn.clicked.connect(self.on_create_dir)
        self.ui.files_delete_btn.clicked.connect(self.on_delete_file)
        self.ui.files_up_btn.clicked.connect(self.on_files_up)
        self.ui.files_root_btn.clicked.connect(self.on_files_root)
        self.ui.files_fs_combo.currentIndexChanged.connect(self.on_filesystem_changed)
        self.ui.files_table.itemDoubleClicked.connect(self.on_file_double_clicked)

        self.ui.files_dialog_btn.clicked.connect(self.on_open_files_dialog)
        self.ui.manage_macros_btn.clicked.connect(self.on_manage_macros)
        self.ui.machine_profile_combo.currentIndexChanged.connect(self.on_machine_profile_changed)
        self.ui.manage_machine_profiles_btn.clicked.connect(self.on_manage_machine_profiles)

        self.update_status_sig.connect(self.update_status_display)
        self.append_console_sig.connect(self.ui.append_console)
        self.update_progress_sig.connect(self.update_progress_ui)
        self.connection_state_sig.connect(self.on_connection_state_changed)
        self.files_update_sig.connect(self.ui.update_files_table)
        self.sd_file_sig.connect(self.ui.add_sd_file)
        self.clear_sd_files_sig.connect(self.ui.clear_sd_files)
        self.controller_info_sig.connect(self.ui.update_controller_info)
        self.busy_sig.connect(self.ui.set_busy)
        self.test_connection_sig.connect(self.on_test_connection_finished)
        self.queue_update_sig.connect(self.update_queue_table)
        self.preview_update_sig.connect(self.update_preview_ui)
        self.auto_level_update_sig.connect(self.update_auto_level_ui)

    def update_tool_list(self, *_args, preserve_selection=True, refresh_preview=True):
        current_name = self.ui.object_combo.currentText().strip() if preserve_selection else ""
        cncjob_count = 0
        self.ui.object_combo.blockSignals(True)
        try:
            self.ui.object_combo.clear()
            for obj in self.app.collection.get_list():
                if getattr(obj, "kind", None) == "cncjob":
                    name = obj.obj_options.get("name", "")
                    if name:
                        self.ui.object_combo.addItem(name)
                        cncjob_count += 1

            if current_name:
                idx = self.ui.object_combo.findText(current_name)
                if idx >= 0:
                    self.ui.object_combo.setCurrentIndex(idx)
        finally:
            self.ui.object_combo.blockSignals(False)

        if refresh_preview and hasattr(self.ui, "gcode_preview_text"):
            self.on_preview_refresh(refresh_jobs=False)

        return cncjob_count

    @staticmethod
    def gcode_text_from_source(source):
        if source is None:
            return ""
        if hasattr(source, "getvalue"):
            source = source.getvalue()
        if isinstance(source, (list, tuple)):
            return "\n".join(str(line) for line in source)
        return str(source)

    def cncjob_gcode_text(self, obj):
        source = self.gcode_text_from_source(getattr(obj, "source_file", ""))
        if source.strip():
            return source

        exporter = getattr(obj, "export_gcode", None)
        if callable(exporter):
            try:
                exported = exporter(
                    preamble=getattr(obj, "prepend_snippet", ""),
                    postamble=getattr(obj, "append_snippet", ""),
                    to_file=True,
                    s_code=getattr(obj, "gc_start", "")
                )
                source = self.gcode_text_from_source(exported)
                if source.strip():
                    obj.source_file = source
                    return source
            except Exception as err:
                log.warning("CNC preview export fallback failed for %s: %s", getattr(obj, "obj_options", {}), err)

        source = self.gcode_text_from_source(getattr(obj, "gcode", ""))
        if source.strip():
            return source

        chunks = []
        for value in getattr(obj, "tools", {}).values():
            if isinstance(value, dict):
                tool_gcode = self.gcode_text_from_source(value.get("gcode", ""))
                if tool_gcode.strip():
                    chunks.append(tool_gcode)

        prefix = "\n".join(
            text for text in [
                self.gcode_text_from_source(getattr(obj, "gc_header", "")),
                self.gcode_text_from_source(getattr(obj, "gc_start", ""))
            ] if text.strip()
        )
        if prefix:
            chunks.insert(0, prefix)

        return "\n".join(chunks)

    def cncjob_lines(self, name):
        obj = self.app.collection.get_by_name(name)
        if not obj:
            return []

        source = self.cncjob_gcode_text(obj)
        return [line.strip() for line in source.splitlines() if line.strip()]

    def on_queue_add(self):
        name = self.ui.object_combo.currentText().strip()
        if not name:
            self.append_console_sig.emit(_("No CNCJob object selected."), "error")
            return

        lines = self.cncjob_lines(name)
        if not lines:
            self.append_console_sig.emit(_("Selected CNCJob has no G-code."), "error")
            return

        self.job_queue.append({
            "name": name,
            "lines": lines,
            "status": _("Queued")
        })
        self.update_queue_table(select_row=len(self.job_queue) - 1)

    def refresh_queued_gcode(self):
        for item in self.job_queue:
            name = str(item.get("name", "")).strip()
            lines = self.cncjob_lines(name)
            if not lines:
                self.append_console_sig.emit(
                    _("Queued CNCJob is missing or has no G-code: %s") % name,
                    "error"
                )
                return False
            item["lines"] = lines
        return True

    def selected_queue_row(self):
        if not hasattr(self.ui, "queue_table"):
            return -1
        rows = sorted({index.row() for index in self.ui.queue_table.selectedIndexes()})
        return rows[0] if rows else -1

    def on_queue_remove(self):
        row = self.selected_queue_row()
        if row < 0 or row >= len(self.job_queue) or self.is_streaming:
            return
        self.job_queue.pop(row)
        self.update_queue_table(select_row=min(row, len(self.job_queue) - 1))

    def on_queue_move(self, direction):
        row = self.selected_queue_row()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self.job_queue) or self.is_streaming:
            return
        self.job_queue[row], self.job_queue[new_row] = self.job_queue[new_row], self.job_queue[row]
        self.update_queue_table(select_row=new_row)

    def update_queue_table(self, select_row=None):
        if not hasattr(self.ui, "queue_table"):
            return

        previous_row = self.selected_queue_row() if select_row is None else select_row
        table = self.ui.queue_table
        table.setRowCount(len(self.job_queue))
        for row, item in enumerate(self.job_queue):
            values = [
                str(row + 1),
                item.get("name", ""),
                str(len(item.get("lines", []))),
                item.get("status", _("Queued")),
            ]
            for column, value in enumerate(values):
                table_item = QtWidgets.QTableWidgetItem(value)
                table_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row, column, table_item)
        table.resizeRowsToContents()
        if 0 <= previous_row < len(self.job_queue):
            table.selectRow(previous_row)
        self.on_preview_refresh()

    def selected_preview_job(self):
        row = self.selected_queue_row()
        if 0 <= row < len(self.job_queue):
            item = self.job_queue[row]
            name = item.get("name", _("Queued Job"))
            fresh_lines = self.cncjob_lines(name)
            if fresh_lines:
                item["lines"] = fresh_lines
                return name, fresh_lines
            return name, list(item.get("lines", []))

        name = self.ui.object_combo.currentText().strip()
        if not name:
            return "", []
        return name, self.cncjob_lines(name)

    def on_preview_clicked(self, *_args):
        self.on_preview_refresh(refresh_jobs=True, action=_("Preview"), announce=True)

    def on_verify_clicked(self, *_args):
        self.on_preview_refresh(refresh_jobs=True, action=_("Verify"), announce=True)

    def emit_preview_message(self, message, level="info"):
        self.append_console_sig.emit(message, level)
        try:
            if level == "error":
                self.app.inform.emit("[ERROR_NOTCL] %s" % message)
            elif level == "warn":
                self.app.inform.emit("[WARNING_NOTCL] %s" % message)
            else:
                self.app.inform.emit("[success] %s" % message)
        except Exception:
            pass

    def on_preview_refresh(self, *_args, refresh_jobs=True, action=None, announce=False):
        if not hasattr(self.ui, "gcode_preview_text"):
            return

        action = action or _("Preview")
        job_count = self.ui.object_combo.count()
        if refresh_jobs:
            job_count = self.update_tool_list(refresh_preview=False)

        name, lines = self.selected_preview_job()
        preview_lines = self.transformed_gcode_lines(lines)
        canvas_preview = self.build_job_canvas_preview(name, lines, preview_lines)
        try:
            result = self.analyze_gcode(name, preview_lines)
        except Exception as err:
            log.exception("G-code preview failed")
            result = {
                "name": name or _("No CNCJob selected"),
                "line_count": 0,
                "motion_count": 0,
                "cutting_count": 0,
                "distance": 0.0,
                "bounds": "-",
                "estimated_minutes": 0.0,
                "warnings": [("ERROR", "-", "%s: %s" % (_("Preview failed"), err))],
                "preview": "%s: %s" % (_("Preview failed"), err),
                "canvas": canvas_preview,
                "action": action,
                "updated_at": time.strftime("%H:%M:%S"),
            }
            self.preview_update_sig.emit(result)
            if announce:
                self.emit_preview_message(result["preview"], "error")
            return

        result["action"] = action
        result["updated_at"] = time.strftime("%H:%M:%S")
        result["canvas"] = canvas_preview
        if lines and preview_lines != lines:
            result["name"] = "%s (%s)" % (result["name"], _("mapped to zeroed XY"))
        self.preview_update_sig.emit(result)

        if not announce:
            return

        if job_count == 0:
            self.emit_preview_message(_("No CNCJob object found."), "warn")
        elif not name:
            self.emit_preview_message(_("No CNCJob object selected."), "warn")
        elif result.get("line_count", 0) == 0:
            self.emit_preview_message(_("Selected CNCJob has no G-code."), "warn")
        else:
            self.emit_preview_message(
                "%s: %s (%d %s, %d %s)" % (
                    action,
                    name,
                    result.get("line_count", 0),
                    _("lines"),
                    len(result.get("warnings", [])),
                    _("warnings")
                ),
                "info"
            )

    @staticmethod
    def clean_gcode_line(line):
        line = re.sub(r"\([^)]*\)", "", line or "")
        line = line.split(";", 1)[0]
        return line.strip()

    @staticmethod
    def gcode_words(line):
        return {
            key.upper(): float(value)
            for key, value in re.findall(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line)
        }

    def analyze_gcode(self, name, lines):
        warnings = []
        preview_limit = 500
        clean_lines = []
        position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        bounds = {axis: [None, None] for axis in "XYZ"}
        bounds_lines = {axis: [None, None] for axis in "XYZ"}
        absolute = True
        units = None
        has_position_mode = False
        spindle_on = False
        feed = None
        motion_count = 0
        cutting_count = 0
        distance = 0.0
        estimated_minutes = 0.0
        current_motion = None
        rapid_below_surface = False
        cut_without_spindle = False
        cut_without_feed = False
        uses_incremental = False
        pauses = []

        for index, raw_line in enumerate(lines, start=1):
            clean_line = self.clean_gcode_line(raw_line)
            if not clean_line:
                continue

            clean_lines.append((index, raw_line.rstrip()))
            upper_line = clean_line.upper()
            words = self.gcode_words(upper_line)
            g_codes = [int(float(value)) for value in re.findall(
                r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", upper_line
            )]
            m_codes = [int(float(value)) for value in re.findall(
                r"\bM\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", upper_line
            )]

            if 20 in g_codes:
                units = "inch"
            if 21 in g_codes:
                units = "mm"
            if 90 in g_codes:
                absolute = True
                has_position_mode = True
            if 91 in g_codes:
                absolute = False
                has_position_mode = True
                uses_incremental = True
            if 3 in m_codes or 4 in m_codes:
                spindle_on = True
            if 5 in m_codes:
                spindle_on = False
            if 0 in m_codes or 1 in m_codes:
                pauses.append(index)
            if "F" in words and words["F"] > 0:
                feed = words["F"]

            motion = None
            for g_code in g_codes:
                if g_code in [0, 1, 2, 3]:
                    motion = g_code
                    current_motion = g_code
            if motion is None:
                motion = current_motion

            if motion is None:
                continue

            next_position = dict(position)
            has_axis = False
            for axis in "XYZ":
                if axis in words:
                    has_axis = True
                    next_position[axis] = position[axis] + words[axis] if not absolute else words[axis]
            if not has_axis:
                continue

            segment = sum((next_position[axis] - position[axis]) ** 2 for axis in "XYZ") ** 0.5
            distance += segment
            motion_count += 1
            for axis in "XYZ":
                val = next_position[axis]
                if bounds[axis][0] is None or val < bounds[axis][0]:
                    bounds[axis][0] = val
                    bounds_lines[axis][0] = index
                if bounds[axis][1] is None or val > bounds[axis][1]:
                    bounds[axis][1] = val
                    bounds_lines[axis][1] = index

            if motion == 0 and next_position["Z"] < 0 and (next_position["X"] != position["X"] or
                                                            next_position["Y"] != position["Y"]):
                rapid_below_surface = True

            if motion in [1, 2, 3] and next_position["Z"] < 0:
                cutting_count += 1
                if not spindle_on:
                    cut_without_spindle = True
                if not feed:
                    cut_without_feed = True
                if feed and feed > 0:
                    estimated_minutes += segment / feed

            position = next_position

        if not clean_lines:
            warnings.append(("ERROR", "-", _("No G-code lines found.")))
        if units is None:
            warnings.append(("WARN", "-", _("No G20/G21 units command found.")))
        if not has_position_mode:
            warnings.append(("WARN", "-", _("No G90/G91 positioning mode found.")))
        if uses_incremental:
            warnings.append(("INFO", "-", _("Program uses incremental mode G91.")))
        if cut_without_spindle:
            warnings.append(("WARN", "-", _("Cutting moves detected before spindle start M3/M4.")))
        if cut_without_feed:
            warnings.append(("WARN", "-", _("Cutting moves detected before a feedrate command.")))
        if rapid_below_surface:
            warnings.append(("WARN", "-", _("Rapid XY motion detected while Z is below zero.")))
        if pauses:
            warnings.append(("INFO", ",".join(str(line) for line in pauses[:8]), _("Program contains pause commands.")))

        profile = self.current_machine_profile()
        units_for_limits = units
        if units_for_limits is None:
            units_for_limits = "inch" if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else "mm"
        to_mm_factor = 25.4 if units_for_limits == "inch" else 1.0
        tolerance_mm = 0.001

        def add_limit_warning(axis, bound_index, message):
            line_no = bounds_lines[axis][bound_index]
            warnings.append(("WARN", str(line_no) if line_no is not None else "-", message))

        def axis_bound_mm(axis, bound_index):
            value = bounds[axis][bound_index]
            return None if value is None else value * to_mm_factor

        for axis in "XY":
            travel_limit = float(profile.get("travel_%s" % axis.lower(), 0) or 0)
            if travel_limit <= 0:
                continue

            axis_min = axis_bound_mm(axis, 0)
            axis_max = axis_bound_mm(axis, 1)
            if axis_min is not None and axis_min < -tolerance_mm:
                add_limit_warning(
                    axis, 0,
                    _("%s minimum is below the active machine profile origin.") % axis
                )
            if axis_max is not None and axis_max > travel_limit + tolerance_mm:
                add_limit_warning(
                    axis, 1,
                    _("%s maximum exceeds the active machine profile travel limit.") % axis
                )

        travel_z = float(profile.get("travel_z", 0) or 0)
        if travel_z > 0:
            z_min = axis_bound_mm("Z", 0)
            z_max = axis_bound_mm("Z", 1)
            if z_min is not None and abs(z_min) > travel_z + tolerance_mm:
                add_limit_warning("Z", 0, _("Minimum Z exceeds the active machine profile travel limit."))
            if z_max is not None and abs(z_max) > travel_z + tolerance_mm:
                add_limit_warning("Z", 1, _("Maximum Z exceeds the active machine profile travel limit."))

        preview = "\n".join(
            f"{line_no:>5}: {text}" for line_no, text in clean_lines[:preview_limit]
        )
        if not preview:
            preview = _("No CNCJob object selected.") if not name else _("Selected CNCJob has no G-code to preview.")
        if len(clean_lines) > preview_limit:
            preview += f"\n... {_('preview truncated')} ({len(clean_lines) - preview_limit} {_('more lines')})"

        def bounds_text(axis):
            lo, hi = bounds[axis]
            if lo is None or hi is None:
                return f"{axis}-"
            return f"{axis}{lo:.3f}..{hi:.3f}"

        return {
            "name": name or _("No CNCJob selected"),
            "line_count": len(clean_lines),
            "motion_count": motion_count,
            "cutting_count": cutting_count,
            "distance": distance,
            "bounds": "  ".join(bounds_text(axis) for axis in "XYZ"),
            "estimated_minutes": estimated_minutes,
            "warnings": warnings,
            "preview": preview,
        }

    def update_preview_ui(self, result):
        if not hasattr(self.ui, "gcode_preview_text"):
            return

        warnings = result.get("warnings", [])
        source_name = result.get("name", _("No CNCJob selected"))
        action = result.get("action", "")
        updated_at = result.get("updated_at", "")
        if action and updated_at:
            source_name = "%s: %s @ %s" % (action, source_name, updated_at)
        self.ui.preview_source_label.setText(source_name)
        self.ui.preview_lines_value.setText(str(result.get("line_count", 0)))
        self.ui.preview_motion_value.setText(
            "%s / %s" % (result.get("motion_count", 0), result.get("cutting_count", 0))
        )
        self.ui.preview_distance_value.setText("%.2f mm" % result.get("distance", 0.0))
        self.ui.preview_bounds_value.setText(result.get("bounds", "-"))
        self.ui.preview_time_value.setText("%.1f min" % result.get("estimated_minutes", 0.0))
        self.ui.preview_warnings_value.setText(str(len(warnings)))
        self.ui.gcode_preview_text.setPlainText(result.get("preview", ""))
        if hasattr(self.ui, "gcode_job_canvas"):
            self.ui.gcode_job_canvas.set_preview(result.get("canvas", {}))

        table = self.ui.gcode_warning_table
        table.setRowCount(len(warnings))
        for row, (level, line, message) in enumerate(warnings):
            for column, value in enumerate([level, line, message]):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row, column, item)
        table.resizeRowsToContents()

    def on_refresh_ports(self):
        self.ui.com_port.clear()
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            description = port.description if port.description else port.device
            self.ui.com_port.addItem(f"{port.device} - {description}", port.device)
        if self.ui.com_port.count() == 0:
            self.ui.com_port.addItem("None", "None")

    def current_profile(self):
        return CNC_PROFILES.get(self.active_profile_key, CNC_PROFILES["fluidnc"])

    def current_profile_key(self):
        return self.active_profile_key

    def update_toolbar_connection_status(self, connected=False, description="", state=None):
        updater = getattr(getattr(self.app, "ui", None), "update_cnc_toolbar_status", None)
        if callable(updater):
            updater(connected, description or "", state=state)

    def register_toolbar_connection_handler(self):
        setter = getattr(getattr(self.app, "ui", None), "set_cnc_toolbar_connection_handler", None)
        if callable(setter):
            setter(self.on_toolbar_connection_clicked)

    def on_toolbar_connection_clicked(self, *_args):
        self.on_refresh_ports()
        self.ui.show_connection_dialog(self.is_connected)

    def on_open_files_dialog(self):
        self.ui.show_file_system_dialog()
        if self.is_connected:
            self.on_refresh_files()

    def on_profile_changed(self):
        self.active_profile_key = self.ui.profile_combo.currentData() or "fluidnc"

    def current_machine_profile(self):
        for profile in self.machine_profiles:
            if profile["name"] == self.active_machine_profile_name:
                return profile
        if self.machine_profiles:
            return self.machine_profiles[0]
        return normalize_machine_profile({})

    def load_machine_profiles(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        import json

        profiles = []
        if settings.contains("cnc_machine_profiles"):
            try:
                profiles = json.loads(settings.value("cnc_machine_profiles"))
            except Exception:
                profiles = []

        self.machine_profiles = normalize_machine_profiles(profiles)
        stored_active = settings.value("cnc_active_machine_profile", "")
        names = {profile["name"] for profile in self.machine_profiles}
        self.active_machine_profile_name = stored_active if stored_active in names else self.machine_profiles[0]["name"]

        if hasattr(self, "ui") and self.ui and hasattr(self.ui, "update_machine_profiles"):
            self.ui.update_machine_profiles(self.machine_profiles, self.active_machine_profile_name)
            self.apply_machine_profile()

    def save_machine_profiles_to_storage(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        import json
        settings.setValue("cnc_machine_profiles", json.dumps(self.machine_profiles))
        settings.setValue("cnc_active_machine_profile", self.active_machine_profile_name)

    def apply_machine_profile(self):
        if not hasattr(self, "ui") or not self.ui:
            return

        profile = self.current_machine_profile()
        if hasattr(self.ui, "jog_feed"):
            self.ui.jog_feed.setValue(profile["jog_feed"])
        if hasattr(self.ui, "probe_feed"):
            self.ui.probe_feed.setValue(profile["probe_feed"])
        if hasattr(self.ui, "autolevel_probe_feed"):
            self.ui.autolevel_probe_feed.setValue(profile["probe_feed"])
        if hasattr(self.ui, "autolevel_safe_z"):
            self.ui.autolevel_safe_z.set_value(profile["safe_z"])
        if hasattr(self.ui, "spindle_rpm"):
            current_rpm = int(self.ui.spindle_rpm.value())
            max_rpm = profile["spindle_max"]
            self.ui.spindle_rpm.set_range(0, max(1, max_rpm))
            if max_rpm <= 0:
                self.ui.spindle_rpm.setValue(0)
            elif current_rpm > max_rpm:
                self.ui.spindle_rpm.setValue(max_rpm)
        if hasattr(self.ui, "update_machine_profile_summary"):
            self.ui.update_machine_profile_summary(profile)

    def on_machine_profile_changed(self, _index=None):
        if not hasattr(self.ui, "machine_profile_combo"):
            return
        selected = self.ui.machine_profile_combo.currentData()
        if not selected:
            return
        self.active_machine_profile_name = selected
        self.save_machine_profiles_to_storage()
        self.apply_machine_profile()

    def on_manage_machine_profiles(self, *_args):
        dialog = MachineProfileDialog(self.machine_profiles, self.active_machine_profile_name, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.machine_profiles = normalize_machine_profiles(dialog.profiles)
            self.active_machine_profile_name = dialog.active_name
            names = {profile["name"] for profile in self.machine_profiles}
            if self.active_machine_profile_name not in names:
                self.active_machine_profile_name = self.machine_profiles[0]["name"]
            self.save_machine_profiles_to_storage()
            self.ui.update_machine_profiles(self.machine_profiles, self.active_machine_profile_name)
            self.apply_machine_profile()

    def on_poll_status_changed(self, enabled):
        self.status_poll_enabled = bool(enabled)

    def on_hide_status_reports_changed(self, enabled):
        self.hide_status_reports = bool(enabled)

    def on_connect_clicked(self):
        if self.is_connected:
            self.disconnect()
            return

        config = self.ui.connection_config()
        message = self.validate_connection_config(config)
        if message:
            self.append_console_sig.emit(message, "error")
            return

        self.ui.set_connection_actions_enabled(False)
        self.append_console_sig.emit(_("Connecting..."), "info")
        threading.Thread(target=self._connect_worker, args=(config,), daemon=True).start()

    def validate_connection_config(self, config):
        if config["mode"] == "serial" and config["port"] == "None":
            return _("No COM port selected.")
        if config["mode"] == "tcp" and not config["host"]:
            return _("No host selected.")
        if config["mode"] == "http" and not config["web_url"]:
            return _("No URL selected.")
        return ""

    def build_transport(self, config):
        if config["mode"] == "serial":
            return SerialTransport(config["port"], config["baudrate"])
        if config["mode"] == "tcp":
            return TcpTransport(config["host"], config["tcp_port"])
        return HttpTransport(config["web_url"], config["user"], config["password"])

    def _connect_worker(self, config):
        try:
            transport = self.build_transport(config)
            transport.open()
            with self.io_lock:
                self.transport = transport
                self.is_connected = True
                self.stop_thread.clear()

            self.connection_state_sig.emit(True, transport.description())
            self.receiver_thread = threading.Thread(target=self.receive_loop, daemon=True)
            self.receiver_thread.start()

            if isinstance(transport, HttpTransport) and transport.info_text:
                self.parse_controller_info(transport.info_text)
            else:
                self.send_profile_command("info", log=False)
        except Exception as e:
            log.error("CNC connection error: %s", e)
            self.append_console_sig.emit(f"{_('Connection failed')}: {e}", "error")
            self.connection_state_sig.emit(False, "")

    def on_connection_state_changed(self, connected, description):
        self.ui.set_connection_actions_enabled(True)
        self.ui.set_connected(connected)
        self.update_toolbar_connection_status(connected, description)
        if connected:
            self.append_console_sig.emit(f"{_('Connected')}: {description}", "info")
            self.ui.connection_desc.setText(description)
            self.on_refresh_files()
        else:
            self.ui.connection_desc.setText(_("Offline"))
            self.append_console_sig.emit(_("Disconnected"), "info")
        self.ui.sync_connection_dialog(connected)

    # ##########################################################
    # ##################### MACRO SYSTEM #######################
    # ##########################################################

    def load_macros(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        if settings.contains("cnc_macros"):
            import json
            try:
                self.macros = json.loads(settings.value("cnc_macros"))
            except Exception:
                self.macros = []
        else:
            self.macros = [
                {"name": "Home & Zero", "content": "G28\nG10 L20 P1 X0 Y0 Z0"},
                {"name": "Probe Z", "content": "G38.2 Z-50 F100\nG92 Z0"}
            ]

        # Only update an inline macro list if a future CNC subplugin provides one.
        if hasattr(self, 'ui') and self.ui and hasattr(self.ui, "macro_list"):
            self.ui.macro_list.clear()
            for macro in self.macros:
                self.ui.macro_list.addItem(macro["name"])

    def save_macros_to_storage(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        import json
        settings.setValue("cnc_macros", json.dumps(self.macros))

    def on_manage_macros(self):
        dialog = MacroDialog(self.macros, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.macros = dialog.macros
            self.save_macros_to_storage()
            self.load_macros()

    def on_test_connection_clicked(self):
        if self.is_connected:
            self.append_console_sig.emit(_("Already connected."), "info")
            return

        config = self.ui.connection_config()
        message = self.validate_connection_config(config)
        if message:
            self.append_console_sig.emit(message, "error")
            return

        self.ui.set_connection_actions_enabled(False)
        self.append_console_sig.emit(_("Testing connection..."), "info")
        threading.Thread(target=self._test_connection_worker, args=(config,), daemon=True).start()

    def _test_connection_worker(self, config):
        transport = None
        try:
            transport = self.build_transport(config)
            transport.open()
            self.test_connection_sig.emit(True, transport.description())
        except Exception as e:
            log.error("CNC test connection error: %s", e)
            self.test_connection_sig.emit(False, str(e))
        finally:
            if transport:
                try:
                    transport.close()
                except Exception:
                    pass

    def on_test_connection_finished(self, success, message):
        self.ui.set_connection_actions_enabled(True)
        if success:
            text = f"{_('Connection test succeeded')}: {message}"
            self.append_console_sig.emit(text, "info")
            try:
                self.app.inform.emit('[success] %s' % text)
            except Exception:
                pass
        else:
            text = f"{_('Connection test failed')}: {message}"
            self.append_console_sig.emit(text, "error")
            try:
                self.app.inform.emit('[ERROR_NOTCL] %s' % text)
            except Exception:
                pass

    def disconnect(self):
        self.stop_thread.set()
        with self.io_lock:
            transport = self.transport
            self.transport = None
            self.is_connected = False

        if transport:
            try:
                transport.close()
            except Exception:
                pass

        self.is_streaming = False
        self.connection_state_sig.emit(False, "")

    def on_send_command(self):
        command = self.ui.command_entry.text().strip()
        if command:
            self.ui.command_entry.clear()
            self.queue_command(command)

    def queue_command(self, command, log=True):
        self.queue_commands([command], log=log)

    def queue_commands(self, commands, log=True):
        normalized = [cmd.strip() for cmd in commands if str(cmd).strip()]
        if not normalized:
            return
        threading.Thread(target=self._send_commands_worker, args=(normalized, log), daemon=True).start()

    def _send_commands_worker(self, commands, log=True):
        for command in commands:
            self.send_command(command, log=log)

    def send_command(self, command, log=True):
        command = (command or "").strip()
        if not command:
            return []
        if not self.is_connected or not self.transport:
            message = _("Controller is not connected.")
            self.append_console_sig.emit(message, "error")
            try:
                self.app.inform.emit("[WARNING_NOTCL] %s" % message)
            except Exception:
                pass
            return []

        try:
            if log:
                self.append_console_sig.emit(command, "tx")
            with self.io_lock:
                responses = self.transport.send_line(command)
            for line in responses:
                self.handle_line(line, echo=True)
            return responses
        except Exception as e:
            self.append_console_sig.emit(f"{_('Communication error')}: {e}", "error")
            self.disconnect()
            return []

    def send_raw(self, data, label=""):
        if not data:
            return []
        if isinstance(data, str):
            return self.send_command(data)
        if not self.is_connected or not self.transport:
            message = _("Controller is not connected.")
            self.append_console_sig.emit(message, "error")
            try:
                self.app.inform.emit("[WARNING_NOTCL] %s" % message)
            except Exception:
                pass
            return []

        try:
            if label:
                self.append_console_sig.emit(label, "tx")
            with self.io_lock:
                responses = self.transport.send_raw(data)
            for line in responses:
                self.handle_line(line, echo=True)
            return responses
        except Exception as e:
            self.append_console_sig.emit(f"{_('Communication error')}: {e}", "error")
            self.disconnect()
            return []

    def send_profile_command(self, key, log=True):
        command = self.current_profile().get(key, "")
        if not command:
            self.append_console_sig.emit(f"{key}: {_('not supported by selected profile')}", "warn")
            return

        if isinstance(command, bytes):
            self.send_raw(command, label=key.upper() if log else "")
            return

        self.queue_commands(str(command).splitlines(), log=log)

    def on_home_clicked(self, *_args):
        if self.is_connected:
            self.update_status_sig.emit({"state": "Homing", "Pn": self.active_limit_pins})
        self.send_profile_command("home")

    def send_zero(self, axis):
        if self.current_profile_key() in {"fluidnc", "grbl"}:
            self.on_set_work_offset((axis,))
            return

        command = self.current_profile().get("zero_axis", "").format(axis=axis)
        self.queue_command(command)

    def on_zero_all_clicked(self, *_args):
        if self.current_profile_key() in {"fluidnc", "grbl"}:
            self.on_set_work_offset(("X", "Y", "Z"))
            return
        self.send_profile_command("zero_all")

    def send_jog(self, axis, direction):
        try:
            step = float(self.ui.get_jog_step())
            feed = int(self.ui.jog_feed.value())
        except Exception:
            step = 1.0
            feed = 1000

        template = self.current_profile().get("jog", "")
        distance = step * direction
        command = template.format(axis=axis, distance=distance, feed=feed)
        self.queue_commands(command.splitlines())

    def on_set_spindle_rpm(self):
        try:
            rpm = int(self.ui.spindle_rpm.value())
        except Exception:
            rpm = 0

        template = self.current_profile().get("spindle_set", "")
        if not template:
            self.append_console_sig.emit(f"spindle_set: {_('not supported by selected profile')}", "warn")
            return

        command = template.format(rpm=rpm)
        self.queue_commands(command.splitlines())

    def on_set_override(self, key, widget):
        try:
            percent = int(widget.value())
        except Exception:
            percent = 100

        template = self.current_profile().get(key, "")
        if not template:
            self.append_console_sig.emit(f"{key}: {_('not supported by selected profile')}", "warn")
            return

        command = template.format(percent=percent)
        self.queue_commands(command.splitlines())

    def on_probe_z(self):
        commands = self.probe_commands()
        if commands:
            self.queue_commands(commands)

    def selected_work_offset(self):
        if not hasattr(self.ui, "work_offset_combo"):
            return "G54", 1

        label = self.ui.work_offset_combo.currentText().strip() or "G54"
        p_num = self.ui.work_offset_combo.currentData()
        try:
            p_num = int(p_num)
        except (TypeError, ValueError):
            p_num = 1
        return label, p_num

    def probe_settings(self):
        profile = self.current_machine_profile()
        try:
            distance = float(self.ui.probe_distance.value())
        except Exception:
            distance = 50.0
        try:
            feed = int(self.ui.probe_feed.value())
        except Exception:
            feed = int(profile.get("probe_feed", 100))
        try:
            plate = float(self.ui.touch_plate_thickness.value())
        except Exception:
            plate = 0.0
        try:
            retract = float(self.ui.probe_retract.value())
        except Exception:
            retract = 5.0

        return {
            "distance": abs(distance),
            "feed": max(1, feed),
            "plate": plate,
            "retract": max(0.0, retract),
        }

    def probe_commands(self):
        template = self.current_profile().get("probe_z", "")
        if not template:
            self.append_console_sig.emit(f"probe_z: {_('not supported by selected profile')}", "warn")
            return []

        settings = self.probe_settings()
        command = str(template)
        if "{probe_feed}" in command or "{probe_distance}" in command:
            command = command.format(
                probe_feed=settings["feed"],
                probe_distance=settings["distance"]
            )
        else:
            command = re.sub(
                r"\bZ\s*-?\d+(?:\.\d+)?",
                f"Z-{settings['distance']:.4f}",
                command,
                flags=re.IGNORECASE
            )
            command = re.sub(
                r"\bF\s*-?\d+(?:\.\d+)?",
                f"F{settings['feed']}",
                command,
                flags=re.IGNORECASE
            )
        return command.splitlines()

    def on_probe_and_set_z(self):
        _wcs_label, p_num = self.selected_work_offset()
        settings = self.probe_settings()
        commands = self.probe_commands()
        if not commands:
            return

        commands.append(f"G10 L20 P{p_num} Z{settings['plate']:.4f}")
        if settings["retract"] > 0:
            commands.extend([
                "G91",
                f"G0 Z{settings['retract']:.4f}",
                "G90"
            ])
        self.queue_commands(commands)

    def on_set_work_offset(self, axes):
        wcs_label, p_num = self.selected_work_offset()
        axis_values = " ".join(f"{axis}0" for axis in axes)
        self.queue_commands([
            wcs_label,
            f"G10 L20 P{p_num} {axis_values}",
            wcs_label
        ])

    def on_apply_work_coordinate_system(self):
        wcs_label, _p_num = self.selected_work_offset()
        self.queue_command(wcs_label)

    def selected_job_origin_mode(self):
        combo = getattr(self.ui, "job_origin_combo", None)
        if combo is None:
            return "top_left"
        return combo.currentData() or "top_left"

    def selected_job_placement_mode(self):
        combo = getattr(self.ui, "job_placement_combo", None)
        if combo is None:
            return "origin"
        return combo.currentData() or "origin"

    def selected_job_size(self, raw_width, raw_height, units):
        try:
            job_width = float(self.ui.job_size_x.value())
        except Exception:
            job_width = 0.0
        try:
            job_height = float(self.ui.job_size_y.value())
        except Exception:
            job_height = 0.0

        if units == "inch":
            job_width /= 25.4
            job_height /= 25.4

        if job_width <= 0:
            job_width = raw_width
        if job_height <= 0:
            job_height = raw_height
        return max(0.0, job_width), max(0.0, job_height)

    def selected_job_margin(self, units):
        try:
            margin_x = float(self.ui.job_margin_x.value())
        except Exception:
            margin_x = 0.0
        try:
            margin_y = float(self.ui.job_margin_y.value())
        except Exception:
            margin_y = 0.0

        if units == "inch":
            margin_x /= 25.4
            margin_y /= 25.4
        return max(0.0, margin_x), max(0.0, margin_y)

    @staticmethod
    def material_bounds_for_origin(mode, job_width, job_height):
        if mode == "center":
            return [-job_width / 2.0, job_width / 2.0, -job_height / 2.0, job_height / 2.0]
        if mode == "top_left":
            return [0.0, job_width, -job_height, 0.0]
        return [0.0, job_width, 0.0, job_height]

    @staticmethod
    def resolved_job_placement(origin_mode, placement):
        if placement and placement != "origin":
            return placement
        if origin_mode == "center":
            return "center"
        if origin_mode == "top_left":
            return "top_left"
        return "bottom_left"

    @staticmethod
    def job_placement_alignment(placement):
        if placement == "center":
            return "center", "center"

        if placement.endswith("_right"):
            x_align = "right"
        elif placement.endswith("_center"):
            x_align = "center"
        else:
            x_align = "left"

        if placement.startswith("top_") or placement == "top_left":
            y_align = "top"
        elif placement.startswith("center_"):
            y_align = "center"
        else:
            y_align = "bottom"

        return x_align, y_align

    @staticmethod
    def job_placement_label(placement):
        labels = {
            "origin": _("Same as Origin"),
            "bottom_left": _("Bottom-Left"),
            "bottom_center": _("Bottom-Center"),
            "bottom_right": _("Bottom-Right"),
            "center_left": _("Center-Left"),
            "center": _("Center"),
            "center_right": _("Center-Right"),
            "top_left": _("Back-Left"),
            "top_center": _("Back-Center"),
            "top_right": _("Back-Right"),
        }
        return labels.get(placement, _("Placement"))

    @staticmethod
    def target_bounds_for_placement(material_bounds, raw_width, raw_height, margin_x, margin_y, placement):
        x_min, x_max, y_min, y_max = material_bounds
        inner_x_min = x_min + margin_x
        inner_x_max = x_max - margin_x
        inner_y_min = y_min + margin_y
        inner_y_max = y_max - margin_y

        if inner_x_max < inner_x_min:
            midpoint = (x_min + x_max) / 2.0
            inner_x_min = midpoint
            inner_x_max = midpoint
        if inner_y_max < inner_y_min:
            midpoint = (y_min + y_max) / 2.0
            inner_y_min = midpoint
            inner_y_max = midpoint

        x_align, y_align = ToolCNCControl.job_placement_alignment(placement)
        if x_align == "right":
            target_x_min = inner_x_max - raw_width
        elif x_align == "center":
            target_x_min = inner_x_min + ((inner_x_max - inner_x_min - raw_width) / 2.0)
        else:
            target_x_min = inner_x_min

        if y_align == "top":
            target_y_min = inner_y_max - raw_height
        elif y_align == "center":
            target_y_min = inner_y_min + ((inner_y_max - inner_y_min - raw_height) / 2.0)
        else:
            target_y_min = inner_y_min

        return {
            "X": [target_x_min, target_x_min + raw_width],
            "Y": [target_y_min, target_y_min + raw_height],
        }

    @staticmethod
    def margin_guides_for_bounds(material_bounds, margin_x, margin_y, factor):
        x_min, x_max, y_min, y_max = material_bounds
        guides = []
        if margin_x > 0:
            guides.append({"axis": "X", "value": (x_min + margin_x) * factor})
            guides.append({"axis": "X", "value": (x_max - margin_x) * factor})
        if margin_y > 0:
            guides.append({"axis": "Y", "value": (y_min + margin_y) * factor})
            guides.append({"axis": "Y", "value": (y_max - margin_y) * factor})
        return guides

    def on_fit_job_size_clicked(self, *_args):
        name, lines = self.selected_preview_job()
        if not lines:
            self.append_console_sig.emit(_("No CNCJob object selected."), "error")
            return

        bounds, units = self.gcode_bounds(lines, cutting_only=True)
        if bounds["X"][0] is None or bounds["Y"][0] is None:
            bounds, units = self.gcode_bounds(lines)
        if bounds["X"][0] is None or bounds["Y"][0] is None:
            self.append_console_sig.emit(_("Selected CNCJob has no usable XY bounds."), "error")
            return

        width = bounds["X"][1] - bounds["X"][0]
        height = bounds["Y"][1] - bounds["Y"][0]
        if units == "inch":
            width *= 25.4
            height *= 25.4

        self.ui.job_size_x.set_value(width)
        self.ui.job_size_y.set_value(height)
        self.append_console_sig.emit(
            _("Job size fitted from %s: X%.3f Y%.3f mm") % (name, width, height),
            "info"
        )
        self.on_preview_refresh(refresh_jobs=False)

    def auto_level_settings(self):
        def double_value(attr, default=0.0):
            widget = getattr(self.ui, attr, None)
            try:
                return float(widget.value())
            except Exception:
                return float(default)

        def int_value(attr, default=1):
            widget = getattr(self.ui, attr, None)
            try:
                return int(widget.value())
            except Exception:
                return int(default)

        x_min = double_value("autolevel_x_min")
        x_max = double_value("autolevel_x_max")
        y_min = double_value("autolevel_y_min")
        y_max = double_value("autolevel_y_max")
        if x_max < x_min:
            x_min, x_max = x_max, x_min
        if y_max < y_min:
            y_min, y_max = y_max, y_min

        probe_depth = double_value("autolevel_probe_depth", -1.0)
        if probe_depth >= 0:
            probe_depth = -abs(probe_depth) if probe_depth else -1.0

        def bool_value(attr, default=True):
            widget = getattr(self.ui, attr, None)
            try:
                return bool(widget.get_value())
            except Exception:
                return bool(default)

        return {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "rows": max(2, int_value("autolevel_rows", 4)),
            "columns": max(2, int_value("autolevel_columns", 4)),
            "safe_z": double_value("autolevel_safe_z", 5.0),
            "probe_depth": probe_depth,
            "probe_feed": max(1, int_value("autolevel_probe_feed", 120)),
            "auto_zero_z": bool_value("autolevel_auto_zero", True),
        }

    @staticmethod
    def auto_level_range_values(start, stop, count):
        if count <= 1:
            return [start]
        step = (stop - start) / float(count - 1)
        return [start + (step * index) for index in range(count)]

    def auto_level_probe_points(self, settings):
        x_values = self.auto_level_range_values(settings["x_min"], settings["x_max"], settings["columns"])
        y_values = self.auto_level_range_values(settings["y_min"], settings["y_max"], settings["rows"])
        points = []
        for row, y_value in enumerate(y_values):
            columns = range(len(x_values)) if row % 2 == 0 else range(len(x_values) - 1, -1, -1)
            for column in columns:
                points.append({
                    "row": row,
                    "column": column,
                    "x": x_values[column],
                    "y": y_value,
                })
        return x_values, y_values, points

    @staticmethod
    def auto_level_reference_point(x_values, y_values, measurements):
        best = None
        for row, y_value in enumerate(y_values):
            for column, x_value in enumerate(x_values):
                z_value = measurements[row][column]
                distance = math.hypot(x_value, y_value)
                if best is None or distance < best["distance"]:
                    best = {
                        "x": x_value,
                        "y": y_value,
                        "z": z_value,
                        "distance": distance,
                    }
        return best or {"x": 0.0, "y": 0.0, "z": 0.0, "distance": 0.0}

    def on_auto_level_fit_area(self, *_args):
        name, lines = self.selected_preview_job()
        if not lines:
            self.append_console_sig.emit(_("No CNCJob object selected."), "error")
            return

        transform_context = self.stream_transform_context(lines)
        units = self.effective_gcode_units(transform_context.get("units"))
        bounds = None
        preview_lines = [self.transform_stream_command(line, transform_context) for line in lines]
        _segments, path_bounds, _start_point = self.gcode_preview_segments(preview_lines)
        if path_bounds:
            bounds = path_bounds
        else:
            gcode_bounds, units = self.gcode_bounds(preview_lines, cutting_only=True)
            if gcode_bounds["X"][0] is None or gcode_bounds["Y"][0] is None:
                gcode_bounds, units = self.gcode_bounds(preview_lines)
            if gcode_bounds["X"][0] is not None and gcode_bounds["Y"][0] is not None:
                bounds = [
                    gcode_bounds["X"][0],
                    gcode_bounds["X"][1],
                    gcode_bounds["Y"][0],
                    gcode_bounds["Y"][1],
                ]

        if not bounds:
            self.append_console_sig.emit(_("Selected CNCJob has no usable XY bounds."), "error")
            return

        units = self.effective_gcode_units(units)
        factor = 25.4 if units == "inch" else 1.0
        self.ui.autolevel_x_min.set_value(bounds[0] * factor)
        self.ui.autolevel_x_max.set_value(bounds[1] * factor)
        self.ui.autolevel_y_min.set_value(bounds[2] * factor)
        self.ui.autolevel_y_max.set_value(bounds[3] * factor)
        self.ui.autolevel_status.setText(_("Area fitted from %s") % (name or _("CNCJob")))
        self.append_console_sig.emit(
            _("Auto level area fitted from toolpath: X%.3f..%.3f  Y%.3f..%.3f mm") % (
                bounds[0] * factor, bounds[1] * factor, bounds[2] * factor, bounds[3] * factor
            ),
            "info"
        )

    def current_auto_level_job_bounds_mm(self):
        _name, lines = self.selected_preview_job()
        if not lines:
            return None

        context = self.stream_transform_context(lines)
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        material_bounds = context.get("material_bounds")
        if material_bounds:
            return [value * factor for value in material_bounds]

        preview_lines = [self.transform_stream_command(line, context) for line in lines]
        _segments, path_bounds, _start_point = self.gcode_preview_segments(preview_lines)
        if path_bounds:
            return [value * factor for value in path_bounds]
        return None

    def auto_level_area_is_inside_job(self, settings):
        bounds = self.current_auto_level_job_bounds_mm()
        if not bounds:
            return True, None

        tolerance = 0.001
        area = [settings["x_min"], settings["x_max"], settings["y_min"], settings["y_max"]]
        inside = (
            area[0] >= bounds[0] - tolerance and
            area[1] <= bounds[1] + tolerance and
            area[2] >= bounds[2] - tolerance and
            area[3] <= bounds[3] + tolerance
        )
        return inside, bounds

    def on_auto_level_probe_clicked(self, *_args):
        if not self.is_connected:
            self.append_console_sig.emit(_("Controller is not connected."), "error")
            return
        if self.is_streaming:
            self.append_console_sig.emit(_("Stop queue streaming before probing."), "warn")
            return
        if self.is_auto_leveling:
            return
        if self.current_profile_key() not in {"fluidnc", "grbl"}:
            self.append_console_sig.emit(_("Auto level probing currently requires GRBL/FluidNC probe reports."), "warn")
            return

        settings = self.auto_level_settings()
        if math.isclose(settings["x_min"], settings["x_max"]) or math.isclose(settings["y_min"], settings["y_max"]):
            self.on_auto_level_fit_area()
            settings = self.auto_level_settings()

        if math.isclose(settings["x_min"], settings["x_max"]) or math.isclose(settings["y_min"], settings["y_max"]):
            self.append_console_sig.emit(_("Auto level area is empty."), "error")
            return

        inside_job, job_bounds = self.auto_level_area_is_inside_job(settings)
        if not inside_job:
            self.append_console_sig.emit(
                _("Auto level area is outside the current job bounds. Click Fit Area or correct X/Y values. "
                  "Job bounds: X%.3f..%.3f  Y%.3f..%.3f mm") % (
                    job_bounds[0], job_bounds[1], job_bounds[2], job_bounds[3]
                ),
                "error"
            )
            return

        x_values, y_values, points = self.auto_level_probe_points(settings)
        if not points:
            self.append_console_sig.emit(_("No probing points generated."), "error")
            return

        wcs_label, _p_num = self.selected_work_offset()
        spindle_stop = self.current_profile().get("spindle_stop", "M5")
        self.is_auto_leveling = True
        self.auto_level_cancel.clear()
        self.auto_level_update_sig.emit({
            "busy": True,
            "progress": 0,
            "status": _("Probing 0/%d") % len(points),
        })
        threading.Thread(
            target=self.auto_level_probe_worker,
            args=(settings, x_values, y_values, points, wcs_label, spindle_stop),
            daemon=True
        ).start()

    def on_auto_level_stop(self, *_args):
        if not self.is_auto_leveling:
            return
        self.auto_level_cancel.set()
        self.auto_level_update_sig.emit({"status": _("Stopping after current probe...")})

    def on_auto_level_clear(self, *_args):
        if self.is_auto_leveling:
            return
        self.auto_level_map = None
        self.ui.autolevel_enable_cb.set_value(False)
        self.auto_level_update_sig.emit({
            "progress": 0,
            "status": _("No height map"),
            "map": None,
        })
        self.on_preview_refresh(refresh_jobs=False)

    def on_auto_level_3d_clicked(self, *_args):
        viewer = getattr(self.app, "cnc_height_map_3d_tool", None)
        if viewer is None:
            self.append_console_sig.emit(_("Height Map 3D plugin is not available."), "error")
            return
        viewer.run(toggle=True)

    def send_command_and_wait(self, command, timeout=5.0):
        self.ok_received.clear()
        self.send_command(command, log=True)
        return self.ok_received.wait(timeout=timeout)

    def auto_level_probe_worker(self, settings, x_values, y_values, points, wcs_label, spindle_stop):
        previous_poll = self.status_poll_enabled
        measurements = [[None for _ in x_values] for _ in y_values]
        total = len(points)

        try:
            self.status_poll_enabled = False
            setup_commands = [wcs_label]
            if isinstance(spindle_stop, str) and spindle_stop.strip():
                setup_commands.extend(spindle_stop.splitlines())
            setup_commands.extend([
                "G21",
                "G90",
                "G0 Z%s" % self.format_gcode_number(settings["safe_z"]),
            ])
            for command in setup_commands:
                if self.auto_level_cancel.is_set():
                    raise RuntimeError(_("Auto level probing was stopped."))
                if not self.send_command_and_wait(command, timeout=8.0):
                    raise RuntimeError(_("Controller did not acknowledge: %s") % command)

            self.work_offsets = {}
            self.g92_offset = [0.0, 0.0, 0.0]
            self.tool_length_offset = [0.0, 0.0, 0.0]
            self.probe_coordinate_mode = None
            if not self.send_command_and_wait("$#", timeout=8.0):
                raise RuntimeError(_("Controller did not acknowledge: %s") % "$#")

            probe_timeout = max(10.0, (abs(settings["probe_depth"]) / settings["probe_feed"] * 60.0) + 5.0)
            for index, point in enumerate(points, start=1):
                if self.auto_level_cancel.is_set():
                    raise RuntimeError(_("Auto level probing was stopped."))

                self.auto_level_update_sig.emit({
                    "progress": ((index - 1) / total) * 100.0,
                    "status": _("Probing %d/%d") % (index, total),
                })

                move_command = "G0 X%s Y%s" % (
                    self.format_gcode_number(point["x"]),
                    self.format_gcode_number(point["y"]),
                )
                if not self.send_command_and_wait(move_command, timeout=12.0):
                    raise RuntimeError(_("Controller did not acknowledge: %s") % move_command)

                self.last_probe_result = None
                self.probe_result_event.clear()
                self.ok_received.clear()
                probe_command = "G38.2 Z%s F%d" % (
                    self.format_gcode_number(settings["probe_depth"]),
                    int(settings["probe_feed"]),
                )
                self.send_command(probe_command, log=True)
                if not self.probe_result_event.wait(timeout=probe_timeout):
                    raise RuntimeError(_("Probe result timed out."))

                result = self.last_probe_result or {}
                self.ok_received.wait(timeout=2.0)
                if not result.get("success", False):
                    raise RuntimeError(_("Probe failed at X%.3f Y%.3f.") % (point["x"], point["y"]))

                work_result = self.probe_result_to_work_position(
                    result,
                    wcs_label,
                    expected_xy=(point["x"], point["y"])
                )
                measurements[point["row"]][point["column"]] = work_result["z"]

                retract_command = "G0 Z%s" % self.format_gcode_number(settings["safe_z"])
                if not self.send_command_and_wait(retract_command, timeout=8.0):
                    raise RuntimeError(_("Controller did not acknowledge: %s") % retract_command)

            reference = self.auto_level_reference_point(x_values, y_values, measurements)
            measured_values = [
                z_value for row_values in measurements for z_value in row_values if z_value is not None
            ]
            # Normalize all Z measurements relative to the reference point.
            # The reference point (closest to work XY origin) defines Z=0 of the map.
            # All other values are deltas — same as 3D printer auto bed leveling.
            measured_ref_z = reference["z"]
            normalized_measurements = [
                [z_val - measured_ref_z if z_val is not None else None for z_val in row]
                for row in measurements
            ]
            auto_map = {
                "unit": "mm",
                "x_values": x_values,
                "y_values": y_values,
                "z_values": normalized_measurements,
                "reference_x": reference["x"],
                "reference_y": reference["y"],
                "reference_z": 0.0,
                "measured_reference_z": measured_ref_z,
                "reference_mode": "self_zeroing",
                "probe_coordinate_mode": self.probe_coordinate_mode,
                "rows": len(y_values),
                "columns": len(x_values),
                "point_count": total,
                "created_at": time.strftime("%H:%M:%S"),
            }
            self.auto_level_map = auto_map

            # Auto Zero Z: move to reference point and set G92 Z0 there.
            # Like 3D printer auto bed leveling — the probe map defines its own Z=0.
            # This means the user only needs to physically touch the bit to the PCB
            # surface (no manual Set Z Zero needed before probing).
            if settings.get("auto_zero_z", True):
                self.append_console_sig.emit(
                    _("Auto Zero Z: moving to X%.3f Y%.3f and probing surface to set Z=0...") % (
                        reference["x"], reference["y"]
                    ), "info"
                )
                # Step 1: move to reference XY (already at safe Z from last retract)
                move_ref = "G0 X%s Y%s" % (
                    self.format_gcode_number(reference["x"]),
                    self.format_gcode_number(reference["y"]),
                )
                if not self.send_command_and_wait(move_ref, timeout=12.0):
                    self.append_console_sig.emit(
                        _("Auto Zero Z: move to reference point failed."), "warn"
                    )
                else:
                    # Step 2: probe the surface again (same settings as main probe)
                    # This stops exactly when the bit touches the PCB — no G0 to raw machine Z.
                    probe_timeout = max(10.0, (abs(settings["probe_depth"]) / settings["probe_feed"] * 60.0) + 5.0)
                    self.last_probe_result = None
                    self.probe_result_event.clear()
                    self.ok_received.clear()
                    zero_probe_cmd = "G38.2 Z%s F%d" % (
                        self.format_gcode_number(settings["probe_depth"]),
                        int(settings["probe_feed"]),
                    )
                    self.send_command(zero_probe_cmd, log=True)
                    probe_hit = self.probe_result_event.wait(timeout=probe_timeout)
                    self.ok_received.wait(timeout=2.0)

                    if probe_hit and self.last_probe_result and self.last_probe_result.get("success"):
                        # Step 3: at the exact surface contact point → set Z=0
                        if self.send_command_and_wait("G92 Z0", timeout=5.0):
                            # Step 4: retract to safe Z
                            retract = "G0 Z%s" % self.format_gcode_number(settings["safe_z"])
                            self.send_command_and_wait(retract, timeout=10.0)
                            self.append_console_sig.emit(
                                _("Auto Zero Z complete: Z=0 set at PCB surface (reference point)."), "info"
                            )
                        else:
                            self.append_console_sig.emit(
                                _("Auto Zero Z: G92 Z0 not acknowledged."), "warn"
                            )
                    else:
                        self.append_console_sig.emit(
                            _("Auto Zero Z: surface probe did not trigger. Check Probe Z depth setting."), "warn"
                        )
                        # Retract to safety even on failure
                        self.send_command_and_wait("G0 Z%s" % self.format_gcode_number(settings["safe_z"]), timeout=10.0)
            self.auto_level_update_sig.emit({
                "busy": False,
                "enabled": True,
                "map": auto_map,
                "progress": 100,
                "status": _("Height map ready: %d points") % total,
            })
            if measured_values:
                self.append_console_sig.emit(
                    _("Auto level height map ready: %d points. Z range %.4f..%.4f mm; work zero is reference.") % (
                        total, min(measured_values), max(measured_values)
                    ),
                    "info"
                )
            else:
                self.append_console_sig.emit(_("Auto level height map ready: %d points.") % total, "info")
        except Exception as err:
            self.auto_level_update_sig.emit({
                "busy": False,
                "progress": 0,
                "status": "%s: %s" % (_("Auto level failed"), err),
            })
            self.append_console_sig.emit("%s: %s" % (_("Auto level failed"), err), "error")
        finally:
            self.status_poll_enabled = previous_poll
            self.is_auto_leveling = False
            self.auto_level_update_sig.emit({"busy": False})

    def update_auto_level_ui(self, data):
        if "status" in data and hasattr(self.ui, "autolevel_status"):
            self.ui.autolevel_status.setText(str(data["status"]))
        if "progress" in data and hasattr(self.ui, "autolevel_progress"):
            self.ui.autolevel_progress.setValue(int(max(0, min(100, float(data["progress"])))))
        if "enabled" in data and hasattr(self.ui, "autolevel_enable_cb"):
            self.ui.autolevel_enable_cb.set_value(bool(data["enabled"]))
        if "map" in data and data.get("map") is None and hasattr(self.ui, "autolevel_progress"):
            self.ui.autolevel_progress.setValue(0)

        busy = bool(data.get("busy", self.is_auto_leveling))
        if hasattr(self.ui, "autolevel_probe_btn"):
            self.ui.autolevel_probe_btn.setEnabled(self.is_connected and not busy)
        if hasattr(self.ui, "autolevel_stop_btn"):
            self.ui.autolevel_stop_btn.setEnabled(self.is_connected and busy)
        if hasattr(self.ui, "autolevel_clear_btn"):
            self.ui.autolevel_clear_btn.setEnabled(not busy)
        if "map" in data or "enabled" in data:
            self.on_preview_refresh(refresh_jobs=False)

    def gcode_bounds(self, lines, cutting_only=False):
        position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        bounds = {axis: [None, None] for axis in "XYZ"}
        absolute = True
        units = None
        current_motion = None
        has_seen_z = False

        for raw_line in lines:
            clean_line = self.clean_gcode_line(raw_line)
            if not clean_line:
                continue

            upper_line = clean_line.upper()
            words = self.gcode_words(upper_line)
            g_codes = [int(float(value)) for value in re.findall(
                r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", upper_line
            )]

            if 20 in g_codes:
                units = "inch"
            if 21 in g_codes:
                units = "mm"
            if 90 in g_codes:
                absolute = True
            if 91 in g_codes:
                absolute = False

            motion = None
            for g_code in g_codes:
                if g_code in [0, 1, 2, 3]:
                    motion = g_code
                    current_motion = g_code
            if motion is None:
                motion = current_motion
            if motion is None:
                continue

            next_position = dict(position)
            has_axis = False
            for axis in "XYZ":
                if axis in words:
                    has_axis = True
                    next_position[axis] = position[axis] + words[axis] if not absolute else words[axis]
            if not has_axis:
                continue

            line_has_z = "Z" in words
            include_bounds = not cutting_only
            if cutting_only and motion in [1, 2, 3]:
                include_bounds = not has_seen_z or position["Z"] < 0 or next_position["Z"] < 0

            if include_bounds:
                for point in [position, next_position]:
                    for axis in "XYZ":
                        value = point[axis]
                        if bounds[axis][0] is None or value < bounds[axis][0]:
                            bounds[axis][0] = value
                        if bounds[axis][1] is None or value > bounds[axis][1]:
                            bounds[axis][1] = value

            position = next_position
            if line_has_z:
                has_seen_z = True

        return bounds, units

    def effective_gcode_units(self, units):
        if units in {"inch", "mm"}:
            return units
        return "inch" if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else "mm"

    def gcode_preview_segments(self, lines):
        position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        absolute = True
        current_motion = None
        segments = []
        path_bounds = {"X": [None, None], "Y": [None, None]}
        all_bounds = {"X": [None, None], "Y": [None, None]}
        start_point = None
        first_motion_point = None

        def add_point(point, bounds):
            for axis, value in [("X", point[0]), ("Y", point[1])]:
                if bounds[axis][0] is None or value < bounds[axis][0]:
                    bounds[axis][0] = value
                if bounds[axis][1] is None or value > bounds[axis][1]:
                    bounds[axis][1] = value

        def add_segment(start, end, rapid=False):
            nonlocal start_point, first_motion_point
            if start[0] == end[0] and start[1] == end[1]:
                return
            segments.append({
                "start": [start[0], start[1]],
                "end": [end[0], end[1]],
                "rapid": bool(rapid),
            })
            if first_motion_point is None:
                first_motion_point = [start[0], start[1]]
            add_point(start, all_bounds)
            add_point(end, all_bounds)
            if not rapid:
                if start_point is None:
                    start_point = [start[0], start[1]]
                add_point(start, path_bounds)
                add_point(end, path_bounds)

        for raw_line in lines:
            clean_line = self.clean_gcode_line(raw_line)
            if not clean_line:
                continue

            upper_line = clean_line.upper()
            words = self.gcode_words(upper_line)
            g_codes = [int(float(value)) for value in re.findall(
                r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", upper_line
            )]

            if 90 in g_codes:
                absolute = True
            if 91 in g_codes:
                absolute = False

            motion = None
            for g_code in g_codes:
                if g_code in [0, 1, 2, 3]:
                    motion = g_code
                    current_motion = g_code
            if motion is None:
                motion = current_motion
            if motion is None:
                continue

            next_position = dict(position)
            has_axis = False
            for axis in "XYZ":
                if axis in words:
                    has_axis = True
                    next_position[axis] = position[axis] + words[axis] if not absolute else words[axis]
            if not has_axis:
                continue

            start_xy = (position["X"], position["Y"])
            end_xy = (next_position["X"], next_position["Y"])

            if motion in [2, 3] and ("I" in words or "J" in words):
                center_x = position["X"] + words.get("I", 0.0)
                center_y = position["Y"] + words.get("J", 0.0)
                radius = math.hypot(position["X"] - center_x, position["Y"] - center_y)
                if radius > 0:
                    start_angle = math.atan2(position["Y"] - center_y, position["X"] - center_x)
                    end_angle = math.atan2(next_position["Y"] - center_y, next_position["X"] - center_x)
                    if motion == 3:
                        while end_angle <= start_angle:
                            end_angle += math.tau
                    else:
                        while end_angle >= start_angle:
                            end_angle -= math.tau
                    sweep = end_angle - start_angle
                    steps = max(8, min(96, int(abs(sweep) * radius / 1.0)))
                    previous = start_xy
                    for step in range(1, steps + 1):
                        angle = start_angle + (sweep * step / steps)
                        point = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
                        add_segment(previous, point, rapid=False)
                        previous = point
                else:
                    add_segment(start_xy, end_xy, rapid=False)
            else:
                add_segment(start_xy, end_xy, rapid=(motion == 0))

            position = next_position

        if path_bounds["X"][0] is None or path_bounds["Y"][0] is None:
            if all_bounds["X"][0] is None or all_bounds["Y"][0] is None:
                return segments, None, start_point or first_motion_point
            path_bounds = all_bounds

        return (
            segments,
            [path_bounds["X"][0], path_bounds["X"][1], path_bounds["Y"][0], path_bounds["Y"][1]],
            start_point or first_motion_point,
        )

    @staticmethod
    def scaled_point(point, factor):
        return [point[0] * factor, point[1] * factor]

    def build_job_canvas_preview(self, name, raw_lines, preview_lines):
        if not raw_lines:
            return {}

        context = self.stream_transform_context(raw_lines)
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        mode = context.get("mode", self.selected_job_origin_mode())
        placement = context.get(
            "placement",
            self.resolved_job_placement(mode, self.selected_job_placement_mode())
        )
        job_width = float(context.get("job_width", 0.0) or 0.0)
        job_height = float(context.get("job_height", 0.0) or 0.0)
        material_bounds = context.get("material_bounds")

        if job_width <= 0 or job_height <= 0:
            preview_bounds, preview_units = self.gcode_bounds(preview_lines)
            units = self.effective_gcode_units(preview_units)
            factor = 25.4 if units == "inch" else 1.0
            if preview_bounds["X"][0] is None or preview_bounds["Y"][0] is None:
                return {}
            job_width = preview_bounds["X"][1] - preview_bounds["X"][0]
            job_height = preview_bounds["Y"][1] - preview_bounds["Y"][0]

        if not material_bounds:
            material_bounds = self.material_bounds_for_origin(mode, job_width, job_height)

        segments, path_bounds, start_point = self.gcode_preview_segments(preview_lines)
        scaled_segments = [
            {
                "start": self.scaled_point(segment["start"], factor),
                "end": self.scaled_point(segment["end"], factor),
                "rapid": segment.get("rapid", False),
            }
            for segment in segments
        ]

        margin_x = float(context.get("margin_x", 0.0) or 0.0)
        margin_y = float(context.get("margin_y", 0.0) or 0.0)
        if mode == "center":
            origin_label = _("Center")
        elif mode == "top_left":
            origin_label = _("Back-Left")
        else:
            origin_label = _("Bottom-Left")

        margin_guides = self.margin_guides_for_bounds(material_bounds, margin_x, margin_y, factor)
        scaled_job_bounds = [value * factor for value in material_bounds]
        scaled_path_bounds = [value * factor for value in path_bounds] if path_bounds else None
        scaled_start = self.scaled_point(start_point, factor) if start_point else None
        tolerance = 0.001
        outside = False
        if scaled_path_bounds:
            outside = (
                scaled_path_bounds[0] < scaled_job_bounds[0] - tolerance or
                scaled_path_bounds[1] > scaled_job_bounds[1] + tolerance or
                scaled_path_bounds[2] < scaled_job_bounds[2] - tolerance or
                scaled_path_bounds[3] > scaled_job_bounds[3] + tolerance
            )

        return {
            "label": _("%s | Job %.1f x %.1f mm | Origin: %s | Place: %s") % (
                name or _("CNCJob"),
                job_width * factor,
                job_height * factor,
                origin_label,
                self.job_placement_label(placement),
            ),
            "job_bounds": scaled_job_bounds,
            "segments": scaled_segments,
            "path_bounds": scaled_path_bounds,
            "origin": [0.0, 0.0],
            "start": scaled_start,
            "margin_guides": margin_guides,
            "outside": outside,
        }

    def stream_transform_context(self, lines):
        mode = self.selected_job_origin_mode()
        bounds, units = self.gcode_bounds(lines, cutting_only=True)
        if bounds["X"][0] is None or bounds["Y"][0] is None:
            bounds, units = self.gcode_bounds(lines)
        units = self.effective_gcode_units(units)
        x_min = bounds.get("X", [None, None])[0]
        x_max = bounds.get("X", [None, None])[1]
        y_bounds = bounds.get("Y", [None, None])
        y_min = y_bounds[0]
        y_max = y_bounds[1]
        if x_min is None or x_max is None or y_min is None or y_max is None:
            return {
                "mode": mode,
                "enabled": False,
                "absolute": True,
                "units": units,
            }

        raw_width = x_max - x_min
        raw_height = y_max - y_min
        job_width, job_height = self.selected_job_size(raw_width, raw_height, units)
        margin_x, margin_y = self.selected_job_margin(units)
        material_bounds = self.material_bounds_for_origin(mode, job_width, job_height)
        selected_placement = self.selected_job_placement_mode()
        placement = self.resolved_job_placement(mode, selected_placement)

        if mode == "absolute":
            return {
                "mode": mode,
                "enabled": False,
                "job_width": job_width,
                "job_height": job_height,
                "margin_x": margin_x,
                "margin_y": margin_y,
                "material_bounds": material_bounds,
                "placement": placement,
                "absolute": True,
                "units": units,
            }

        target_bounds = self.target_bounds_for_placement(
            material_bounds, raw_width, raw_height, margin_x, margin_y, placement
        )
        x_anchor = x_min - target_bounds["X"][0]
        y_anchor = y_min - target_bounds["Y"][0]

        return {
            "mode": mode,
            "enabled": True,
            "x_anchor": x_anchor,
            "y_anchor": y_anchor,
            "job_width": job_width,
            "job_height": job_height,
            "margin_x": margin_x,
            "margin_y": margin_y,
            "material_bounds": material_bounds,
            "placement": placement,
            "target_bounds": target_bounds,
            "absolute": True,
            "units": units,
        }

    @staticmethod
    def format_gcode_number(value):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text not in {"", "-0"} else "0"

    @staticmethod
    def auto_level_map_is_valid(height_map):
        if not isinstance(height_map, dict):
            return False
        x_values = height_map.get("x_values", [])
        y_values = height_map.get("y_values", [])
        z_values = height_map.get("z_values", [])
        if len(x_values) < 2 or len(y_values) < 2:
            return False
        if len(z_values) != len(y_values):
            return False
        return all(isinstance(row, list) and len(row) == len(x_values) for row in z_values)

    @staticmethod
    def auto_level_map_z_values(height_map):
        if not isinstance(height_map, dict):
            return []
        values = []
        for row_values in height_map.get("z_values", []):
            if not isinstance(row_values, list):
                continue
            for z_value in row_values:
                try:
                    values.append(float(z_value))
                except (TypeError, ValueError):
                    pass
        return values

    def active_auto_level_map(self):
        enabled_widget = getattr(self.ui, "autolevel_enable_cb", None)
        enabled = bool(enabled_widget.get_value()) if enabled_widget is not None else False
        if not enabled:
            return None
        if not self.auto_level_map_is_valid(self.auto_level_map):
            return None
        return self.auto_level_map

    def attach_auto_level_context(self, context):
        height_map = self.active_auto_level_map()
        context["autolevel_enabled"] = height_map is not None
        context["autolevel_map"] = height_map
        context["position"] = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        context["current_motion"] = None
        return context

    @staticmethod
    def auto_level_bracket(values, value):
        if value <= values[0]:
            return 0, 0
        if value >= values[-1]:
            last = len(values) - 1
            return last, last
        for index in range(len(values) - 1):
            if values[index] <= value <= values[index + 1]:
                return index, index + 1
        last = len(values) - 1
        return last, last

    @staticmethod
    def linear_interpolate(a, b, ratio):
        return a + ((b - a) * ratio)

    def auto_level_surface_z(self, height_map, x_mm, y_mm):
        x_values = height_map["x_values"]
        y_values = height_map["y_values"]
        z_values = height_map["z_values"]

        x0_idx, x1_idx = self.auto_level_bracket(x_values, x_mm)
        y0_idx, y1_idx = self.auto_level_bracket(y_values, y_mm)
        x0 = x_values[x0_idx]
        x1 = x_values[x1_idx]
        y0 = y_values[y0_idx]
        y1 = y_values[y1_idx]
        x_ratio = 0.0 if x1 == x0 else (x_mm - x0) / (x1 - x0)
        y_ratio = 0.0 if y1 == y0 else (y_mm - y0) / (y1 - y0)

        z00 = z_values[y0_idx][x0_idx]
        z10 = z_values[y0_idx][x1_idx]
        z01 = z_values[y1_idx][x0_idx]
        z11 = z_values[y1_idx][x1_idx]
        z0 = self.linear_interpolate(z00, z10, x_ratio)
        z1 = self.linear_interpolate(z01, z11, x_ratio)
        return self.linear_interpolate(z0, z1, y_ratio)

    def auto_level_offset_at(self, context, x_value, y_value):
        height_map = context.get("autolevel_map")
        if not height_map:
            return 0.0

        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        # z_values are already normalized: reference point = 0.0, other points = delta.
        # surface_z is therefore the Z correction to apply (positive = surface is higher).
        surface_z = self.auto_level_surface_z(height_map, x_value * factor, y_value * factor)
        return surface_z / factor

    def replace_axis_word(self, line, axis, value):
        replacement = "%s%s" % (axis, self.format_gcode_number(value))
        pattern = r"(?<![A-Za-z])%s\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))" % axis
        if re.search(pattern, line, flags=re.IGNORECASE):
            return re.sub(pattern, replacement, line, count=1, flags=re.IGNORECASE)
        return "%s %s" % (line.rstrip(), replacement)

    def transform_stream_command(self, command, context):
        clean_line = self.clean_gcode_line(command)
        if not clean_line:
            return command

        upper_line = clean_line.upper()
        words = self.gcode_words(upper_line)
        g_codes = [int(float(value)) for value in re.findall(
            r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", upper_line
        )]
        if 20 in g_codes:
            context["units"] = "inch"
        if 21 in g_codes:
            context["units"] = "mm"
        if 90 in g_codes:
            context["absolute"] = True
        if 91 in g_codes:
            context["absolute"] = False

        if upper_line.startswith("$") or any(code in g_codes for code in [10, 53, 92]):
            return command

        x_anchor = float(context.get("x_anchor", 0.0))
        y_anchor = float(context.get("y_anchor", 0.0))
        absolute = bool(context.get("absolute", True))
        transformed = clean_line
        modified = False
        axis_values = {}

        if context.get("enabled"):
            for axis, anchor in [("X", x_anchor), ("Y", y_anchor)]:
                if axis in words:
                    new_value = words[axis] - anchor if absolute else words[axis]
                    axis_values[axis] = new_value
                    transformed = self.replace_axis_word(transformed, axis, new_value)
                    modified = True

        position = context.setdefault("position", {"X": 0.0, "Y": 0.0, "Z": 0.0})
        next_position = dict(position)
        for axis in "XYZ":
            if axis in words:
                value = axis_values.get(axis, words[axis])
                next_position[axis] = value if absolute else position[axis] + value

        motion = None
        for g_code in g_codes:
            if g_code in [0, 1, 2, 3]:
                motion = g_code
                context["current_motion"] = g_code
        if motion is None:
            motion = context.get("current_motion")

        has_xy = "X" in words or "Y" in words
        has_z = "Z" in words
        program_z = next_position.get("Z", position.get("Z", 0.0))
        if (
                context.get("autolevel_enabled") and
                motion in [1, 2, 3] and
                program_z <= 0.000001 and
                (has_xy or has_z)
        ):
            z_offset = self.auto_level_offset_at(context, next_position["X"], next_position["Y"])
            adjusted_z = program_z + z_offset
            transformed = self.replace_axis_word(transformed, "Z", adjusted_z)
            modified = True

        context["position"] = next_position
        return transformed if modified else command

    def transformed_gcode_lines(self, lines, apply_auto_level=True):
        context = self.stream_transform_context(lines)
        if apply_auto_level:
            self.attach_auto_level_context(context)
        return [self.transform_stream_command(line, context) for line in lines]

    def on_toggle_laser(self):
        if self.ui.macro_laser.isChecked():
            self.send_profile_command("laser_on")
            self.ui.macro_laser.setText("LASER OFF")
        else:
            self.send_profile_command("laser_off")
            self.ui.macro_laser.setText("LASER ON")

    def on_info_clicked(self):
        if isinstance(self.transport, HttpTransport):
            self.queue_command(self.current_profile().get("web_info", "[ESP800]"))
        else:
            self.send_profile_command("info")

    def on_sd_list(self):
        self.clear_sd_files_sig.emit()
        self.sd_collecting = False
        self.send_profile_command("sd_list")

    def on_run_sd(self):
        filename = self.ui.sd_combo.currentText().strip()
        if not filename:
            return
        command = self.current_profile().get("sd_run", "")
        if not command:
            self.append_console_sig.emit(_("SD run is not supported by selected profile."), "warn")
            return
        self.queue_commands(command.format(file=filename).splitlines())

    def receive_loop(self):
        while not self.stop_thread.is_set():
            try:
                if self.transport:
                    for line in self.transport.read_lines():
                        self.handle_line(line, echo=True)
            except Exception as e:
                if self.is_connected:
                    self.append_console_sig.emit(f"{_('Read error')}: {e}", "error")
                    self.disconnect()
                break

            if self.is_connected and self.status_poll_enabled:
                now = time.time()
                if isinstance(self.transport, HttpTransport):
                    interval = self.http_status_interval
                elif isinstance(self.transport, TcpTransport):
                    interval = self.tcp_status_interval
                else:
                    interval = self.status_interval
                if now - self.last_status_query >= interval:
                    self.poll_status()
                    self.last_status_query = now

            time.sleep(0.02)

    def poll_status(self):
        profile = self.current_profile()
        raw = profile.get("status_raw")
        command = profile.get("status", "")
        if not raw and not command:
            return

        try:
            with self.io_lock:
                if raw and not isinstance(self.transport, HttpTransport):
                    responses = self.transport.send_raw(raw)
                else:
                    responses = self.transport.send_line(command)
            for line in responses:
                self.handle_line(line, echo=False)
        except Exception:
            pass

    def handle_line(self, line, echo=True):
        line = (line or "").strip()
        if not line:
            return

        lower = line.lower()

        if lower == "ok" or lower.startswith("error"):
            self.last_controller_ack = lower
            self.ok_received.set()

        if self.parse_work_offset_report(line):
            if echo:
                self.append_console_sig.emit(line, "rx")
            return

        if self.parse_probe_result(line):
            if echo:
                self.append_console_sig.emit(line, "rx")
            return

        if line.startswith("<") and line.endswith(">"):
            self.parse_status(line)
            if echo and not self.hide_status_reports:
                self.append_console_sig.emit(line, "rx")
            return

        if self.parse_marlin_position(line):
            if echo:
                self.append_console_sig.emit(line, "rx")
            return

        if line.startswith("FW version") or "# FW target" in line or "[ESP800]" in line:
            self.parse_controller_info(line)

        self.parse_sd_listing(line)

        if echo:
            stream_type = "error" if lower.startswith("error") or "alarm" in lower else "rx"
            self.append_console_sig.emit(line, stream_type)

    def parse_probe_result(self, line):
        match = re.search(r"\[PRB:([^:\]]+):([01])\]", line or "", flags=re.IGNORECASE)
        if not match:
            return False

        coords = []
        for value in match.group(1).split(","):
            try:
                coords.append(float(value))
            except ValueError:
                coords.append(0.0)
        while len(coords) < 3:
            coords.append(0.0)

        self.last_probe_result = {
            "x": coords[0],
            "y": coords[1],
            "z": coords[2],
            "success": match.group(2) == "1",
        }
        self.probe_result_event.set()
        return True

    @staticmethod
    def parse_offset_coords(raw_coords, tlo=False):
        coords = []
        for value in str(raw_coords).split(","):
            try:
                coords.append(float(value))
            except ValueError:
                coords.append(0.0)

        if tlo and len(coords) == 1:
            return [0.0, 0.0, coords[0]]

        while len(coords) < 3:
            coords.append(0.0)
        return coords[:3]

    def parse_work_offset_report(self, line):
        match = re.match(
            r"\[(G54|G55|G56|G57|G58|G59(?:\.[123])?|G92|TLO):([^\]]+)\]",
            line or "",
            flags=re.IGNORECASE
        )
        if not match:
            return False

        label = match.group(1).upper()
        coords = self.parse_offset_coords(match.group(2), tlo=(label == "TLO"))
        if label.startswith("G5"):
            self.work_offsets[label] = coords
        elif label == "G92":
            self.g92_offset = coords
        elif label == "TLO":
            self.tool_length_offset = coords
        return True

    def combined_work_offset(self, wcs_label):
        wcs_offset = self.work_offsets.get(str(wcs_label or "G54").upper())
        if wcs_offset is None:
            wcs_offset = self.last_wco or [0.0, 0.0, 0.0]

        return [
            float(wcs_offset[idx]) + float(self.g92_offset[idx]) + float(self.tool_length_offset[idx])
            for idx in range(3)
        ]

    def probe_result_to_work_position(self, result, wcs_label, expected_xy=None):
        # GRBL [PRB:X,Y,Z:1] always reports in MACHINE coordinates.
        # For Z: we normalize against the reference point, so the absolute coordinate
        # system (machine vs work) does NOT matter as long as we are consistent.
        # We use raw machine Z for simplicity and reliability.
        # For XY: convert to work coordinates so probe grid aligns with G-code XY.
        machine = [
            float(result.get("x", 0.0) or 0.0),
            float(result.get("y", 0.0) or 0.0),
            float(result.get("z", 0.0) or 0.0),
        ]
        combined_offset = self.combined_work_offset(wcs_label)
        # XY in work coordinates (so they align with G-code positions)
        work_x = machine[0] - combined_offset[0]
        work_y = machine[1] - combined_offset[1]
        # Z: use raw machine coordinate — normalization (ref subtraction) handles the rest
        raw_z = machine[2]

        if self.probe_coordinate_mode is None:
            # Heuristic for logging only — does not affect the Z value used
            offset_size = math.sqrt(sum(v * v for v in combined_offset))
            detected_mode = "machine" if offset_size > 0.001 else "work"
            self.probe_coordinate_mode = detected_mode
            self.append_console_sig.emit(
                _("Probe Z using raw machine coordinates. Normalization will define Z=0."), "info"
            )

        return {
            "x": work_x,
            "y": work_y,
            "z": raw_z,
            "success": result.get("success", False),
        }


    def parse_status(self, line):
        parts = line[1:-1].split("|")
        if not parts:
            return

        data = {"state": parts[0]}
        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                data[key] = value
        self.update_status_sig.emit(data)

    @staticmethod
    def normalized_controller_state(state):
        state = str(state or "Idle").strip()
        if not state:
            return "Idle"
        base_state = state.split(":", 1)[0].strip()
        aliases = {
            "home": "Homing",
            "homing": "Homing",
            "idle": "Idle",
            "run": "Run",
            "jog": "Jog",
            "hold": "Hold",
            "alarm": "Alarm",
            "door": "Door",
            "check": "Check",
            "sleep": "Sleep",
        }
        return aliases.get(base_state.lower(), base_state)

    def parse_marlin_position(self, line):
        if not ("X:" in line and "Y:" in line and "Z:" in line):
            return False

        matches = dict(re.findall(r"([XYZ]):\s*(-?\d+(?:\.\d+)?)", line))
        if not matches:
            return False

        self.update_status_sig.emit({
            "state": "Idle",
            "WPos": "{},{},{}".format(matches.get("X", "0"), matches.get("Y", "0"), matches.get("Z", "0"))
        })
        return True

    def parse_sd_listing(self, line):
        lower = line.lower().strip()
        if lower == "begin file list":
            self.clear_sd_files_sig.emit()
            self.sd_collecting = True
            return
        if lower == "end file list":
            self.sd_collecting = False
            return

        if line.startswith("[FILE:"):
            filename = line.split("|", 1)[0].split(":", 1)[1].strip("]")
            self.sd_file_sig.emit(filename)
            return

        if self.sd_collecting and line and not lower.startswith(("ok", "echo:")):
            filename = line.split()[0]
            self.sd_file_sig.emit(filename)

    def parse_controller_info(self, text):
        info = {}
        cleaned = text.replace("\r", "\n")
        for chunk in cleaned.replace("\n", "#").split("#"):
            if ":" not in chunk:
                continue
            key, value = chunk.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key:
                info[key] = value

        if info:
            self.controller_info_sig.emit(info)

    def update_status_display(self, data):
        state = self.normalized_controller_state(data.get("state", "Idle"))
        self.ui.state_label.setText(state.upper())
        self.update_toolbar_connection_status(True, self.ui.connection_desc.text(), state=state)

        colors = {
            "Idle": "#5cb85c",
            "Run": "#337ab7",
            "Jog": "#31b0d5",
            "Hold": "#f0ad4e",
            "Homing": "#5bc0de",
            "Alarm": "#d9534f",
            "Door": "#d9534f",
            "Check": "#777777",
            "Sleep": "#777777",
        }
        self.ui.state_indicator.setStyleSheet(
            f"background-color: {colors.get(state, '#999999')}; border-radius: 6px;"
        )

        if "WCO" in data:
            try:
                self.last_wco = [float(x) for x in (data["WCO"].split(",") + ["0", "0", "0"])[:3]]
            except ValueError:
                pass

        if "WPos" in data:
            coords = (data["WPos"].split(",") + ["0.000", "0.000", "0.000"])[:3]
            self.ui.x_val.setText(coords[0])
            self.ui.y_val.setText(coords[1])
            self.ui.z_val.setText(coords[2])
        elif "MPos" in data and "WCO" in data:
            # Calculate WPos from MPos and WCO if WPos is not directly provided
            m_coords = [float(x) for x in (data["MPos"].split(",") + ["0", "0", "0"])[:3]]
            wco = self.last_wco or [0.0, 0.0, 0.0]
            self.ui.x_val.setText(f"{m_coords[0] - wco[0]:.3f}")
            self.ui.y_val.setText(f"{m_coords[1] - wco[1]:.3f}")
            self.ui.z_val.setText(f"{m_coords[2] - wco[2]:.3f}")

        if "MPos" in data:
            coords = (data["MPos"].split(",") + ["0.000", "0.000", "0.000"])[:3]
            self.ui.mx_val.setText(coords[0])
            self.ui.my_val.setText(coords[1])
            self.ui.mz_val.setText(coords[2])

        pins = data.get("Pn", "")
        active_axes = "".join(axis for axis in "XYZ" if axis in str(pins).upper())
        self.ui.set_limit_pins(active_axes)
        if active_axes != self.active_limit_pins:
            self.active_limit_pins = active_axes
            if active_axes:
                self.append_console_sig.emit(
                    _("Active limit input(s): %s") % ", ".join(active_axes),
                    "warn"
                )

        if "FS" in data:
            values = (data["FS"].split(",") + ["0", "0"])[:2]
            self.ui.feed_value.setText(values[0])
            self.ui.spindle_value.setText(values[1])
            try:
                feed = float(values[0])
            except ValueError:
                feed = 0.0
            try:
                spindle = float(values[1])
            except ValueError:
                spindle = 0.0
            self.ui.update_dashboard_gauges(feed, spindle)

        if "Ov" in data:
            values = (data["Ov"].split(",") + ["100", "100", "100"])[:3]
            self.ui.feed_override_value.setText(values[0] + "%")
            self.ui.rapid_override_value.setText(values[1] + "%")
            self.ui.spindle_override_value.setText(values[2] + "%")

    def on_stream_start(self):
        if not self.is_connected:
            self.append_console_sig.emit(_("Controller is not connected."), "error")
            return

        if self.is_streaming:
            return

        if not self.job_queue:
            self.on_queue_add()
            if not self.job_queue:
                return

        if not self.refresh_queued_gcode():
            return

        for item in self.job_queue:
            item["status"] = _("Queued")
        self.current_queue_idx = -1
        self.current_line_idx = 0
        self.is_streaming = True
        self.streaming_paused = False
        self.ui.pause_btn.setText("PAUSE")
        self.queue_update_sig.emit()
        threading.Thread(target=self.stream_worker, daemon=True).start()

    def on_stream_pause(self):
        if not self.is_streaming:
            return
        self.streaming_paused = not self.streaming_paused
        if self.streaming_paused:
            self.send_profile_command("hold")
            self.ui.pause_btn.setText("RESUME")
        else:
            self.send_profile_command("resume")
            self.ui.pause_btn.setText("PAUSE")

    def on_stream_stop(self):
        self.is_streaming = False
        self.streaming_paused = False
        self.ui.pause_btn.setText("PAUSE")
        if 0 <= self.current_queue_idx < len(self.job_queue):
            self.job_queue[self.current_queue_idx]["status"] = _("Stopped")
            self.queue_update_sig.emit()

    def wait_for_stream_ack(self, command, timeout=None, warn_after=5.0):
        started = time.time()
        warned = False

        while self.is_streaming and self.is_connected:
            if self.ok_received.wait(timeout=0.1):
                ack = getattr(self, "last_controller_ack", "")
                if str(ack).lower().startswith("error"):
                    self.append_console_sig.emit(
                        "%s: %s" % (_("Controller rejected command"), command),
                        "error"
                    )
                    return False
                return True

            elapsed = time.time() - started
            if warn_after is not None and not warned and elapsed >= warn_after:
                self.append_console_sig.emit(
                    "%s: %s" % (_("Waiting for controller response before sending more G-code"), command),
                    "warn"
                )
                warned = True

            if timeout is not None and elapsed >= timeout:
                self.append_console_sig.emit(
                    "%s: %s" % (_("Controller response timeout; streaming stopped"), command),
                    "error"
                )
                return False

        return False

    def stream_worker(self):
        total = sum(len(item.get("lines", [])) for item in self.job_queue)
        sent = 0
        stream_aborted = False
        for job_idx, item in enumerate(self.job_queue):
            if not self.is_streaming:
                break

            self.current_queue_idx = job_idx
            item["status"] = _("Running")
            self.queue_update_sig.emit()

            lines = item.get("lines", [])
            transform_context = self.stream_transform_context(lines)
            self.attach_auto_level_context(transform_context)
            stream_lines = [
                self.transform_stream_command(command, transform_context)
                for command in lines
            ]
            if transform_context.get("enabled"):
                mode_labels = {
                    "top_left": _("Back-Left"),
                    "bottom_left": _("Bottom-Left"),
                    "center": _("Center"),
                }
                mode_label = mode_labels.get(transform_context.get("mode"), _("Job Origin"))
                placement_label = self.job_placement_label(transform_context.get("placement"))
                self.append_console_sig.emit(
                    _("Zeroed XY is mapped to CNCJob %s; placement is %s.") % (mode_label, placement_label),
                    "info"
                )
                target_bounds = transform_context.get("target_bounds")
                if target_bounds:
                    self.append_console_sig.emit(
                        _("Mapped XY bounds: X%.3f..%.3f  Y%.3f..%.3f") % (
                            target_bounds["X"][0], target_bounds["X"][1],
                            target_bounds["Y"][0], target_bounds["Y"][1],
                        ),
                        "info"
                    )
            elif (
                    transform_context.get("mode") == "absolute" and
                    (float(transform_context.get("margin_x", 0.0) or 0.0) > 0 or
                     float(transform_context.get("margin_y", 0.0) or 0.0) > 0)
            ):
                self.append_console_sig.emit(
                    _("Job margins are visible in preview, but are not applied while Origin is 'Use G-code Absolute XY'."),
                    "warn"
                )
            if transform_context.get("autolevel_enabled"):
                height_map = transform_context.get("autolevel_map", {})
                z_values = self.auto_level_map_z_values(height_map)
                mode_label = height_map.get("probe_coordinate_mode") or _("unknown")
                if z_values:
                    self.append_console_sig.emit(
                        _("Auto level map is active: %d points. Z range %.4f..%.4f mm; probe mode: %s.") % (
                            int(height_map.get("point_count", 0) or 0),
                            min(z_values),
                            max(z_values),
                            mode_label
                        ),
                        "info"
                    )
                else:
                    self.append_console_sig.emit(
                        _("Auto level map is active: %d points.") % int(height_map.get("point_count", 0) or 0),
                        "info"
                    )

            wcs_label, _p_num = self.selected_work_offset()
            self.ok_received.clear()
            self.last_controller_ack = ""
            self.send_command(wcs_label, log=True)
            if not self.wait_for_stream_ack(wcs_label, timeout=15.0):
                item["status"] = _("Stopped")
                self.queue_update_sig.emit()
                stream_aborted = True
                break

            for line_idx, sent_command in enumerate(stream_lines):
                if not self.is_streaming:
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    break

                while self.streaming_paused and self.is_streaming:
                    time.sleep(0.1)

                self.current_line_idx = line_idx
                self.ok_received.clear()
                if not str(sent_command).strip():
                    continue
                self.last_controller_ack = ""
                self.send_command(sent_command, log=True)
                if not self.wait_for_stream_ack(sent_command, timeout=None, warn_after=None):
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    stream_aborted = True
                    break
                sent += 1
                self.update_progress_sig.emit((sent / total * 100.0) if total else 0.0, sent_command)

            if stream_aborted:
                break

            if self.is_streaming:
                item["status"] = _("Done")
                self.queue_update_sig.emit()

        completed = self.is_streaming and not stream_aborted
        self.is_streaming = False
        self.streaming_paused = False
        self.current_queue_idx = -1
        self.update_progress_sig.emit(100.0 if completed and total else 0.0, _("Done") if completed else _("Stopped"))
        self.queue_update_sig.emit()

    def update_progress_ui(self, percent, _text):
        self.ui.progress.setValue(int(percent))
        if not self.is_streaming:
            self.ui.pause_btn.setText("PAUSE")

    def http_transport(self):
        if isinstance(self.transport, HttpTransport):
            return self.transport
        return None

    def on_refresh_files(self):
        if not self.is_connected:
            return

        transport = self.http_transport()
        if transport:
            endpoint = self.ui.files_fs_combo.currentData()
            path = self.ui.current_path
            self.busy_sig.emit(True, _("Refreshing files..."))
            threading.Thread(target=self._refresh_files_worker, args=(transport, endpoint, path), daemon=True).start()
        else:
            # Fallback to Serial/TCP SD List command
            self.on_sd_list()

    def _refresh_files_worker(self, transport, endpoint, path):
        try:
            data = transport.list_files(endpoint, path)
            if "path" not in data:
                data["path"] = path
            self.files_update_sig.emit(data)
        except Exception as e:
            self.append_console_sig.emit(f"{_('File list failed')}: {e}", "error")
        finally:
            self.busy_sig.emit(False, "")

    def on_upload_files(self):
        transport = self.http_transport()
        if not transport:
            return

        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            _("Upload files"),
            "",
            _("All Files") + " (*)"
        )
        if not files:
            return

        endpoint = self.ui.files_fs_combo.currentData()
        path = self.ui.current_path
        self.busy_sig.emit(True, _("Uploading files..."))
        threading.Thread(target=self._upload_files_worker, args=(transport, endpoint, path, files), daemon=True).start()

    def _upload_files_worker(self, transport, endpoint, path, files):
        try:
            data = transport.upload_files(endpoint, path, files)
            self.files_update_sig.emit(data)
            self.append_console_sig.emit(_("Upload finished."), "info")
        except Exception as e:
            self.append_console_sig.emit(f"{_('Upload failed')}: {e}", "error")
        finally:
            self.busy_sig.emit(False, "")

    def on_create_dir(self):
        transport = self.http_transport()
        if not transport:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, _("Create directory"), _("Directory name:"))
        if not ok or not name.strip():
            return
        self._file_action("createdir", name.strip())

    def on_delete_file(self):
        item = self.ui.selected_file_item()
        if not item:
            return

        action = "deletedir" if item.get("is_dir") else "delete"
        answer = QtWidgets.QMessageBox.question(
            self,
            _("Confirm deletion"),
            "%s: %s" % (_("Delete"), item["name"])
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self._file_action(action, item["name"])

    def _file_action(self, action, filename):
        transport = self.http_transport()
        if not transport:
            return
        endpoint = self.ui.files_fs_combo.currentData()
        path = self.ui.current_path
        self.busy_sig.emit(True, _("Updating files..."))
        threading.Thread(
            target=self._file_action_worker,
            args=(transport, endpoint, path, action, filename),
            daemon=True
        ).start()

    def _file_action_worker(self, transport, endpoint, path, action, filename):
        try:
            data = transport.list_files(endpoint, path, action=action, filename=filename)
            self.files_update_sig.emit(data)
        except Exception as e:
            self.append_console_sig.emit(f"{_('File action failed')}: {e}", "error")
        finally:
            self.busy_sig.emit(False, "")

    def on_files_up(self):
        path = self.ui.current_path.rstrip("/")
        if not path:
            self.ui.current_path = "/"
        else:
            parent = path.rsplit("/", 1)[0]
            self.ui.current_path = (parent + "/") if parent else "/"
        self.on_refresh_files()

    def on_files_root(self):
        self.ui.current_path = "/"
        self.on_refresh_files()

    def on_filesystem_changed(self):
        self.ui.current_path = "/"
        if self.is_connected and isinstance(self.transport, HttpTransport):
            self.on_refresh_files()

    def on_file_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data.get("is_dir"):
            self.ui.current_path = self.ui.current_path.rstrip("/") + "/" + data["name"] + "/"
            self.on_refresh_files()
