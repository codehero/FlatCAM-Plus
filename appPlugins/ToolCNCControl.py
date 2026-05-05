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
        self.last_status_query = 0
        self.status_interval = 0.1
        self.sd_collecting = False
        self.active_profile_key = "fluidnc"
        self.status_poll_enabled = True
        self.hide_status_reports = True

        self.is_streaming = False
        self.streaming_paused = False
        self.current_line_idx = 0
        self.gcode_lines = []
        self.job_queue = []
        self.current_queue_idx = -1

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
            if self.app.ui.plot_tab_area.tabText(i) == _("CNC Settings"):
                self.app.ui.plot_tab_area.setCurrentIndex(i)
                tab_exists = True
                break

        if not tab_exists:
            self.scroll_area = VerticalScrollArea()
            self.scroll_area.setWidget(self)
            self.scroll_area.setWidgetResizable(True)
            self.app.ui.plot_tab_area.addTab(self.scroll_area, _("CNC Settings"))
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

        self.ui.home_btn.clicked.connect(lambda: self.send_profile_command("home"))
        self.ui.unlock_btn.clicked.connect(lambda: self.send_profile_command("unlock"))
        self.ui.reset_btn.clicked.connect(lambda: self.send_profile_command("reset"))
        self.ui.estop_btn.clicked.connect(lambda: self.send_profile_command("hold"))
        self.ui.resume_btn.clicked.connect(lambda: self.send_profile_command("resume"))
        self.ui.info_btn.clicked.connect(self.on_info_clicked)
        self.ui.cfg_dump.clicked.connect(lambda: self.send_profile_command("config"))

        self.ui.zero_x.clicked.connect(lambda: self.send_zero("X"))
        self.ui.zero_y.clicked.connect(lambda: self.send_zero("Y"))
        self.ui.zero_z.clicked.connect(lambda: self.send_zero("Z"))
        self.ui.zero_all.clicked.connect(lambda: self.send_profile_command("zero_all"))

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

        self.ui.macro_probe.clicked.connect(self.on_probe_z)
        self.ui.macro_laser.clicked.connect(self.on_toggle_laser)
        self.ui.probe_z_btn.clicked.connect(self.on_probe_z)
        self.ui.probe_set_z_btn.clicked.connect(self.on_probe_and_set_z)
        self.ui.set_xy_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("X", "Y")))
        self.ui.set_z_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("Z",)))
        self.ui.set_xyz_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("X", "Y", "Z")))
        self.ui.apply_wcs_btn.clicked.connect(self.on_apply_work_coordinate_system)

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
            return item.get("name", _("Queued Job")), list(item.get("lines", []))

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
        try:
            result = self.analyze_gcode(name, lines)
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
                "action": action,
                "updated_at": time.strftime("%H:%M:%S"),
            }
            self.preview_update_sig.emit(result)
            if announce:
                self.emit_preview_message(result["preview"], "error")
            return

        result["action"] = action
        result["updated_at"] = time.strftime("%H:%M:%S")
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
            for key, value in re.findall(r"([A-Za-z])\s*([+-]?\d+(?:\.\d+)?)", line)
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
            g_codes = [int(float(value)) for value in re.findall(r"\bG\s*([+-]?\d+(?:\.\d+)?)", upper_line)]
            m_codes = [int(float(value)) for value in re.findall(r"\bM\s*([+-]?\d+(?:\.\d+)?)", upper_line)]

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

    def on_toolbar_connection_clicked(self):
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

    def on_manage_machine_profiles(self):
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

    def send_zero(self, axis):
        command = self.current_profile().get("zero_axis", "").format(axis=axis)
        self.queue_command(command)

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
        _wcs_label, p_num = self.selected_work_offset()
        axis_values = " ".join(f"{axis}0" for axis in axes)
        self.queue_command(f"G10 L20 P{p_num} {axis_values}")

    def on_apply_work_coordinate_system(self):
        wcs_label, _p_num = self.selected_work_offset()
        self.queue_command(wcs_label)

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
                if now - self.last_status_query >= self.status_interval:
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
            self.ok_received.set()

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
        state = data.get("state", "Idle")
        self.ui.state_label.setText(state.upper())
        self.update_toolbar_connection_status(True, self.ui.connection_desc.text(), state=state)

        colors = {
            "Idle": "#5cb85c",
            "Run": "#337ab7",
            "Jog": "#31b0d5",
            "Hold": "#f0ad4e",
            "Home": "#5bc0de",
            "Alarm": "#d9534f",
            "Door": "#d9534f",
            "Check": "#777777",
            "Sleep": "#777777",
        }
        self.ui.state_indicator.setStyleSheet(
            f"background-color: {colors.get(state, '#999999')}; border-radius: 6px;"
        )

        if "WPos" in data:
            coords = (data["WPos"].split(",") + ["0.000", "0.000", "0.000"])[:3]
            self.ui.x_val.setText(coords[0])
            self.ui.y_val.setText(coords[1])
            self.ui.z_val.setText(coords[2])
        elif "MPos" in data and "WCO" in data:
            # Calculate WPos from MPos and WCO if WPos is not directly provided
            m_coords = [float(x) for x in (data["MPos"].split(",") + ["0", "0", "0"])[:3]]
            wco = [float(x) for x in (data["WCO"].split(",") + ["0", "0", "0"])[:3]]
            self.ui.x_val.setText(f"{m_coords[0] - wco[0]:.3f}")
            self.ui.y_val.setText(f"{m_coords[1] - wco[1]:.3f}")
            self.ui.z_val.setText(f"{m_coords[2] - wco[2]:.3f}")

        if "MPos" in data:
            coords = (data["MPos"].split(",") + ["0.000", "0.000", "0.000"])[:3]
            self.ui.mx_val.setText(coords[0])
            self.ui.my_val.setText(coords[1])
            self.ui.mz_val.setText(coords[2])

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

    def stream_worker(self):
        total = sum(len(item.get("lines", [])) for item in self.job_queue)
        sent = 0
        for job_idx, item in enumerate(self.job_queue):
            if not self.is_streaming:
                break

            self.current_queue_idx = job_idx
            item["status"] = _("Running")
            self.queue_update_sig.emit()

            lines = item.get("lines", [])
            for line_idx, command in enumerate(lines):
                if not self.is_streaming:
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    break

                while self.streaming_paused and self.is_streaming:
                    time.sleep(0.1)

                self.current_line_idx = line_idx
                self.ok_received.clear()
                self.send_command(command, log=True)
                self.ok_received.wait(timeout=5.0)
                sent += 1
                self.update_progress_sig.emit((sent / total * 100.0) if total else 0.0, command)

            if self.is_streaming:
                item["status"] = _("Done")
                self.queue_update_sig.emit()

        completed = self.is_streaming
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
