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
from appGUI.GUIElements import FCFileSaveDialog, VerticalScrollArea
from appPlugins.cnc_control.dialogs import MachineProfileDialog, MacroDialog
from appPlugins.cnc_control.machine_profiles import normalize_machine_profile, normalize_machine_profiles
from appPlugins.cnc_control.profiles import CNC_PROFILES
from appPlugins.cnc_control.transports import HttpTransport, SerialTransport, TcpTransport
from appPlugins.cnc_control.ui import CNCControlUI, CNCPreviewModal

import builtins
import gettext
import json
import logging
import math
import os
import queue
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
    jog_controls_update_sig = pyqtSignal()

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
        self.stream_ack_queue = queue.Queue()
        self.stream_buffer_length = 127
        self.last_status_query = 0
        self.status_interval = 0.25
        self.tcp_status_interval = 0.5
        self.http_status_interval = 1.0
        self.sd_collecting = False
        self.active_profile_key = "fluidnc"
        self.status_poll_enabled = True
        self.hide_status_reports = True
        self.active_limit_pins = ""
        self.controller_state = "Offline"
        self.jog_in_flight = False
        self.jog_motion_seen = False
        self.jog_lock = threading.Lock()
        self.last_jog_warning = 0.0

        self.is_streaming = False
        self.stream_mode = "job"
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
        self.live_offset_x = 0.0
        self.live_offset_y = 0.0
        self.live_rotation = 0.0
        self.live_placement_active = False
        self.live_edit_enabled = False
        self.live_placement_history = {}
        self.auto_connect_attempts = 2
        self.auto_connect_retry_delay = 2.0

        self.ui = CNCControlUI(layout=self.layout, app=self.app)
        self.pluginName = self.ui.pluginName
        self.load_live_placement_history()
        self.load_connection_settings()
        self.active_profile_key = self.ui.profile_combo.currentData() or "fluidnc"
        self.load_macros()
        self.load_machine_profiles()
        self.connect_signals_at_init()
        self.ui.set_connected(False)
        self.register_toolbar_connection_handler()
        self.update_toolbar_connection_status(False, "")
        self.connect_project_workspace_signals()
        QtCore.QTimer.singleShot(500, self.maybe_auto_connect_on_startup)

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
        self.init_job_size()
        self.update_tool_list()
        self.load_macros()
        self.load_machine_profiles()

    def init_job_size(self):
        bounds = self.project_workspace_bounds("mm")
        if bounds:
            width = bounds[1] - bounds[0]
            height = bounds[3] - bounds[2]

            def set_silent(widget, value):
                widget.blockSignals(True)
                try:
                    widget.set_value(value)
                finally:
                    widget.blockSignals(False)

            if hasattr(self.ui, 'job_size_x'):
                set_silent(self.ui.job_size_x, width)
            if hasattr(self.ui, 'job_size_y'):
                set_silent(self.ui.job_size_y, height)

    def connect_project_workspace_signals(self):
        try:
            self.app.file_opened.connect(self.on_project_workspace_changed)
        except Exception:
            pass
        try:
            self.app.new_project_signal.connect(self.on_project_workspace_changed)
        except Exception:
            pass

    def on_project_workspace_changed(self, kind=None, *_args):
        if kind is not None and str(kind).lower() != "project":
            return
        self.init_job_size()
        self.invalidate_auto_level_map(_("Project workspace changed; probe the height map again."))
        if hasattr(self.ui, "gcode_preview_text"):
            self.on_preview_refresh(refresh_jobs=False)

    def on_job_setup_changed(self, *_args):
        self.invalidate_auto_level_map(_("Job setup changed; probe the height map again."))
        self.on_preview_refresh(refresh_jobs=False)

    def connect_signals_at_init(self):
        self.ui.connect_btn.clicked.connect(self.on_connect_clicked)
        self.ui.test_connection_btn.clicked.connect(self.on_test_connection_clicked)
        self.ui.disconnect_btn.clicked.connect(self.disconnect)
        self.ui.com_refresh.clicked.connect(self.on_refresh_ports)
        self.ui.connection_mode_combo.currentIndexChanged.connect(self.ui.on_connection_mode_changed)
        self.ui.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        if hasattr(self.ui, "auto_connect_cb"):
            self.ui.auto_connect_cb.toggled.connect(self.on_auto_connect_changed)
        self.connect_connection_setting_signals()
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
        if hasattr(self.ui, "set_xy_zero_btn"):
            self.ui.set_xy_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("X", "Y")))
        if hasattr(self.ui, "set_z_zero_btn"):
            self.ui.set_z_zero_btn.clicked.connect(lambda: self.on_set_work_offset(("Z",)))
        if hasattr(self.ui, "set_xyz_zero_btn"):
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
        if hasattr(self.ui, "preview_export_btn"):
            self.ui.preview_export_btn.clicked.connect(self.on_export_preview_gcode)
        self.ui.live_placement_btn.clicked.connect(self.on_toggle_live_placement)
        if hasattr(self.ui, "simulate_xy_btn"):
            self.ui.simulate_xy_btn.clicked.connect(self.on_simulate_xy_clicked)
        if hasattr(self.ui, "zcut_override_cb"):
            self.ui.zcut_override_cb.toggled.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        if hasattr(self.ui, "zcut_override_value"):
            self.ui.zcut_override_value.valueChanged.connect(lambda *_args: self.on_preview_refresh(refresh_jobs=False))
        self.ui.gcode_job_canvas.placement_changed.connect(self.on_live_placement_changed)
        self.ui.object_combo.currentIndexChanged.connect(
            self.on_job_setup_changed
        )
        if hasattr(self.ui, "job_origin_combo"):
            self.ui.job_origin_combo.currentIndexChanged.connect(
                self.on_job_setup_changed
            )
        if hasattr(self.ui, "job_placement_combo"):
            self.ui.job_placement_combo.currentIndexChanged.connect(
                self.on_job_setup_changed
            )
        if hasattr(self.ui, "job_size_x"):
            self.ui.job_size_x.valueChanged.connect(self.on_job_setup_changed)
        if hasattr(self.ui, "job_size_y"):
            self.ui.job_size_y.valueChanged.connect(self.on_job_setup_changed)
        if hasattr(self.ui, "job_margin_x"):
            self.ui.job_margin_x.valueChanged.connect(self.on_job_setup_changed)
        if hasattr(self.ui, "job_margin_y"):
            self.ui.job_margin_y.valueChanged.connect(self.on_job_setup_changed)
        if hasattr(self.ui, "fit_job_size_btn"):
            self.ui.fit_job_size_btn.clicked.connect(self.on_fit_job_size_clicked)
        self.ui.autolevel_fit_btn.clicked.connect(self.on_auto_level_fit_area)
        self.ui.autolevel_probe_btn.clicked.connect(self.on_auto_level_probe_clicked)
        self.ui.autolevel_stop_btn.clicked.connect(self.on_auto_level_stop)
        self.ui.autolevel_clear_btn.clicked.connect(self.on_auto_level_clear)
        self.ui.autolevel_3d_btn.clicked.connect(self.on_auto_level_3d_clicked)
        for widget_name in ("autolevel_x_min", "autolevel_x_max", "autolevel_y_min", "autolevel_y_max",
                            "autolevel_rows", "autolevel_columns"):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.valueChanged.connect(
                    lambda *_args: self.invalidate_auto_level_map(
                        _("Auto level area changed; probe the height map again.")
                    )
                )
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
        self.ui.macro_list.customContextMenuRequested.connect(self.on_macro_context_menu)
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
        self.jog_controls_update_sig.connect(self.update_jog_controls_enabled)

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

    @staticmethod
    def with_start_code(source, start_code):
        source_text = ToolCNCControl.gcode_text_from_source(source)
        start_text = ToolCNCControl.gcode_text_from_source(start_code)
        if not source_text.strip() or not start_text.strip():
            return source_text

        if source_text.lstrip().startswith(start_text.strip()):
            return source_text

        source_has_units = re.search(r"(?im)^\s*G\s*(20|21)\b", source_text)
        source_has_positioning = re.search(r"(?im)^\s*G\s*(90|91)\b", source_text)
        start_has_units = re.search(r"(?im)^\s*G\s*(20|21)\b", start_text)
        start_has_positioning = re.search(r"(?im)^\s*G\s*(90|91)\b", start_text)

        if (start_has_units and not source_has_units) or (start_has_positioning and not source_has_positioning):
            return start_text.rstrip() + "\n" + source_text.lstrip()

        return source_text

    def cncjob_gcode_text(self, obj):
        source = self.gcode_text_from_source(getattr(obj, "source_file", ""))
        if source.strip():
            return self.with_start_code(source, getattr(obj, "gc_start", ""))

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

    def cncjob_object_xy_bounds(self, name):
        obj = self.app.collection.get_by_name(name)
        if obj is None:
            return None

        options = getattr(obj, "obj_options", {}) or {}
        try:
            bounds = [
                float(options["xmin"]),
                float(options["xmax"]),
                float(options["ymin"]),
                float(options["ymax"]),
            ]
        except (KeyError, TypeError, ValueError):
            try:
                xmin, ymin, xmax, ymax = obj.bounds()
                bounds = [float(xmin), float(xmax), float(ymin), float(ymax)]
            except Exception:
                return None

        if not all(math.isfinite(value) for value in bounds):
            return None
        if math.isclose(bounds[0], bounds[1]) or math.isclose(bounds[2], bounds[3]):
            return None
        return bounds

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

    @staticmethod
    def live_history_key(name):
        return str(name or "__default__").strip() or "__default__"

    @staticmethod
    def normalized_live_history_record(record):
        if not isinstance(record, dict):
            return None
        try:
            return {
                "dx": float(record.get("dx", 0.0)),
                "dy": float(record.get("dy", 0.0)),
                "rotation": float(record.get("rotation", 0.0)),
                "saved_at": str(record.get("saved_at", "")),
            }
        except (TypeError, ValueError):
            return None

    def load_live_placement_history(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        raw = settings.value("cnc_live_placement_history", "")
        history = {}
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
            if isinstance(data, dict):
                for key, items in data.items():
                    if not isinstance(items, list):
                        continue
                    records = []
                    for item in items:
                        record = self.normalized_live_history_record(item)
                        if record:
                            records.append(record)
                        if len(records) >= 5:
                            break
                    if records:
                        history[str(key)] = records
        self.live_placement_history = history

    def save_live_placement_history(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        settings.setValue("cnc_live_placement_history", json.dumps(self.live_placement_history))
        settings.sync()

    @staticmethod
    def live_history_record_matches(record, dx, dy, rotation):
        try:
            return (
                abs(float(record.get("dx", 0.0)) - float(dx or 0.0)) <= 0.01 and
                abs(float(record.get("dy", 0.0)) - float(dy or 0.0)) <= 0.01 and
                abs(float(record.get("rotation", 0.0)) - float(rotation or 0.0)) <= 0.01
            )
        except (TypeError, ValueError):
            return False

    def live_history_for_job(self, name):
        key = self.live_history_key(name)
        return list(self.live_placement_history.get(key, []))[:3]

    def remember_live_placement(self, name, dx, dy, rotation):
        key = self.live_history_key(name)
        record = {
            "dx": float(dx or 0.0),
            "dy": float(dy or 0.0),
            "rotation": float(rotation or 0.0),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        records = [
            item for item in self.live_placement_history.get(key, [])
            if not self.live_history_record_matches(item, record["dx"], record["dy"], record["rotation"])
        ]
        records.insert(0, record)
        self.live_placement_history[key] = records[:5]
        self.save_live_placement_history()

    def on_toggle_live_placement(self, *_args):
        # Open the large modal for placement
        if not hasattr(self, 'preview_modal'):
            self.preview_modal = CNCPreviewModal(self.app.ui)

        # Prepare modal canvas
        self.preview_modal.canvas.edit_mode = True
        self.preview_modal.set_placement(self.live_offset_x, self.live_offset_y, self.live_rotation)

        # Get preview data with workspace bounds
        name, lines = self.selected_preview_job()
        if not lines:
            self.emit_preview_message(_("Select a CNCJob first."), "warn")
            return

        old_offset_x = self.live_offset_x
        old_offset_y = self.live_offset_y
        old_rotation = self.live_rotation
        old_live_active = self.live_placement_active
        old_live_edit = self.live_edit_enabled
        self.live_edit_enabled = True
        try:
            # The modal canvas applies the live transform visually while dragging.
            # Keep the generated G-code preview at its base placement to avoid double-offsetting.
            preview_lines = self.transformed_gcode_lines(lines, name=name, apply_live_placement=False)
            canvas_preview = self.build_job_canvas_preview(name, lines, preview_lines, apply_live_placement=False)
        finally:
            self.live_edit_enabled = old_live_edit

        self.preview_modal.set_preview(canvas_preview)
        self.preview_modal.set_placement_history(self.live_history_for_job(name))

        # Connect signals
        try:
            self.preview_modal.placement_changed.disconnect(self.on_live_placement_changed)
        except:
            pass
        self.preview_modal.placement_changed.connect(self.on_live_placement_changed)

        # Execute modal
        if self.preview_modal.exec():
            # Save clicked
            placement_changed = (
                abs(float(self.live_offset_x or 0.0) - float(old_offset_x or 0.0)) > 1e-6 or
                abs(float(self.live_offset_y or 0.0) - float(old_offset_y or 0.0)) > 1e-6 or
                abs(float(self.live_rotation or 0.0) - float(old_rotation or 0.0)) > 1e-6
            )
            self.live_placement_active = self.live_placement_has_transform()
            if placement_changed:
                self.remember_live_placement(name, self.live_offset_x, self.live_offset_y, self.live_rotation)
            self.emit_preview_message(
                _("Live Placement saved: X%.3f Y%.3f R%.2f deg") % (
                    self.live_offset_x, self.live_offset_y, self.live_rotation
                ),
                "success"
            )
            # Refresh inline preview
            self.preview_modal.canvas.edit_mode = False
            self.on_preview_refresh(refresh_jobs=False)
            if hasattr(self.ui, "autolevel_x_min"):
                if placement_changed:
                    self.invalidate_auto_level_map(_("Live Placement changed; probe the height map again."))
                self.on_auto_level_fit_area()
        else:
            self.live_offset_x = old_offset_x
            self.live_offset_y = old_offset_y
            self.live_rotation = old_rotation
            self.live_placement_active = old_live_active
            self.preview_modal.set_placement(old_offset_x, old_offset_y, old_rotation)
            self.preview_modal.canvas.edit_mode = False

    def on_live_placement_changed(self, dx, dy, rotation):
        self.live_offset_x = dx
        self.live_offset_y = dy
        self.live_rotation = rotation

    def on_preview_clicked(self, *_args):
        self.on_preview_refresh(refresh_jobs=True, action=_("Preview"), announce=True)

    def on_verify_clicked(self, *_args):
        self.on_preview_refresh(refresh_jobs=True, action=_("Verify"), announce=True)

    @staticmethod
    def safe_gcode_filename(name):
        cleaned = re.sub(r"[^\w.\-]+", "_", str(name or "mapped_preview_gcode"), flags=re.UNICODE)
        cleaned = cleaned.strip("._")
        return cleaned or "mapped_preview_gcode"

    def preview_export_gcode_lines(self):
        name, lines = self.selected_preview_job()
        if not lines:
            return name, []

        transformed_lines = self.transformed_gcode_lines(lines, name=name)
        return name, self.split_generated_gcode_lines(transformed_lines)

    def on_export_preview_gcode(self, *_args):
        name, export_lines = self.preview_export_gcode_lines()
        if not export_lines:
            self.emit_preview_message(_("Select a CNCJob first."), "warn")
            return

        default_name = "%s_mapped" % self.safe_gcode_filename(name)
        try:
            directory = self.app.get_last_save_folder() + "/" + default_name
        except Exception:
            directory = default_name

        filename, _filter = FCFileSaveDialog.get_saved_filename(
            caption=_("Export Preview G-code ..."),
            directory=directory,
            ext_filter=self.app.options.get("cncjob_save_filters", "G-Code Files .nc (*.nc);;All Files (*.*)")
        )
        filename = str(filename or "")
        if not filename:
            self.emit_preview_message(_("Export cancelled."), "warn")
            return

        try:
            force_windows_line_endings = self.app.options.get('cncjob_line_ending', False)
            newline = '\r\n' if force_windows_line_endings and sys.platform != 'win32' else None
            with open(filename, 'w', newline=newline) as gcode_file:
                gcode_file.write("\n".join(export_lines).rstrip() + "\n")
        except FileNotFoundError:
            self.emit_preview_message(_("No such file or directory"), "error")
            return
        except PermissionError:
            self.emit_preview_message(
                _("Permission denied, saving not possible.\nMost likely another app is holding the file open."),
                "error"
            )
            return
        except OSError as err:
            self.emit_preview_message("%s: %s" % (_("Export failed"), err), "error")
            return

        if self.app.options.get("global_open_style") is False:
            self.app.file_opened.emit("gcode", filename)
        self.app.file_saved.emit("gcode", filename)
        self.on_preview_refresh(refresh_jobs=False, action=_("Export"), announce=False)
        self.emit_preview_message(
            _("Mapped preview G-code exported: %s") % filename,
            "info"
        )

    def on_simulate_xy_clicked(self, *_args):
        if not self.is_connected or not self.transport:
            self.emit_preview_message(_("Controller is not connected."), "error")
            return
        if self.is_streaming:
            self.emit_preview_message(_("A job is already streaming."), "warn")
            return
        if self.is_auto_leveling:
            self.emit_preview_message(_("Simulation is disabled while auto-level probing is running."), "warn")
            return

        name, lines = self.selected_preview_job()
        if not lines:
            self.emit_preview_message(_("Select a CNCJob first."), "warn")
            return

        try:
            simulation_lines = self.xy_simulation_gcode_lines(lines, name=name)
        except Exception as err:
            log.exception("XY simulation G-code generation failed")
            self.emit_preview_message("%s: %s" % (_("Simulation failed"), err), "error")
            return

        if not simulation_lines:
            self.emit_preview_message(_("No XY motion found to simulate."), "warn")
            return

        safe_z = self.simulation_safe_z_value()
        self.is_streaming = True
        self.stream_mode = "simulate"
        self.streaming_paused = False
        self.current_queue_idx = -1
        self.current_line_idx = 0
        self.ui.pause_btn.setText("PAUSE")
        self.jog_controls_update_sig.emit()
        self.update_progress_sig.emit(0.0, _("Simulation"))
        threading.Thread(
            target=self.xy_simulation_worker,
            args=(name, simulation_lines, safe_z),
            daemon=True
        ).start()

    def simulation_safe_z_value(self):
        try:
            safe_z = float(self.ui.autolevel_safe_z.value())
        except Exception:
            try:
                safe_z = float(self.current_machine_profile().get("safe_z", 5.0))
            except Exception:
                safe_z = 5.0
        if not math.isfinite(safe_z):
            return 5.0
        return safe_z

    @staticmethod
    def split_generated_gcode_lines(lines):
        flat_lines = []
        for line in lines:
            flat_lines.extend(str(line or "").splitlines())
        return flat_lines

    def xy_simulation_gcode_lines(self, lines, name=None):
        transformed_lines = self.transformed_gcode_lines(lines, name=name)
        return self.xy_only_safe_motion_lines(self.split_generated_gcode_lines(transformed_lines))

    def xy_only_safe_motion_lines(self, lines):
        simulation_lines = []
        current_motion = None
        current_feed = None
        current_units = None
        absolute = True

        for raw_line in lines:
            clean_line = self.clean_gcode_line(raw_line)
            if not clean_line:
                continue

            upper_line = clean_line.upper()
            if upper_line.startswith("$"):
                continue

            raw_g_values = self.raw_g_code_values(upper_line)
            if any(
                    math.isclose(code, 10.0) or math.isclose(code, 28.0) or
                    math.isclose(code, 30.0) or math.isclose(code, 38.2) or
                    math.isclose(code, 53.0) or int(code) == 92
                    for code in raw_g_values
            ):
                continue

            words = self.gcode_words(upper_line)
            g_codes = self.modal_g_codes(upper_line)

            if 20 in g_codes and current_units != "inch":
                current_units = "inch"
                simulation_lines.append("G20")
            if 21 in g_codes and current_units != "mm":
                current_units = "mm"
                simulation_lines.append("G21")
            if 90 in g_codes and not absolute:
                absolute = True
                simulation_lines.append("G90")
            if 91 in g_codes and absolute:
                absolute = False
                simulation_lines.append("G91")

            for code in g_codes:
                if code in (0, 1, 2, 3):
                    current_motion = code

            if "F" in words:
                current_feed = words["F"]

            has_xy = "X" in words or "Y" in words
            has_full_circle_arc = current_motion in (2, 3) and ("I" in words or "J" in words)
            if not has_xy and not has_full_circle_arc:
                continue

            motion = current_motion if current_motion in (0, 1, 2, 3) else 0
            command_words = ["G%d" % motion]
            for axis in ("X", "Y"):
                if axis in words:
                    command_words.append("%s%s" % (axis, self.format_gcode_number(words[axis])))
            if motion in (2, 3):
                for axis in ("I", "J", "R"):
                    if axis in words:
                        command_words.append("%s%s" % (axis, self.format_gcode_number(words[axis])))
            if motion in (1, 2, 3) and current_feed is not None:
                command_words.append("F%s" % self.format_gcode_number(current_feed))

            simulation_lines.append(" ".join(command_words))

        return simulation_lines

    def spindle_stop_simulation_commands(self):
        command = self.current_profile().get("spindle_stop", "M5")
        if isinstance(command, bytes):
            return []
        commands = [line.strip() for line in str(command or "").splitlines() if line.strip()]
        return commands or ["M5"]

    def xy_simulation_worker(self, name, simulation_lines, safe_z):
        wcs_label, _p_num = self.selected_work_offset()
        safe_z_word = self.format_gcode_number(safe_z)
        setup_commands = [
            wcs_label,
        ] + self.spindle_stop_simulation_commands() + [
            "G21",
            "G90",
            "G0 Z%s" % safe_z_word,
        ]
        teardown_commands = self.spindle_stop_simulation_commands() + [
            "G21",
            "G90",
            "G0 Z%s" % safe_z_word,
        ]
        stream_commands = setup_commands + simulation_lines + teardown_commands
        total = len(stream_commands)
        sent = 0
        aborted = False

        self.append_console_sig.emit(
            _("XY simulation started for %s. Z is held at safe height %.3f mm; spindle/probe commands are skipped.") % (
                name, safe_z
            ),
            "info"
        )

        try:
            for index, command in enumerate(stream_commands):
                if not self.is_streaming:
                    aborted = True
                    break

                while self.streaming_paused and self.is_streaming:
                    time.sleep(0.1)

                if not str(command).strip():
                    continue

                self.current_line_idx = index
                self.ok_received.clear()
                self.last_controller_ack = ""
                self.send_command(command, log=True)
                if not self.wait_for_stream_ack(command, timeout=900.0, warn_after=5.0):
                    aborted = True
                    break

                sent += 1
                self.update_progress_sig.emit((sent / total * 100.0) if total else 0.0, command)
        finally:
            completed = self.is_streaming and not aborted
            self.is_streaming = False
            self.streaming_paused = False
            self.current_queue_idx = -1
            self.stream_mode = "job"
            self.jog_controls_update_sig.emit()
            self.update_progress_sig.emit(
                100.0 if completed and total else 0.0,
                _("Simulation done") if completed else _("Simulation stopped")
            )
            self.queue_update_sig.emit()
            self.emit_preview_message(
                _("XY simulation completed.") if completed else _("XY simulation stopped."),
                "info" if completed else "warn"
            )

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
        preview_lines = self.transformed_gcode_lines(lines, name=name)
        canvas_preview = self.build_job_canvas_preview(name, lines, preview_lines)
        try:
            result = self.analyze_gcode(name, preview_lines, original_lines=lines)
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
        zcut_override_mm = self.selected_zcut_override("mm")
        if zcut_override_mm is not None:
            result["name"] = "%s | %s %.4f mm" % (result["name"], _("Z Cut"), zcut_override_mm)
            result["zcut_override_mm"] = zcut_override_mm
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

    @staticmethod
    def modal_g_codes(line):
        values = []
        for value in re.findall(r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line):
            try:
                number = float(value)
            except ValueError:
                continue
            nearest = int(round(number))
            if abs(number - nearest) < 1e-9:
                values.append(nearest)
        return values

    @staticmethod
    def raw_g_code_values(line):
        values = []
        for value in re.findall(r"\bG\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line):
            try:
                values.append(float(value))
            except ValueError:
                pass
        return values

    @staticmethod
    def metadata_number(value):
        try:
            return float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None

    @classmethod
    def gcode_comment_metadata(cls, lines):
        metadata = {}
        number = r"([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))"
        for index, raw_line in enumerate(lines or [], start=1):
            text = str(raw_line or "")
            tool_match = re.search(r"TOOL\s+DIAMETER\s*:\s*%s" % number, text, flags=re.IGNORECASE)
            if tool_match and "tool_dia_mm" not in metadata:
                value = cls.metadata_number(tool_match.group(1))
                if value is not None:
                    metadata["tool_dia_mm"] = value
                    metadata["tool_dia_line"] = index

            zcut_match = re.search(r"\bZ[\s_-]*CUT\s*:\s*%s" % number, text, flags=re.IGNORECASE)
            if zcut_match and "zcut_mm" not in metadata:
                value = cls.metadata_number(zcut_match.group(1))
                if value is not None:
                    metadata["zcut_mm"] = value
                    metadata["zcut_line"] = index
        return metadata

    @staticmethod
    def probable_pcb_isolation_gcode(name, lines, metadata):
        if not metadata.get("tool_dia_mm") or metadata.get("zcut_mm") is None:
            return False

        text_parts = [str(name or "")]
        text_parts.extend(str(line or "") for line in list(lines or [])[:60])
        text = "\n".join(text_parts).lower()
        return bool(re.search(r"(^|[^a-z0-9])iso([^a-z0-9]|$)|isolation", text))

    def estimated_vbit_cut_width(self, cut_z_mm):
        try:
            tip_dia = float(self.app.options.get("tools_iso_vtipdia", self.app.options.get("tools_mill_vtipdia", 0.0)))
            tip_angle = float(
                self.app.options.get("tools_iso_vtipangle", self.app.options.get("tools_mill_vtipangle", 0.0))
            )
        except (AttributeError, TypeError, ValueError):
            return None

        if tip_dia <= 0 or tip_angle <= 0:
            return None

        half_angle = tip_angle / 2.0
        width = tip_dia + (2.0 * abs(float(cut_z_mm or 0.0)) * math.tan(math.radians(half_angle)))
        return width, tip_dia, tip_angle

    def zcut_override_warnings(self, original_lines, zcut_override_mm=None):
        if zcut_override_mm is None:
            zcut_override_mm = self.selected_zcut_override("mm")
        if zcut_override_mm is None:
            return []

        metadata = self.gcode_comment_metadata(original_lines)
        original_zcut = metadata.get("zcut_mm")
        if original_zcut is None:
            return []

        try:
            zcut_override_mm = float(zcut_override_mm)
            original_zcut = float(original_zcut)
        except (TypeError, ValueError):
            return []

        if abs(zcut_override_mm - original_zcut) <= 0.001:
            return []

        line_no = str(metadata.get("zcut_line", "-"))
        warnings = [(
            "WARN",
            line_no,
            _("Z Cut Override changes cut depth after the CNCJob was generated; XY isolation offsets are not recalculated. "
              "For V-bit PCB isolation, regenerate the isolation/CNCJob with the final Cut Z.")
        )]

        override_width = self.estimated_vbit_cut_width(zcut_override_mm)
        if override_width:
            new_width, tip_dia, tip_angle = override_width
            old_width = metadata.get("tool_dia_mm")
            if old_width is None:
                old_width_estimate = self.estimated_vbit_cut_width(original_zcut)
                old_width = old_width_estimate[0] if old_width_estimate else None
            if old_width is not None:
                try:
                    old_width = float(old_width)
                    delta = new_width - old_width
                    warnings.append((
                        "INFO",
                        "-",
                        _("Estimated V-bit cut width changes from %.4f mm to %.4f mm "
                          "(tip %.4f mm, angle %.1f deg).") % (old_width, new_width, tip_dia, tip_angle)
                    ))
                    if delta > 0.005:
                        warnings.append((
                            "WARN",
                            "-",
                            _("The override makes the physical channel about %.4f mm wider while the toolpath offset "
                              "stays based on the original CNCJob.") % delta
                        ))
                except (TypeError, ValueError):
                    pass

        return warnings

    def analyze_gcode(self, name, lines, original_lines=None):
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
            g_codes = self.modal_g_codes(upper_line)
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
        warnings.extend(self.zcut_override_warnings(original_lines if original_lines is not None else lines))

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
        if hasattr(self.ui, 'gcode_job_canvas'):
            self.ui.gcode_job_canvas.edit_mode = False
            self.ui.gcode_job_canvas.sync_placement(0.0, 0.0, 0.0)
            self.ui.gcode_job_canvas.set_preview(result.get('canvas', {}))
        if hasattr(self.ui, 'live_simulation_canvas'):
            self.ui.live_simulation_canvas.sync_placement(0.0, 0.0, 0.0)
            self.ui.live_simulation_canvas.set_preview(result.get('canvas', {}))
        if hasattr(self, 'preview_modal') and self.preview_modal.isVisible():
            if not self.preview_modal.canvas.edit_mode:
                self.preview_modal.set_placement(0.0, 0.0, 0.0)
                self.preview_modal.set_preview(result.get('canvas', {}))

        table = self.ui.gcode_warning_table
        table.setRowCount(len(warnings))
        for row, (level, line, message) in enumerate(warnings):
            for column, value in enumerate([level, line, message]):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row, column, item)
        table.resizeRowsToContents()

    def on_refresh_ports(self):
        selected_port = ""
        try:
            selected_port = self.ui.connection_config().get("port", "")
        except Exception:
            selected_port = ""
        if not selected_port or selected_port == "None":
            selected_port = self.read_connection_settings().get("config", {}).get("port", "")

        self.ui.com_port.blockSignals(True)
        try:
            self.ui.com_port.clear()
            ports = list(serial.tools.list_ports.comports())
            for port in ports:
                description = port.description if port.description else port.device
                self.ui.com_port.addItem(f"{port.device} - {description}", port.device)
            if self.ui.com_port.count() == 0:
                self.ui.com_port.addItem("None", "None")
            if selected_port and selected_port != "None":
                port_idx = self.find_com_port_index(selected_port)
                if port_idx < 0:
                    self.ui.com_port.addItem(selected_port, selected_port)
                    port_idx = self.ui.com_port.count() - 1
                self.ui.com_port.setCurrentIndex(port_idx)
        finally:
            self.ui.com_port.blockSignals(False)

    def find_com_port_index(self, port_name):
        port_name = str(port_name or "").strip()
        if not port_name:
            return -1
        for index in range(self.ui.com_port.count()):
            item_data = self.ui.com_port.itemData(index)
            item_text = self.ui.com_port.itemText(index).strip().split(" - ", 1)[0]
            if str(item_data or "").strip() == port_name or item_text == port_name:
                return index
        return -1

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

    @staticmethod
    def qsettings_bool(value, default=False):
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def connection_settings_path(self):
        data_path = getattr(self.app, "data_path", None)
        if not data_path:
            return None
        return os.path.join(data_path, "cnc_connection_settings.json")

    def read_connection_settings(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        config = {}
        raw_config = settings.value("cnc_connection_config", "")
        if raw_config:
            try:
                config = json.loads(str(raw_config))
            except Exception:
                config = {}

        data = {
            "auto_connect": self.qsettings_bool(settings.value("cnc_auto_connect", False)),
            "config": config if isinstance(config, dict) else {},
        }

        path = self.connection_settings_path()
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as settings_file:
                    file_data = json.load(settings_file)
            except Exception as err:
                log.warning("Could not read CNC connection settings: %s", err)
                file_data = {}
            if isinstance(file_data, dict):
                file_config = file_data.get("config")
                if isinstance(file_config, dict):
                    data["config"] = file_config
                elif "mode" in file_data:
                    data["config"] = file_data
                if "auto_connect" in file_data:
                    data["auto_connect"] = self.qsettings_bool(file_data.get("auto_connect"), data["auto_connect"])

        return data

    def write_connection_settings(self, config, auto_connect):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        settings.setValue("cnc_auto_connect", bool(auto_connect))
        settings.setValue("cnc_connection_config", json.dumps(config))
        settings.sync()

        path = self.connection_settings_path()
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump(
                    {
                        "auto_connect": bool(auto_connect),
                        "config": config,
                    },
                    settings_file,
                    indent=2
                )
        except Exception as err:
            log.warning("Could not write CNC connection settings: %s", err)

    def load_connection_settings(self):
        stored = self.read_connection_settings()
        config = stored.get("config", {})
        if not isinstance(config, dict):
            config = {}

        mode = config.get("mode")
        if mode:
            mode_idx = self.ui.connection_mode_combo.findData(mode)
            if mode_idx >= 0:
                self.ui.connection_mode_combo.setCurrentIndex(mode_idx)
        self.ui.on_connection_mode_changed()

        profile = config.get("profile")
        if profile:
            profile_idx = self.ui.profile_combo.findData(profile)
            if profile_idx >= 0:
                self.ui.profile_combo.setCurrentIndex(profile_idx)

        port = str(config.get("port", "") or "").strip()
        if port:
            if self.ui.com_port.findText(port) < 0:
                self.ui.com_port.addItem(port, port)
            self.ui.com_port.setCurrentText(port)
        baudrate = str(config.get("baudrate", "") or "").strip()
        if baudrate:
            self.ui.baudrate_combo.setCurrentText(baudrate)
        if config.get("host"):
            self.ui.tcp_host.setText(str(config.get("host", "")))
        try:
            self.ui.tcp_port.setValue(int(config.get("tcp_port", self.ui.tcp_port.value())))
        except Exception:
            pass
        if config.get("web_url"):
            self.ui.web_url.setText(str(config.get("web_url", "")))
        self.ui.web_user.setText(str(config.get("user", "") or ""))
        self.ui.web_password.setText(str(config.get("password", "") or ""))

        auto_connect = bool(stored.get("auto_connect", False))
        if hasattr(self.ui, "auto_connect_cb"):
            self.ui.auto_connect_cb.blockSignals(True)
            self.ui.auto_connect_cb.setChecked(auto_connect)
            self.ui.auto_connect_cb.blockSignals(False)
        self.write_connection_settings(self.ui.connection_config(), auto_connect)

    def save_connection_settings(self):
        auto_connect = bool(getattr(self.ui, "auto_connect_cb", None) and self.ui.auto_connect_cb.isChecked())
        self.write_connection_settings(self.ui.connection_config(), auto_connect)

    def connect_connection_setting_signals(self):
        watched = [
            self.ui.connection_mode_combo,
            self.ui.profile_combo,
            self.ui.com_port,
            self.ui.baudrate_combo,
        ]
        for combo in watched:
            try:
                combo.currentTextChanged.connect(self.on_connection_settings_changed)
            except Exception:
                pass
        for entry in [self.ui.tcp_host, self.ui.web_url, self.ui.web_user, self.ui.web_password]:
            entry.textChanged.connect(self.on_connection_settings_changed)
        self.ui.tcp_port.valueChanged.connect(self.on_connection_settings_changed)

    def on_auto_connect_changed(self, _enabled=False):
        self.save_connection_settings()

    def on_connection_settings_changed(self, *_args):
        self.save_connection_settings()

    def maybe_auto_connect_on_startup(self):
        if self.is_connected:
            return
        auto_cb = getattr(self.ui, "auto_connect_cb", None)
        if auto_cb is None or not auto_cb.isChecked():
            return
        config = self.ui.connection_config()
        message = self.validate_connection_config(config)
        if message:
            self.append_console_sig.emit(
                "%s: %s" % (_("Auto connect skipped"), message),
                "warn"
            )
            return
        self.ui.set_connection_actions_enabled(False)
        self.append_console_sig.emit(_("Auto connecting to CNC..."), "info")
        threading.Thread(
            target=self._connect_worker,
            args=(config, True, self.auto_connect_attempts),
            daemon=True
        ).start()

    def on_profile_changed(self, *_args):
        self.active_profile_key = self.ui.profile_combo.currentData() or "fluidnc"
        self.on_connection_settings_changed()

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

        if getattr(self.ui, "auto_connect_cb", None) and self.ui.auto_connect_cb.isChecked():
            self.save_connection_settings()
        self.ui.set_connection_actions_enabled(False)
        self.append_console_sig.emit(_("Connecting..."), "info")
        threading.Thread(target=self._connect_worker, args=(config, False, 1), daemon=True).start()

    def validate_connection_config(self, config):
        if config["mode"] == "serial" and not str(config.get("port", "")).strip():
            return _("No COM port selected.")
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

    def _connect_worker(self, config, auto=False, attempts=1):
        attempts = max(1, int(attempts or 1))
        last_error = None

        for attempt in range(1, attempts + 1):
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
                return
            except Exception as e:
                last_error = e
                log.error("CNC connection error: %s", e)
                if not auto or attempt >= attempts:
                    break
                self.append_console_sig.emit(
                    _("Auto connect failed (%d/%d). Retrying...") % (attempt, attempts),
                    "warn"
                )
                time.sleep(self.auto_connect_retry_delay)

        if auto:
            self.append_console_sig.emit(
                "%s: %s" % (_("Auto connect stopped"), last_error),
                "warn"
            )
        else:
            self.append_console_sig.emit(f"{_('Connection failed')}: {last_error}", "error")
        self.connection_state_sig.emit(False, "")

    def on_connection_state_changed(self, connected, description):
        self.ui.set_connection_actions_enabled(True)
        self.controller_state = "Idle" if connected else "Offline"
        if not connected:
            self.jog_in_flight = False
            self.jog_motion_seen = False
        self.ui.set_connected(connected)
        self.jog_controls_update_sig.emit()
        self.update_toolbar_connection_status(connected, description)
        if connected:
            self.append_console_sig.emit(f"{_('Connected')}: {description}", "info")
            self.ui.connection_desc.setText(description)
            self.on_refresh_files()
        else:
            self.ui.connection_desc.setText(_("Offline"))
            self.append_console_sig.emit(_("Disconnected"), "info")
        self.ui.sync_connection_dialog(connected)
        if hasattr(self.ui, 'live_simulation_canvas'):
            self.ui.live_simulation_canvas.full_screen_requested.connect(self.on_full_screen_preview)

    # ##########################################################
    # ##################### MACRO SYSTEM #######################
    # ##########################################################

    def macros_settings_path(self):
        data_path = getattr(self.app, "data_path", None)
        if not data_path:
            return None
        return os.path.join(data_path, "cnc_macros.json")

    @staticmethod
    def normalize_macro_list(macros):
        if not isinstance(macros, list):
            return None
        normalized = []
        for macro in macros:
            if not isinstance(macro, dict):
                continue
            name = str(macro.get("name", "")).strip()
            if not name:
                continue
            normalized.append({
                "name": name,
                "content": str(macro.get("content", "")),
            })
        return normalized

    def default_macros(self):
        return [
            {"name": "Home & Zero", "content": "G28\nG10 L20 P1 X0 Y0 Z0"},
            {"name": "Probe Z", "content": "G38.2 Z-50 F100\nG10 L20 P1 Z0"}
        ]

    def load_macros(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        macros = None
        if settings.contains("cnc_macros"):
            try:
                macros = self.normalize_macro_list(json.loads(str(settings.value("cnc_macros"))))
            except Exception:
                macros = None

        path = self.macros_settings_path()
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as settings_file:
                    file_data = json.load(settings_file)
                if isinstance(file_data, dict):
                    file_data = file_data.get("macros")
                file_macros = self.normalize_macro_list(file_data)
                if file_macros is not None:
                    macros = file_macros
            except Exception as err:
                log.warning("Could not read CNC macros: %s", err)

        self.macros = macros if macros is not None else self.default_macros()

        # Migrate the old default Probe Z macro away from G92. G92 is temporary and
        # can stack with WCS + auto-level corrections if it is not explicitly cleared.
        for macro in self.macros:
            if macro.get("name") == "Probe Z" and "G92 Z0" in str(macro.get("content", "")).upper():
                macro["content"] = str(macro["content"]).replace("G92 Z0", "G10 L20 P1 Z0")
                self.save_macros_to_storage()

        # Only update an inline macro list if a future CNC subplugin provides one.
        if hasattr(self, 'ui') and self.ui and hasattr(self.ui, "macro_list"):
            self.ui.macro_list.clear()
            for macro in self.macros:
                self.ui.macro_list.addItem(macro["name"])

    def save_macros_to_storage(self):
        settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        settings.setValue("cnc_macros", json.dumps(self.macros))
        settings.sync()

        path = self.macros_settings_path()
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump({"macros": self.macros}, settings_file, indent=2)
        except Exception as err:
            log.warning("Could not write CNC macros: %s", err)

    def apply_macro_dialog_changes(self, dialog_or_macros):
        macros = getattr(dialog_or_macros, "macros", dialog_or_macros)
        macros = self.normalize_macro_list(macros)
        if macros is None or macros == self.macros:
            return
        self.macros = macros
        self.save_macros_to_storage()
        self.load_macros()

    def on_manage_macros(self):
        dialog = MacroDialog(self.macros, self)
        dialog.macros_changed.connect(self.apply_macro_dialog_changes)
        dialog.exec()
        self.apply_macro_dialog_changes(dialog)

    def selected_macro_index(self):
        if not hasattr(self.ui, "macro_list"):
            return -1
        selected = self.ui.macro_list.selectedItems()
        if not selected:
            return -1
        return self.ui.macro_list.row(selected[0])

    def on_macro_context_menu(self, pos):
        item = self.ui.macro_list.itemAt(pos)
        if item is not None:
            self.ui.macro_list.setCurrentItem(item)
            idx = self.ui.macro_list.row(item)
        else:
            idx = -1
        has_macro = 0 <= idx < len(self.macros)

        menu = QtWidgets.QMenu(self.ui.macro_list)
        run_action = menu.addAction(_("Run"))
        edit_action = menu.addAction(_("Edit"))
        delete_action = menu.addAction(_("Delete"))
        for action in (run_action, edit_action, delete_action):
            action.setEnabled(has_macro)

        action = menu.exec(self.ui.macro_list.viewport().mapToGlobal(pos))
        if action == run_action:
            self.on_run_macro(idx)
        elif action == edit_action:
            self.on_edit_macro(idx)
        elif action == delete_action:
            self.on_delete_macro(idx)

    def on_run_macro(self, idx=None):
        if idx is None:
            idx = self.selected_macro_index()
        if idx < 0 or idx >= len(self.macros):
            return
        if not self.is_connected or not self.transport:
            self.append_console_sig.emit(_("Controller is not connected."), "error")
            return
        if self.is_streaming:
            self.append_console_sig.emit(_("Stop queue streaming before running a macro."), "warn")
            return
        if self.is_auto_leveling:
            self.append_console_sig.emit(_("Stop auto level probing before running a macro."), "warn")
            return

        macro = self.macros[idx]
        name = str(macro.get("name", _("Macro"))).strip() or _("Macro")
        commands = [line.strip() for line in str(macro.get("content", "")).splitlines() if line.strip()]
        if not commands:
            self.append_console_sig.emit("%s: %s" % (name, _("macro is empty.")), "warn")
            return

        self.append_console_sig.emit("%s: %s" % (_("Running macro"), name), "info")
        self.queue_commands(commands)

    def on_edit_macro(self, idx=None):
        if idx is None:
            idx = self.selected_macro_index()
        dialog = MacroDialog(self.macros, self)
        dialog.macros_changed.connect(self.apply_macro_dialog_changes)
        if idx is not None and 0 <= idx < dialog.macro_list.count():
            dialog.macro_list.setCurrentRow(idx)
        dialog.exec()
        self.apply_macro_dialog_changes(dialog)

    def on_delete_macro(self, idx=None):
        if idx is None:
            idx = self.selected_macro_index()
        if idx < 0 or idx >= len(self.macros):
            return
        name = str(self.macros[idx].get("name", _("Macro"))).strip() or _("Macro")
        answer = QtWidgets.QMessageBox.question(
            self,
            _("Delete Macro"),
            "%s: %s" % (_("Delete"), name)
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self.macros.pop(idx)
        self.save_macros_to_storage()
        self.load_macros()
        self.append_console_sig.emit("%s: %s" % (_("Deleted macro"), name), "info")

    def on_test_connection_clicked(self):
        if self.is_connected:
            self.append_console_sig.emit(_("Already connected."), "info")
            return

        config = self.ui.connection_config()
        message = self.validate_connection_config(config)
        if message:
            self.append_console_sig.emit(message, "error")
            return

        if getattr(self.ui, "auto_connect_cb", None) and self.ui.auto_connect_cb.isChecked():
            self.save_connection_settings()
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

        self.controller_state = "Offline"
        self.jog_in_flight = False
        self.jog_motion_seen = False
        self.jog_controls_update_sig.emit()

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
        if not template:
            self.append_console_sig.emit(_("Jog is not supported by selected profile."), "warn")
            return
        if not self.can_start_jog():
            return

        distance = step * direction
        try:
            command = template.format(axis=axis, distance=distance, feed=feed)
        except Exception as err:
            self.append_console_sig.emit("%s: %s" % (_("Jog command could not be created"), err), "error")
            self.finish_jog()
            return

        commands = [line.strip() for line in str(command).splitlines() if line.strip()]
        if not commands:
            self.finish_jog()
            return

        estimated_seconds = max(0.15, abs(float(distance)) / max(1.0, float(feed)) * 60.0)
        threading.Thread(
            target=self._send_jog_worker,
            args=(commands, estimated_seconds),
            daemon=True
        ).start()

    def can_start_jog(self):
        if not self.is_connected or not self.transport:
            self.warn_jog_blocked(_("Controller is not connected."))
            return False
        if self.is_streaming:
            self.warn_jog_blocked(_("Jog is disabled while a job is streaming. Stop the job before jogging."))
            return False
        if self.is_auto_leveling:
            self.warn_jog_blocked(_("Jog is disabled while auto-level probing is running."))
            return False

        state = self.normalized_controller_state(getattr(self, "controller_state", "Idle"))
        if state != "Idle":
            self.warn_jog_blocked(_("Jog is allowed only while the controller is Idle. Current state: %s") % state)
            return False

        with self.jog_lock:
            if self.jog_in_flight:
                self.warn_jog_blocked(_("Previous jog is still active; wait for the controller to become Idle."))
                return False
            self.jog_in_flight = True
            self.jog_motion_seen = False
        self.jog_controls_update_sig.emit()
        return True

    def warn_jog_blocked(self, message):
        now = time.time()
        if now - self.last_jog_warning < 0.8:
            return
        self.last_jog_warning = now
        self.append_console_sig.emit(message, "warn")

    def finish_jog(self):
        changed = False
        with self.jog_lock:
            if self.jog_in_flight:
                self.jog_in_flight = False
                self.jog_motion_seen = False
                changed = True
        if changed:
            self.jog_controls_update_sig.emit()

    def _send_jog_worker(self, commands, estimated_seconds):
        try:
            for command in commands:
                self.ok_received.clear()
                self.last_controller_ack = ""
                self.send_command(command, log=True)
                if not self.ok_received.wait(timeout=4.0):
                    self.append_console_sig.emit(
                        "%s: %s" % (_("Jog command was not acknowledged"), command),
                        "warn"
                    )
                    return
                if str(self.last_controller_ack).lower().startswith("error"):
                    self.append_console_sig.emit(
                        "%s: %s" % (_("Controller rejected jog command"), command),
                        "error"
                    )
                    return

            self.wait_for_jog_motion_done(estimated_seconds)
        finally:
            self.finish_jog()

    def wait_for_jog_motion_done(self, estimated_seconds):
        started = time.time()
        motion_seen = False
        minimum_hold = min(max(float(estimated_seconds or 0.15), 0.15), 30.0)
        deadline = started + max(minimum_hold + 2.0, 0.75)

        while self.is_connected and time.time() < deadline:
            state = self.normalized_controller_state(getattr(self, "controller_state", "Idle"))
            if state in {"Jog", "Run"}:
                motion_seen = True
            if state == "Idle":
                if motion_seen or time.time() - started >= minimum_hold:
                    return True
            time.sleep(0.05)
        return False

    def update_jog_controls_enabled(self):
        if not hasattr(self.ui, "jog_up"):
            return
        state = self.normalized_controller_state(getattr(self, "controller_state", "Idle"))
        enabled = (
            self.is_connected and
            not self.is_streaming and
            not self.is_auto_leveling and
            not self.jog_in_flight and
            state == "Idle"
        )
        for button in [
                self.ui.jog_up, self.ui.jog_down, self.ui.jog_left,
                self.ui.jog_right, self.ui.jog_z_up, self.ui.jog_z_down
        ]:
            button.setEnabled(enabled)

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
        
        # 1. Start with standard probe commands (Fast Seek)
        commands = self.probe_commands()
        if not commands:
            return
            
        # 2. Add High-Precision Stage (Candle style)
        # G91 (Relative), G0 Z0.5 (Retract), G90 (Absolute)
        # Then Slow Probe G38.2 Z... F10
        slow_z_target = -settings['distance']
        commands.extend([
            "G91",
            "G0 Z0.5",
            "G90",
            f"G38.2 Z{slow_z_target:.4f} F10"
        ])
        
        # 3. Set the Work Offset based on the final (slow) touch
        commands.append(f"G10 L20 P{p_num} Z{settings['plate']:.4f}")
        
        # 4. Final Retract
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
        return "canvas"

    def selected_job_size(self, raw_width, raw_height, units):
        units = self.normalized_units(units)
        size_x = getattr(self.ui, "job_size_x", None)
        size_y = getattr(self.ui, "job_size_y", None)
        try:
            job_width = float(size_x.value()) if size_x is not None else 0.0
        except Exception:
            job_width = 0.0
        try:
            job_height = float(size_y.value()) if size_y is not None else 0.0
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
        units = self.normalized_units(units)
        margin_x_widget = getattr(self.ui, "job_margin_x", None)
        margin_y_widget = getattr(self.ui, "job_margin_y", None)
        try:
            margin_x = float(margin_x_widget.value()) if margin_x_widget is not None else 0.0
        except Exception:
            margin_x = 0.0
        try:
            margin_y = float(margin_y_widget.value()) if margin_y_widget is not None else 0.0
        except Exception:
            margin_y = 0.0

        if units == "inch":
            margin_x /= 25.4
            margin_y /= 25.4
        return max(0.0, margin_x), max(0.0, margin_y)

    def selected_zcut_override(self, units):
        enabled_widget = getattr(self.ui, "zcut_override_cb", None)
        value_widget = getattr(self.ui, "zcut_override_value", None)
        if enabled_widget is None or value_widget is None or not enabled_widget.isChecked():
            return None

        try:
            z_value_mm = float(value_widget.value())
        except Exception:
            return None

        if z_value_mm > 0:
            z_value_mm = -abs(z_value_mm)

        return z_value_mm / 25.4 if self.effective_gcode_units(units) == "inch" else z_value_mm

    def live_placement_has_transform(self):
        return (
            abs(float(self.live_offset_x or 0.0)) > 1e-9 or
            abs(float(self.live_offset_y or 0.0)) > 1e-9 or
            abs(float(self.live_rotation or 0.0)) > 1e-9
        )

    @staticmethod
    def normalized_units(units, default="mm"):
        text = str(units or default).strip().lower()
        if text in {"in", "inch", "inches"}:
            return "inch"
        return "mm"

    def project_workspace_bounds(self, units):
        if not self.app.options.get('global_workspace', False):
            return None

        dimensions = None
        try:
            dimensions_fcn = getattr(self.app.plotcanvas, "workspace_dimensions", None)
            if callable(dimensions_fcn):
                dimensions = dimensions_fcn(self.app.options.get('global_workspaceT', 'A4'))
        except Exception as err:
            log.debug("ToolCNCControl.project_workspace_bounds() -> %s", err)

        if not dimensions:
            return None

        width, height = dimensions
        app_units = "inch" if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else "mm"
        target_units = self.normalized_units(units, app_units)
        if app_units == "mm" and target_units == "inch":
            width /= 25.4
            height /= 25.4
        elif app_units == "inch" and target_units == "mm":
            width *= 25.4
            height *= 25.4

        return [0.0, width, 0.0, height]

    def project_workspace_material_bounds(self, units, mode):
        bounds = self.project_workspace_bounds(units)
        if not bounds:
            return None
        width = max(0.0, float(bounds[1]) - float(bounds[0]))
        height = max(0.0, float(bounds[3]) - float(bounds[2]))
        if mode in {"absolute", "canvas"}:
            return bounds
        return self.material_bounds_for_origin(mode, width, height)

    @staticmethod
    def copy_target_bounds(bounds):
        if not bounds:
            return None
        try:
            return {
                "X": [float(bounds["X"][0]), float(bounds["X"][1])],
                "Y": [float(bounds["Y"][0]), float(bounds["Y"][1])],
            }
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def transformed_bounds_for_live(base_bounds, dx, dy, rotation):
        bounds = ToolCNCControl.copy_target_bounds(base_bounds)
        if not bounds:
            return None

        x0, x1 = bounds["X"]
        y0, y1 = bounds["Y"]
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        rad = math.radians(float(rotation or 0.0))
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        points = []
        for x_value, y_value in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            tx = x_value - cx
            ty = y_value - cy
            points.append((
                (tx * cos_r) - (ty * sin_r) + cx + dx,
                (tx * sin_r) + (ty * cos_r) + cy + dy,
            ))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return {"X": [min(xs), max(xs)], "Y": [min(ys), max(ys)]}

    def apply_live_placement_to_context(self, context, apply_live_placement=True):
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        live_enabled = bool(apply_live_placement and (self.live_edit_enabled or self.live_placement_active))
        dx = (float(self.live_offset_x or 0.0) / factor) if live_enabled else 0.0
        dy = (float(self.live_offset_y or 0.0) / factor) if live_enabled else 0.0
        rotation = float(self.live_rotation or 0.0) if live_enabled else 0.0

        base_bounds = self.copy_target_bounds(context.get("target_bounds"))
        if base_bounds:
            context["base_target_bounds"] = base_bounds
            if live_enabled:
                live_bounds = self.transformed_bounds_for_live(base_bounds, dx, dy, rotation)
                if live_bounds:
                    context["target_bounds"] = live_bounds

        context["live_placement_enabled"] = live_enabled
        context["live_offset_x"] = dx
        context["live_offset_y"] = dy
        context["live_rotation"] = rotation
        zcut_override = self.selected_zcut_override(units)
        context["zcut_override"] = zcut_override
        context["zcut_override_mm"] = None if zcut_override is None else zcut_override * factor
        return context

    @staticmethod
    def live_rotation_active(context):
        return bool(
            context.get("live_placement_enabled") and
            abs(float(context.get("live_rotation", 0.0) or 0.0)) > 1e-9
        )

    def mapped_job_xy(self, context, x_value, y_value, controller_x_offset=0.0, controller_y_offset=0.0):
        x_pos = (
            float(x_value) -
            float(context.get("x_anchor", 0.0) or 0.0) -
            float(controller_x_offset or 0.0)
        )
        y_pos = (
            float(y_value) -
            float(context.get("y_anchor", 0.0) or 0.0) -
            float(controller_y_offset or 0.0)
        )

        if context.get("live_placement_enabled"):
            rotation = float(context.get("live_rotation", 0.0) or 0.0)
            bounds = self.copy_target_bounds(
                context.get("base_target_bounds") or context.get("target_bounds")
            )
            if bounds and abs(rotation) > 1e-9:
                cx = (bounds["X"][0] + bounds["X"][1]) / 2.0
                cy = (bounds["Y"][0] + bounds["Y"][1]) / 2.0
                rad = math.radians(rotation)
                tx = x_pos - cx
                ty = y_pos - cy
                x_pos = (tx * math.cos(rad)) - (ty * math.sin(rad)) + cx
                y_pos = (tx * math.sin(rad)) + (ty * math.cos(rad)) + cy
            x_pos += float(context.get("live_offset_x", 0.0) or 0.0)
            y_pos += float(context.get("live_offset_y", 0.0) or 0.0)

        return x_pos, y_pos

    def unmapped_job_xy(self, context, x_pos, y_pos, controller_x_offset=0.0, controller_y_offset=0.0):
        x_value = float(x_pos)
        y_value = float(y_pos)

        if context.get("live_placement_enabled"):
            x_value -= float(context.get("live_offset_x", 0.0) or 0.0)
            y_value -= float(context.get("live_offset_y", 0.0) or 0.0)

            rotation = float(context.get("live_rotation", 0.0) or 0.0)
            bounds = self.copy_target_bounds(
                context.get("base_target_bounds") or context.get("target_bounds")
            )
            if bounds and abs(rotation) > 1e-9:
                cx = (bounds["X"][0] + bounds["X"][1]) / 2.0
                cy = (bounds["Y"][0] + bounds["Y"][1]) / 2.0
                rad = math.radians(rotation)
                tx = x_value - cx
                ty = y_value - cy
                x_value = (tx * math.cos(rad)) + (ty * math.sin(rad)) + cx
                y_value = (-tx * math.sin(rad)) + (ty * math.cos(rad)) + cy

        return (
            x_value + float(context.get("x_anchor", 0.0) or 0.0) + float(controller_x_offset or 0.0),
            y_value + float(context.get("y_anchor", 0.0) or 0.0) + float(controller_y_offset or 0.0),
        )

    @staticmethod
    def material_bounds_for_origin(mode, job_width, job_height):
        if mode == "center":
            return [-job_width / 2.0, job_width / 2.0, -job_height / 2.0, job_height / 2.0]
        if mode == "top_left":
            return [0.0, job_width, 0.0, job_height]
        return [0.0, job_width, -job_height, 0.0]

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
            "canvas": _("Live Placement"),
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
            target_y_min = inner_y_min
        elif y_align == "center":
            target_y_min = inner_y_min + ((inner_y_max - inner_y_min - raw_height) / 2.0)
        else:
            target_y_min = inner_y_max - raw_height

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
        if self.effective_gcode_units(units) == "inch":
            width *= 25.4
            height *= 25.4

        if hasattr(self.ui, "job_size_x"):
            self.ui.job_size_x.set_value(width)
        if hasattr(self.ui, "job_size_y"):
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

        factor = 25.4 if self.app.app_units.upper() == 'IN' else 1.0
        x_min = double_value("autolevel_x_min") * factor
        x_max = double_value("autolevel_x_max") * factor
        y_min = double_value("autolevel_y_min") * factor
        y_max = double_value("autolevel_y_max") * factor
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
            "slow_probe_feed": int_value("autolevel_slow_probe_feed", 0),
            "auto_zero_z": bool_value("autolevel_auto_zero", True),
        }

    @staticmethod
    def auto_level_slow_probe_gcode(settings):
        """
        Second G38.2 pass after micro-retract (same for grid and Auto Zero Z).
        If slow_probe_feed > 0 in settings, use it (mm/min); else scale from probe_feed.
        """
        try:
            manual = int(settings.get("slow_probe_feed") or 0)
        except (TypeError, ValueError):
            manual = 0
        if manual > 0:
            slow_f = max(4, min(120, manual))
            return "G38.2 Z-2.5 F%d" % slow_f
        fast = max(1, int(settings.get("probe_feed", 120)))
        slow_f = max(12, min(45, fast // 4))
        return "G38.2 Z-2.5 F%d" % slow_f

    @staticmethod
    def auto_level_range_values(start, stop, count):
        count = max(2, count)
        step = (stop - start) / float(count - 1)
        return [start + (step * index) for index in range(count)]

    def auto_level_probe_points(self, settings):
        x_values = self.auto_level_range_values(settings["x_min"], settings["x_max"], settings["columns"])
        y_values = self.auto_level_range_values(settings["y_min"], settings["y_max"], settings["rows"])
        points = []

        forward_columns = list(range(len(x_values)))
        reverse_columns = list(reversed(forward_columns))
        for row, y_value in enumerate(y_values):
            y_value = y_values[row]
            columns = forward_columns if row % 2 == 0 else reverse_columns
            for column in columns:
                points.append({
                    "row": row,
                    "column": column,
                    "x": x_values[column],
                    "y": y_value,
                })
        return x_values, y_values, points

    def project_xy_to_controller_xy(self, x_value, y_value, wcs_label, x_anchor=0.0, y_anchor=0.0):
        offset = self.combined_work_offset(wcs_label)
        return (
            float(x_value) - float(x_anchor or 0.0) - float(offset[0]),
            float(y_value) - float(y_anchor or 0.0) - float(offset[1]),
        )

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

    @staticmethod
    def auto_level_reference_from_probe_order(points, measurements):
        for point in points or []:
            try:
                z_value = measurements[point["row"]][point["column"]]
            except (KeyError, TypeError, IndexError):
                continue
            if z_value is None:
                continue
            return {
                "x": point["x"],
                "y": point["y"],
                "z": z_value,
                "distance": math.hypot(point["x"], point["y"]),
            }
        return None

    def normalize_auto_level_grid_density(self, width_mm, height_mm):
        def adjust(widget_name, size_mm):
            widget = getattr(self.ui, widget_name, None)
            if widget is None or size_mm <= 0:
                return None
            try:
                current = max(2, int(widget.value()))
            except Exception:
                return None
            current_step = size_mm / float(current - 1)
            if current_step >= 2.0:
                return None

            desired = max(2, min(25, int(math.ceil(size_mm / 10.0)) + 1))
            try:
                widget.setValue(desired)
            except Exception:
                return None
            desired_step = size_mm / float(desired - 1) if desired > 1 else size_mm
            return current, current_step, desired, desired_step

        col_change = adjust("autolevel_columns", width_mm)
        row_change = adjust("autolevel_rows", height_mm)
        if col_change or row_change:
            details = []
            if col_change:
                details.append(
                    _("columns %d (%.3f mm) -> %d (%.3f mm)") % col_change
                )
            if row_change:
                details.append(
                    _("rows %d (%.3f mm) -> %d (%.3f mm)") % row_change
                )
            self.append_console_sig.emit(
                _("Auto level grid was too dense after Fit Area; adjusted %s.") % ", ".join(details),
                "info"
            )

    def on_auto_level_fit_area(self, *_args):
        name, lines = self.selected_preview_job()
        if not lines:
            self.append_console_sig.emit(_("No CNCJob object selected."), "error")
            return

        transform_context = self.stream_transform_context(lines, name=name)
        units = self.effective_gcode_units(transform_context.get("units"))
        app_units = "inch" if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else "mm"
        bounds = None
        bounds_units = units
        bounds_source = _("mapped CNCJob area")
        target_bounds = transform_context.get("target_bounds")
        if target_bounds and (transform_context.get("enabled") or transform_context.get("live_placement_enabled")):
            bounds = [
                target_bounds["X"][0],
                target_bounds["X"][1],
                target_bounds["Y"][0],
                target_bounds["Y"][1],
            ]

        if bounds is None:
            bounds = self.cncjob_object_xy_bounds(name)
            bounds_units = app_units
            bounds_source = _("CNCJob object")

        if bounds is None:
            if target_bounds:
                bounds = [
                    target_bounds["X"][0],
                    target_bounds["X"][1],
                    target_bounds["Y"][0],
                    target_bounds["Y"][1],
                ]
                bounds_units = units
                bounds_source = _("cutting bounds")

        if bounds is None:
            preview_lines = [self.transform_stream_command(line, transform_context) for line in lines]
            gcode_bounds, units = self.gcode_bounds(preview_lines, cutting_only=True)
            if gcode_bounds["X"][0] is None or gcode_bounds["Y"][0] is None:
                gcode_bounds, units = self.gcode_bounds(preview_lines)
                bounds_source = _("G-code bounds")
            else:
                bounds_source = _("cutting bounds")
            if gcode_bounds["X"][0] is not None and gcode_bounds["Y"][0] is not None:
                bounds = [
                    gcode_bounds["X"][0],
                    gcode_bounds["X"][1],
                    gcode_bounds["Y"][0],
                    gcode_bounds["Y"][1],
                ]
                bounds_units = self.effective_gcode_units(units)

        if not bounds:
            self.append_console_sig.emit(_("Selected CNCJob has no usable XY bounds."), "error")
            return

        ui_factor = self.units_scale(bounds_units, app_units)
        mm_factor = self.units_scale(bounds_units, "mm")
        bounds_mm = [
            bounds[0] * mm_factor,
            bounds[1] * mm_factor,
            bounds[2] * mm_factor,
            bounds[3] * mm_factor,
        ]
        self.ui.autolevel_x_min.set_value(bounds[0] * ui_factor)
        self.ui.autolevel_x_max.set_value(bounds[1] * ui_factor)
        self.ui.autolevel_y_min.set_value(bounds[2] * ui_factor)
        self.ui.autolevel_y_max.set_value(bounds[3] * ui_factor)
        self.normalize_auto_level_grid_density(
            abs(bounds_mm[1] - bounds_mm[0]),
            abs(bounds_mm[3] - bounds_mm[2])
        )
        self.ui.autolevel_status.setText(_("Area fitted from %s") % (name or _("CNCJob")))
        self.append_console_sig.emit(
            _("Auto level area fitted from %s: X%.3f..%.3f  Y%.3f..%.3f mm") % (
                bounds_source,
                bounds_mm[0], bounds_mm[1], bounds_mm[2], bounds_mm[3]
            ),
            "info"
        )

    def current_auto_level_job_bounds_mm(self):
        _name, lines = self.selected_preview_job()
        if not lines:
            return None

        context = self.stream_transform_context(lines, name=_name)
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        target_bounds = context.get("target_bounds")
        if target_bounds and (context.get("enabled") or context.get("live_placement_enabled")):
            return [
                target_bounds["X"][0] * factor,
                target_bounds["X"][1] * factor,
                target_bounds["Y"][0] * factor,
                target_bounds["Y"][1] * factor,
            ]

        bounds = self.cncjob_object_xy_bounds(_name)
        if bounds is not None:
            factor = 25.4 if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else 1.0
            return [value * factor for value in bounds]

        if target_bounds:
            return [
                target_bounds["X"][0] * factor,
                target_bounds["X"][1] * factor,
                target_bounds["Y"][0] * factor,
                target_bounds["Y"][1] * factor,
            ]

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

        job_bounds_for_refit = self.current_auto_level_job_bounds_mm()
        if job_bounds_for_refit:
            area_width = abs(settings["x_max"] - settings["x_min"])
            area_height = abs(settings["y_max"] - settings["y_min"])
            job_width = abs(job_bounds_for_refit[1] - job_bounds_for_refit[0])
            job_height = abs(job_bounds_for_refit[3] - job_bounds_for_refit[2])
            x_step = area_width / float(max(1, settings["columns"] - 1))
            y_step = area_height / float(max(1, settings["rows"] - 1))
            area_is_tiny = (
                (job_width > 0 and area_width < (job_width * 0.25)) or
                (job_height > 0 and area_height < (job_height * 0.25))
            )
            if area_is_tiny and min(x_step, y_step) < 2.0:
                self.append_console_sig.emit(
                    _("Auto level area is much smaller than the selected CNCJob and the probe step is below 2 mm; "
                      "refitting area from the CNCJob object."),
                    "warn"
                )
                self.on_auto_level_fit_area()
                settings = self.auto_level_settings()

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
        if len(x_values) > 1 and len(y_values) > 1:
            x_step = abs(x_values[1] - x_values[0])
            y_step = abs(y_values[1] - y_values[0])
            self.append_console_sig.emit(
                _("Auto level probe grid: X%.3f..%.3f (%d columns, %.3f mm step), "
                  "Y%.3f..%.3f (%d rows, %.3f mm step)") % (
                    x_values[0], x_values[-1], len(x_values), x_step,
                    y_values[0], y_values[-1], len(y_values), y_step,
                ),
                "info"
            )
            if min(x_step, y_step) < 2.0:
                self.append_console_sig.emit(
                    _("Auto level probe spacing is below 2 mm. Click Fit Area for the selected CNCJob "
                      "or reduce Rows/Columns if this is not intentional."),
                    "warn"
                )

        job_name, job_lines = self.selected_preview_job()
        if job_lines:
            probe_context = self.stream_transform_context(job_lines, name=job_name)
            settings["job_name"] = job_name
            settings["transform_signature"] = self.auto_level_context_signature(probe_context)

        wcs_label, p_num = self.selected_work_offset()
        spindle_stop = self.current_profile().get("spindle_stop", "M5")
        self.is_auto_leveling = True
        self.auto_level_cancel.clear()
        self.jog_controls_update_sig.emit()
        self.auto_level_update_sig.emit({
            "busy": True,
            "progress": 0,
            "status": _("Probing 0/%d") % len(points),
        })
        threading.Thread(
            target=self.auto_level_probe_worker,
            args=(settings, x_values, y_values, points, wcs_label, p_num, spindle_stop),
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
        self.clear_auto_level_map(refresh=True)

    def clear_auto_level_map(self, refresh=False):
        self.auto_level_map = None
        if hasattr(self.ui, "autolevel_enable_cb"):
            self.ui.autolevel_enable_cb.set_value(False)
        self.auto_level_update_sig.emit({
            "progress": 0,
            "status": _("No height map"),
            "map": None,
        })
        if refresh:
            self.on_preview_refresh(refresh_jobs=False)

    def invalidate_auto_level_map(self, message=None):
        if self.is_auto_leveling:
            return
        if not self.auto_level_map_is_valid(self.auto_level_map):
            return

        self.clear_auto_level_map(refresh=False)
        if message:
            self.append_console_sig.emit(message, "warn")

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

    def auto_level_probe_worker(self, settings, x_values, y_values, points, wcs_label, p_num, spindle_stop):
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
                "G92.1",
                "G49",
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

            if points:
                sample = points[0]
                self.append_console_sig.emit(
                    _("Auto level probe XY uses selected %s work coordinates: first point X%.3f Y%.3f.") % (
                        wcs_label,
                        sample["x"], sample["y"],
                    ),
                    "info"
                )

            if not points:
                raise RuntimeError(_("No probing points generated."))

            def probe_touch(point):
                if self.auto_level_cancel.is_set():
                    raise RuntimeError(_("Auto level probing was stopped."))

                move_command = "G0 X%s Y%s" % (
                    self.format_gcode_number(point["x"]),
                    self.format_gcode_number(point["y"]),
                )
                if not self.send_command_and_wait(move_command, timeout=12.0):
                    raise RuntimeError(_("Controller did not acknowledge: %s") % move_command)

                self.last_probe_result = None
                self.probe_result_event.clear()
                self.ok_received.clear()

                # Compute probe timeout based on distance + feed
                probe_timeout = max(20.0, (abs(settings["probe_depth"]) / settings["probe_feed"] * 60.0) + 10.0)

                probe_command = "G38.2 Z%s F%d" % (
                    self.format_gcode_number(settings["probe_depth"]),
                    int(settings["probe_feed"]),
                )
                self.send_command(probe_command, log=True)
                if not self.probe_result_event.wait(timeout=probe_timeout):
                    raise RuntimeError(_("Probe result timed out."))

                fast_result = self.last_probe_result or {}
                if not fast_result.get("success", False):
                    raise RuntimeError(_("Probe failed at X%.3f Y%.3f.") % (point["x"], point["y"]))
                if not self.ok_received.wait(timeout=5.0):
                    raise RuntimeError(_("Probe acknowledgement timed out."))

                result = fast_result
                if int(settings.get("slow_probe_feed") or 0) > 0:
                    # Optional precision pass. Candle's default flow is the
                    # single touch above; this only runs when explicitly enabled.
                    for cmd in ["G91", "G0 Z1.5"]:
                        cmd_timeout = 5.0 if "Z" in cmd else 2.0
                        if not self.send_command_and_wait(cmd, timeout=cmd_timeout):
                            raise RuntimeError(_("Controller did not acknowledge: %s") % cmd)

                    self.last_probe_result = None
                    self.probe_result_event.clear()
                    self.ok_received.clear()

                    slow_probe_cmd = self.auto_level_slow_probe_gcode(settings)
                    self.send_command(slow_probe_cmd, log=True)
                    probe_success = self.probe_result_event.wait(timeout=15.0)
                    if probe_success and not self.ok_received.wait(timeout=5.0):
                        raise RuntimeError(_("Slow probe acknowledgement timed out."))

                    if not probe_success:
                        raise RuntimeError(_("Slow probe result timed out."))

                    result = self.last_probe_result or {}
                    if not result.get("success", False):
                        raise RuntimeError(_("Slow probe failed at X%.3f Y%.3f.") % (point["x"], point["y"]))

                # IMMEDIATE RETRACT: Move to safe Z before doing any Python processing
                if not self.send_command_and_wait("G90", timeout=3.0):
                    raise RuntimeError(_("Controller did not acknowledge: G90"))
                if not self.send_command_and_wait("G0 Z%s" % self.format_gcode_number(settings["safe_z"]), timeout=10.0):
                    raise RuntimeError(_("Controller did not acknowledge retract to safe Z"))

                work_result = self.probe_result_to_work_position(
                    result,
                    wcs_label,
                    expected_xy=(point["x"], point["y"])
                )
                return work_result["z"]

            reference_point = points[0]
            self.auto_level_update_sig.emit({
                "progress": 0,
                "status": _("Reference touch"),
            })
            self.append_console_sig.emit(
                _("Candle-style reference probe at X%.3f Y%.3f before probing the grid.") % (
                    reference_point["x"],
                    reference_point["y"],
                ),
                "info"
            )
            measured_ref_z = probe_touch(reference_point)
            reference = {
                "x": reference_point["x"],
                "y": reference_point["y"],
                "z": measured_ref_z,
                "distance": math.hypot(reference_point["x"], reference_point["y"]),
            }

            for index, point in enumerate(points, start=1):
                if self.auto_level_cancel.is_set():
                    raise RuntimeError(_("Auto level probing was stopped."))

                self.auto_level_update_sig.emit({
                    "progress": ((index - 1) / total) * 100.0,
                    "status": _("Probing %d/%d") % (index, total),
                })

                z_measured = probe_touch(point)
                measurements[point["row"]][point["column"]] = z_measured

            missing_points = [
                (row_index, column_index)
                for row_index, row_values in enumerate(measurements)
                for column_index, z_value in enumerate(row_values)
                if z_value is None
            ]
            if missing_points:
                raise RuntimeError(_("Auto level map is incomplete; probe all grid points again."))

            # Normalize all grid measurements relative to the separate first
            # touch, matching Candle's height-map delta model.
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
                "reference_mode": "candle_first_touch",
                "interpolation": "candle_bicubic",
                "probe_coordinate_mode": self.probe_coordinate_mode,
                "area_bounds": [
                    min(x_values), max(x_values),
                    min(y_values), max(y_values),
                ],
                "job_name": settings.get("job_name"),
                "transform_signature": settings.get("transform_signature"),
                "rows": len(y_values),
                "columns": len(x_values),
                "point_count": total,
                "created_at": time.strftime("%H:%M:%S"),
            }
            self.auto_level_map = auto_map
            normalized_values = self.auto_level_map_z_values(auto_map)

            # Auto Zero Z: use the grid reference cell's machine Z only (same touch as the map).
            # Avoids a second slow probe that can disagree slightly with the stored height map.
            #
            # Important: persist the zero in the selected WCS with G10 L20 instead of G92.
            # G92 is a temporary offset that survives until explicitly cleared and can stack
            # with the selected WCS + auto-level correction, causing random-looking air cuts
            # or over-deep cuts in later jobs.
            if settings.get("auto_zero_z", True):
                ref_z = reference.get("z")
                if ref_z is None:
                    self.append_console_sig.emit(_("Auto Zero Z: skipped (no reference Z from grid)."), "warn")
                else:
                    self.append_console_sig.emit(
                        _("Auto Zero Z: moving to reference X%.3f Y%.3f; Z=0 synced to grid touch...") % (
                            reference["x"], reference["y"],
                        ),
                        "info",
                    )
                    move_ref = "G0 X%s Y%s" % (
                        self.format_gcode_number(reference["x"]),
                        self.format_gcode_number(reference["y"]),
                    )
                    if not self.send_command_and_wait(move_ref, timeout=12.0):
                        self.append_console_sig.emit(
                            _("Auto Zero Z: move to reference point failed."), "warn"
                        )
                    else:
                        feed_z = max(10, int(settings["probe_feed"]) // 2)
                        move_trigger_cmd = "G90 G53 G1 Z%s F%d" % (
                            self.format_gcode_number(float(ref_z)),
                            feed_z,
                        )
                        if not self.send_command_and_wait(move_trigger_cmd, timeout=25.0):
                            self.append_console_sig.emit(
                                _("Auto Zero Z: move to grid touch height failed or not acknowledged."), "warn"
                            )
                            if not self.send_command_and_wait("G90", timeout=3.0):
                                pass
                            self.send_command_and_wait(
                                "G0 Z%s" % self.format_gcode_number(settings["safe_z"]), timeout=10.0
                            )
                        elif self.send_command_and_wait("G90", timeout=3.0) and self.send_command_and_wait(
                            "%s" % wcs_label, timeout=3.0
                        ) and self.send_command_and_wait("G10 L20 P%d Z0" % p_num, timeout=5.0):
                            retract = "G0 Z%s" % self.format_gcode_number(settings["safe_z"])
                            self.send_command_and_wait(retract, timeout=10.0)
                            self.append_console_sig.emit(
                                _("Auto Zero Z complete: selected WCS Z=0 matches grid reference (single measurement)."), "info"
                            )
                        else:
                            self.append_console_sig.emit(
                                _("Auto Zero Z: WCS Z0 command was not acknowledged."), "warn"
                            )
                            if not self.send_command_and_wait("G90", timeout=3.0):
                                pass
                            self.send_command_and_wait(
                                "G0 Z%s" % self.format_gcode_number(settings["safe_z"]), timeout=10.0
                            )
            self.auto_level_update_sig.emit({
                "busy": False,
                "enabled": True,
                "map": auto_map,
                "progress": 100,
                "status": _("Height map ready: %d points") % total,
            })
            if normalized_values:
                self.append_console_sig.emit(
                    _("Auto level height map ready: %d points. Delta Z range %.4f..%.4f mm; work zero is reference.") % (
                        total, min(normalized_values), max(normalized_values)
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
            self.jog_controls_update_sig.emit()
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

        for raw_line in lines:
            clean_line = self.clean_gcode_line(raw_line)
            if not clean_line:
                continue

            upper_line = clean_line.upper()
            words = self.gcode_words(upper_line)
            g_codes = self.modal_g_codes(upper_line)

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

            include_bounds = not cutting_only
            if cutting_only and motion in [1, 2, 3]:
                include_bounds = position["Z"] < 0 or next_position["Z"] < 0

            if include_bounds:
                for point in [position, next_position]:
                    for axis in "XYZ":
                        value = point[axis]
                        if bounds[axis][0] is None or value < bounds[axis][0]:
                            bounds[axis][0] = value
                        if bounds[axis][1] is None or value > bounds[axis][1]:
                            bounds[axis][1] = value

            position = next_position

        return bounds, units

    def effective_gcode_units(self, units):
        if units in {"inch", "mm"}:
            return units
        return "inch" if str(getattr(self.app, "app_units", "MM")).upper() == "IN" else "mm"

    @staticmethod
    def units_scale(from_units, to_units):
        if from_units == to_units:
            return 1.0
        if from_units == "inch" and to_units == "mm":
            return 25.4
        if from_units == "mm" and to_units == "inch":
            return 1.0 / 25.4
        return 1.0

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
            g_codes = self.modal_g_codes(upper_line)

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

    def build_job_canvas_preview(self, name, raw_lines, preview_lines, apply_live_placement=True):
        if not raw_lines:
            return {}

        context = self.stream_transform_context(raw_lines, name=name, apply_live_placement=apply_live_placement)
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        mode = context.get("mode", self.selected_job_origin_mode())
        placement = context.get(
            "placement",
            self.resolved_job_placement(mode, self.selected_job_placement_mode())
        )
        material_bounds = context.get("material_bounds")
        try:
            job_width = float(context.get("job_width", 0.0) or 0.0)
            job_height = float(context.get("job_height", 0.0) or 0.0)
        except (TypeError, ValueError):
            job_width = 0.0
            job_height = 0.0
        if material_bounds:
            try:
                job_width = float(material_bounds[1]) - float(material_bounds[0])
                job_height = float(material_bounds[3]) - float(material_bounds[2])
            except (TypeError, ValueError, IndexError):
                job_width = 0.0
                job_height = 0.0

        has_live = self.live_offset_x != 0 or self.live_offset_y != 0 or self.live_rotation != 0
        if self.live_edit_enabled or has_live:
            # Keep the editor's workspace rectangle in the same coordinate system as
            # the selected origin. Back-Left follows the inverted app Y axis (0..H);
            # Bottom-Left uses the opposite signed range.
            workspace_bounds = self.project_workspace_material_bounds(units, mode)
            material_bounds = workspace_bounds or material_bounds
            if material_bounds:
                job_width = material_bounds[1] - material_bounds[0]
                job_height = material_bounds[3] - material_bounds[2]

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

        # Ensure path_bounds is not zero-sized to prevent VisPy Singular Matrix error
        if path_bounds:
            pb = list(path_bounds)
            if pb[1] - pb[0] < 0.001: pb[1] = pb[0] + 0.1
            if pb[3] - pb[2] < 0.001: pb[3] = pb[2] + 0.1
            scaled_path_bounds = [v * factor for v in pb]
        else:
            scaled_path_bounds = None

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

        label = _("%s | Job %.1f x %.1f mm | Origin: %s | Place: %s") % (
            name or _("CNCJob"),
            job_width * factor,
            job_height * factor,
            origin_label,
            self.job_placement_label(placement),
        )
        if mode == "absolute":
            if placement == "canvas":
                label = _("%s | Workspace %.1f x %.1f mm | Live Placement") % (
                    name or _("CNCJob"),
                    job_width * factor,
                    job_height * factor,
                )
            else:
                label = _("%s | Workspace %.1f x %.1f mm | Absolute XY") % (
                    name or _("CNCJob"),
                    job_width * factor,
                    job_height * factor,
                )

        return {
            "label": label,
            "job_bounds": scaled_job_bounds,
            "segments": scaled_segments,
            "path_bounds": scaled_path_bounds,
            "origin": [0.0, 0.0],
            "start": scaled_start,
            "margin_guides": margin_guides,
            "outside": outside,
        }

    def finalize_stream_transform_context(self, context, lines, name=None, apply_live_placement=True):
        context = self.apply_live_placement_to_context(context, apply_live_placement)

        metadata = self.gcode_comment_metadata(lines)
        context["gcode_metadata"] = metadata
        is_isolation = self.probable_pcb_isolation_gcode(name, lines, metadata)
        context["probable_pcb_isolation"] = is_isolation

        protect_depth = bool(self.app.options.get("cnc_autolevel_protect_pcb_isolation_depth", True))
        zcut_mm = metadata.get("zcut_mm")
        if protect_depth and is_isolation and zcut_mm is not None:
            try:
                zcut_mm = float(zcut_mm)
            except (TypeError, ValueError):
                zcut_mm = None

        if protect_depth and is_isolation and zcut_mm is not None and zcut_mm < 0.0:
            units = self.effective_gcode_units(context.get("units"))
            factor = 25.4 if units == "inch" else 1.0
            context["autolevel_depth_clamp_z"] = zcut_mm / factor
            context["autolevel_depth_clamp_z_mm"] = zcut_mm

        return context

    def stream_transform_context(self, lines, name=None, apply_live_placement=True):
        mode = self.selected_job_origin_mode()
        bounds, units = self.gcode_bounds(lines, cutting_only=True)
        if bounds["X"][0] is None or bounds["Y"][0] is None:
            bounds, units = self.gcode_bounds(lines)
        units = self.effective_gcode_units(units)
        has_xy_bounds = (
            bounds["X"][0] is not None and bounds["X"][1] is not None and
            bounds["Y"][0] is not None and bounds["Y"][1] is not None
        )
        if not has_xy_bounds:
            material_bounds = (
                self.project_workspace_material_bounds(units, mode) or
                self.material_bounds_for_origin(mode, 1.0, 1.0)
            )
            context = {
                "mode": mode,
                "enabled": False,
                "x_anchor": 0.0,
                "y_anchor": 0.0,
                "job_width": material_bounds[1] - material_bounds[0],
                "job_height": material_bounds[3] - material_bounds[2],
                "margin_x": 0.0,
                "margin_y": 0.0,
                "material_bounds": material_bounds,
                "placement": self.resolved_job_placement(mode, self.selected_job_placement_mode()),
                "target_bounds": {"X": [0.0, 0.0], "Y": [0.0, 0.0]},
                "absolute": True,
                "units": units,
            }
            return self.finalize_stream_transform_context(context, lines, name, apply_live_placement)

        x_min = bounds.get("X", [0.0, 1.0])[0]
        x_max = bounds.get("X", [0.0, 1.0])[1]
        y_bounds = bounds.get("Y", [0.0, 1.0])
        y_min = y_bounds[0]
        y_max = y_bounds[1]

        # Ensure valid numeric values and a minimum width/height of 1.0 to prevent VisPy Singular Matrix errors
        raw_width = max(1.0, (x_max or 1.0) - (x_min or 0.0))
        raw_height = max(1.0, (y_max or 1.0) - (y_min or 0.0))

        selected_placement = self.selected_job_placement_mode()
        if selected_placement == "canvas":
            # CNCJob objects in FlatCAM already have the canvas offset applied. Keep
            # that placement, but express it in the selected work-origin system.
            if mode == "absolute":
                material_bounds = self.project_workspace_bounds(units) or [x_min, x_max, y_min, y_max]
                x_anchor = 0.0
                y_anchor = 0.0
                context_mode = "absolute"
            else:
                job_width, job_height = self.selected_job_size(raw_width, raw_height, units)
                material_bounds = (
                    self.project_workspace_material_bounds(units, mode) or
                    self.material_bounds_for_origin(mode, job_width, job_height)
                )
                x_anchor = -float(material_bounds[0])
                y_anchor = -float(material_bounds[2])
                context_mode = mode
            context = {
                "mode": context_mode,
                "enabled": True,
                "x_anchor": x_anchor,
                "y_anchor": y_anchor,
                "job_width": material_bounds[1] - material_bounds[0],
                "job_height": material_bounds[3] - material_bounds[2],
                "margin_x": 0.0,
                "margin_y": 0.0,
                "material_bounds": material_bounds,
                "placement": "canvas",
                "target_bounds": {
                    "X": [x_min - x_anchor, x_max - x_anchor],
                    "Y": [y_min - y_anchor, y_max - y_anchor],
                },
                "absolute": True,
                "units": units,
            }
            return self.finalize_stream_transform_context(context, lines, name, apply_live_placement)

        if mode == "absolute":
            material_bounds = self.project_workspace_bounds(units) or [x_min, x_max, y_min, y_max]
            context = {
                "mode": mode,
                "enabled": False,
                "x_anchor": 0.0,
                "y_anchor": 0.0,
                "job_width": material_bounds[1] - material_bounds[0],
                "job_height": material_bounds[3] - material_bounds[2],
                "margin_x": 0.0,
                "margin_y": 0.0,
                "material_bounds": material_bounds,
                "placement": "bottom_left",
                "target_bounds": {
                    "X": [x_min, x_max],
                    "Y": [y_min, y_max],
                },
                "absolute": True,
                "units": units,
            }
            return self.finalize_stream_transform_context(context, lines, name, apply_live_placement)

        job_width, job_height = self.selected_job_size(raw_width, raw_height, units)
        margin_x, margin_y = self.selected_job_margin(units)
        material_bounds = self.material_bounds_for_origin(mode, job_width, job_height)
        placement = self.resolved_job_placement(mode, selected_placement)

        target_bounds = self.target_bounds_for_placement(
            material_bounds, raw_width, raw_height, margin_x, margin_y, placement
        )
        x_anchor = x_min - target_bounds["X"][0]
        y_anchor = y_min - target_bounds["Y"][0]

        context = {
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
        return self.finalize_stream_transform_context(context, lines, name, apply_live_placement)

    @staticmethod
    def format_gcode_number(value):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text not in {"", "-0"} else "0"

    @staticmethod
    def finite_auto_level_float(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def finite_motion_float(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def arc_center_from_radius(start_x, start_y, end_x, end_y, radius_word, clockwise):
        radius = abs(float(radius_word))
        dx = end_x - start_x
        dy = end_y - start_y
        chord = math.hypot(dx, dy)
        if radius <= 0.0 or chord <= 1e-9:
            return None

        half_chord = chord / 2.0
        if radius + 1e-9 < half_chord:
            return None

        mid_x = (start_x + end_x) / 2.0
        mid_y = (start_y + end_y) / 2.0
        height = math.sqrt(max(0.0, (radius * radius) - (half_chord * half_chord)))
        perp_x = -dy / chord
        perp_y = dx / chord
        candidates = [
            (mid_x + perp_x * height, mid_y + perp_y * height),
            (mid_x - perp_x * height, mid_y - perp_y * height),
        ]

        want_large_arc = float(radius_word) < 0.0
        best = None
        for cx, cy in candidates:
            start_angle = math.atan2(start_y - cy, start_x - cx)
            end_angle = math.atan2(end_y - cy, end_x - cx)
            sweep = end_angle - start_angle
            if clockwise and sweep >= 0.0:
                sweep -= 2.0 * math.pi
            elif not clockwise and sweep <= 0.0:
                sweep += 2.0 * math.pi
            is_large_arc = abs(sweep) > math.pi
            if is_large_arc == want_large_arc:
                return cx, cy, sweep
            if best is None:
                best = (cx, cy, sweep)
        return best

    @staticmethod
    def auto_level_map_is_valid(height_map):
        if not isinstance(height_map, dict):
            return False
        x_values = height_map.get("x_values", [])
        y_values = height_map.get("y_values", [])
        z_values = height_map.get("z_values", [])
        if len(x_values) < 2 or len(y_values) < 2:
            return False
        x_values = [ToolCNCControl.finite_auto_level_float(value) for value in x_values]
        y_values = [ToolCNCControl.finite_auto_level_float(value) for value in y_values]
        if any(value is None for value in x_values + y_values):
            return False
        if any(x_values[index] >= x_values[index + 1] for index in range(len(x_values) - 1)):
            return False
        if any(y_values[index] >= y_values[index + 1] for index in range(len(y_values) - 1)):
            return False
        if len(z_values) != len(y_values):
            return False
        for row in z_values:
            if not isinstance(row, list) or len(row) != len(x_values):
                return False
            if any(ToolCNCControl.finite_auto_level_float(value) is None for value in row):
                return False
        return True

    @staticmethod
    def auto_level_map_z_values(height_map):
        if not isinstance(height_map, dict):
            return []
        values = []
        for row_values in height_map.get("z_values", []):
            if not isinstance(row_values, list):
                continue
            for z_value in row_values:
                parsed = ToolCNCControl.finite_auto_level_float(z_value)
                if parsed is not None:
                    values.append(parsed)
        return values

    def active_auto_level_map(self):
        enabled_widget = getattr(self.ui, "autolevel_enable_cb", None)
        enabled = bool(enabled_widget.get_value()) if enabled_widget is not None else False
        if not enabled:
            return None
        if not self.auto_level_map_is_valid(self.auto_level_map):
            return None
        return self.auto_level_map

    def auto_level_context_signature(self, context):
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        target_bounds = self.copy_target_bounds(context.get("target_bounds"))
        if target_bounds:
            bounds_mm = [
                target_bounds["X"][0] * factor,
                target_bounds["X"][1] * factor,
                target_bounds["Y"][0] * factor,
                target_bounds["Y"][1] * factor,
            ]
        else:
            bounds_mm = None

        return {
            "mode": context.get("mode"),
            "placement": context.get("placement"),
            "target_bounds_mm": bounds_mm,
            "live_offset_x_mm": float(context.get("live_offset_x", 0.0) or 0.0) * factor,
            "live_offset_y_mm": float(context.get("live_offset_y", 0.0) or 0.0) * factor,
            "live_rotation": float(context.get("live_rotation", 0.0) or 0.0),
        }

    @staticmethod
    def auto_level_signatures_match(stored_signature, current_signature, tolerance=0.05):
        if not stored_signature or not current_signature:
            return True

        for key in ("mode", "placement"):
            if stored_signature.get(key) != current_signature.get(key):
                return False

        for key in ("live_offset_x_mm", "live_offset_y_mm"):
            try:
                if abs(float(stored_signature.get(key, 0.0)) - float(current_signature.get(key, 0.0))) > tolerance:
                    return False
            except (TypeError, ValueError):
                return False

        try:
            if abs(float(stored_signature.get("live_rotation", 0.0)) -
                   float(current_signature.get("live_rotation", 0.0))) > 0.01:
                return False
        except (TypeError, ValueError):
            return False

        stored_bounds = stored_signature.get("target_bounds_mm")
        current_bounds = current_signature.get("target_bounds_mm")
        if stored_bounds and current_bounds:
            try:
                for stored_value, current_value in zip(stored_bounds, current_bounds):
                    if abs(float(stored_value) - float(current_value)) > tolerance:
                        return False
            except (TypeError, ValueError):
                return False

        return True

    @staticmethod
    def auto_level_map_bounds(height_map):
        try:
            x_values = [float(value) for value in height_map.get("x_values", [])]
            y_values = [float(value) for value in height_map.get("y_values", [])]
        except (TypeError, ValueError):
            return None
        if not x_values or not y_values:
            return None
        return [min(x_values), max(x_values), min(y_values), max(y_values)]

    def auto_level_context_bounds_mm(self, context):
        target_bounds = self.copy_target_bounds(context.get("target_bounds"))
        if not target_bounds:
            return None
        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        return [
            target_bounds["X"][0] * factor,
            target_bounds["X"][1] * factor,
            target_bounds["Y"][0] * factor,
            target_bounds["Y"][1] * factor,
        ]

    def auto_level_map_covers_context(self, height_map, context, tolerance=0.10):
        map_bounds = self.auto_level_map_bounds(height_map)
        job_bounds = self.auto_level_context_bounds_mm(context)
        if not map_bounds or not job_bounds:
            return True, None, None

        covers = (
            map_bounds[0] <= job_bounds[0] + tolerance and
            map_bounds[1] >= job_bounds[1] - tolerance and
            map_bounds[2] <= job_bounds[2] + tolerance and
            map_bounds[3] >= job_bounds[3] - tolerance
        )
        return covers, map_bounds, job_bounds

    def validate_auto_level_context(self, context):
        height_map = context.get("autolevel_map")
        if not height_map:
            return True, ""

        current_signature = self.auto_level_context_signature(context)
        stored_signature = height_map.get("transform_signature")
        if not self.auto_level_signatures_match(stored_signature, current_signature):
            return False, _(
                "Auto level map was made for a different job placement. Click Fit Area and Probe Map again."
            )

        covers, map_bounds, job_bounds = self.auto_level_map_covers_context(height_map, context)
        if not covers:
            return False, _(
                "Auto level map does not cover the mapped job. Map X%.3f..%.3f Y%.3f..%.3f; "
                "job X%.3f..%.3f Y%.3f..%.3f. Click Fit Area and Probe Map again."
            ) % (
                map_bounds[0], map_bounds[1], map_bounds[2], map_bounds[3],
                job_bounds[0], job_bounds[1], job_bounds[2], job_bounds[3],
            )

        return True, ""

    def attach_auto_level_context(self, context):
        height_map = self.active_auto_level_map()
        context["autolevel_enabled"] = height_map is not None
        context["autolevel_map"] = height_map
        context["current_motion"] = None
        return context

    @staticmethod
    def auto_level_bracket(values, value):
        if len(values) < 2:
            return 0, 0
        if value <= values[0]:
            return 0, 1
        if value >= values[-1]:
            return len(values) - 2, len(values) - 1
        for i in range(len(values) - 1):
            if values[i] <= value <= values[i + 1]:
                return i, i + 1
        return len(values) - 2, len(values) - 1

    @staticmethod
    def linear_interpolate(a, b, ratio):
        if a is None and b is None:
            return 0.0
        if a is None:
            return b
        if b is None:
            return a
        return a + ((b - a) * ratio)

    @staticmethod
    def cubic_interpolate(p0, p1, p2, p3, ratio):
        return p1 + 0.5 * ratio * (
            p2 - p0 + ratio * (
                (2.0 * p0) - (5.0 * p1) + (4.0 * p2) - p3 +
                ratio * ((3.0 * (p1 - p2)) + p3 - p0)
            )
        )

    @staticmethod
    def auto_level_sample_z(z_values, row, column):
        row = max(0, min(len(z_values) - 1, row))
        column = max(0, min(len(z_values[row]) - 1, column))
        return float(z_values[row][column])

    def auto_level_bilinear_surface_z(self, x_values, y_values, z_values, x_mm, y_mm):
        x0_idx, x1_idx = self.auto_level_bracket(x_values, x_mm)
        y0_idx, y1_idx = self.auto_level_bracket(y_values, y_mm)
        x0 = x_values[x0_idx]
        x1 = x_values[x1_idx]
        y0 = y_values[y0_idx]
        y1 = y_values[y1_idx]
        x_ratio = 0.0 if x1 == x0 else (x_mm - x0) / (x1 - x0)
        y_ratio = 0.0 if y1 == y0 else (y_mm - y0) / (y1 - y0)
        x_ratio = max(0.0, min(1.0, x_ratio))
        y_ratio = max(0.0, min(1.0, y_ratio))

        z00 = z_values[y0_idx][x0_idx]
        z10 = z_values[y0_idx][x1_idx]
        z01 = z_values[y1_idx][x0_idx]
        z11 = z_values[y1_idx][x1_idx]
        z0 = self.linear_interpolate(z00, z10, x_ratio)
        z1 = self.linear_interpolate(z01, z11, x_ratio)
        return self.linear_interpolate(z0, z1, y_ratio)

    def auto_level_bicubic_surface_z(self, x_values, y_values, z_values, x_mm, y_mm):
        if len(x_values) < 2 or len(y_values) < 2:
            return 0.0

        x0_idx, x1_idx = self.auto_level_bracket(x_values, x_mm)
        y0_idx, y1_idx = self.auto_level_bracket(y_values, y_mm)
        x0 = x_values[x0_idx]
        x1 = x_values[x1_idx]
        y0 = y_values[y0_idx]
        y1 = y_values[y1_idx]
        x_ratio = 0.0 if x1 == x0 else (x_mm - x0) / (x1 - x0)
        y_ratio = 0.0 if y1 == y0 else (y_mm - y0) / (y1 - y0)
        x_ratio = max(0.0, min(1.0, x_ratio))
        y_ratio = max(0.0, min(1.0, y_ratio))

        rows = []
        for row_idx in range(y0_idx - 1, y0_idx + 3):
            values = [
                self.auto_level_sample_z(z_values, row_idx, column_idx)
                for column_idx in range(x0_idx - 1, x0_idx + 3)
            ]
            rows.append(self.cubic_interpolate(values[0], values[1], values[2], values[3], x_ratio))
        return self.cubic_interpolate(rows[0], rows[1], rows[2], rows[3], y_ratio)

    def auto_level_surface_z(self, height_map, x_mm, y_mm):
        x_values = [float(value) for value in height_map["x_values"]]
        y_values = [float(value) for value in height_map["y_values"]]
        z_values = [[float(value) for value in row] for row in height_map["z_values"]]

        interpolation = str(height_map.get("interpolation", "candle_bicubic")).lower()
        if interpolation == "bilinear":
            return self.auto_level_bilinear_surface_z(x_values, y_values, z_values, x_mm, y_mm)
        return self.auto_level_bicubic_surface_z(x_values, y_values, z_values, x_mm, y_mm)

    def auto_level_offset_at(self, context, x_value, y_value):
        height_map = context.get("autolevel_map")
        if not height_map:
            return 0.0

        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        
        # Translate project (unanchored) coordinates to the same work XY used by the probed map.
        x_phys, y_phys = self.mapped_job_xy(context, x_value, y_value)
        
        # z_values are already normalized: reference point = 0.0, other points = delta.
        # surface_z is therefore the Z correction to apply (positive = surface is higher).
        surface_z = self.auto_level_surface_z(height_map, x_phys * factor, y_phys * factor)
        return surface_z / factor

    @staticmethod
    def auto_level_depth_clamped_z(context, program_z, adjusted_z):
        clamp_z = context.get("autolevel_depth_clamp_z")
        if clamp_z is None:
            return adjusted_z

        try:
            program_z = float(program_z)
            adjusted_z = float(adjusted_z)
            clamp_z = float(clamp_z)
        except (TypeError, ValueError):
            return adjusted_z

        if program_z < 0.0 and adjusted_z < clamp_z:
            context["autolevel_depth_clamped_count"] = int(context.get("autolevel_depth_clamped_count", 0) or 0) + 1
            return clamp_z
        return adjusted_z

    def replace_axis_word(self, line, axis, value):
        replacement = "%s%s" % (axis, self.format_gcode_number(value))
        pattern = r"(?<![A-Za-z])%s\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))" % axis
        if re.search(pattern, line, flags=re.IGNORECASE):
            return re.sub(pattern, replacement, line, count=1, flags=re.IGNORECASE)
        return "%s %s" % (line.rstrip(), replacement)

    def zcut_override_comment(self, command, context):
        zcut_override = context.get("zcut_override")
        if zcut_override is None:
            return command
        if "Z_CUT" not in str(command or "").upper():
            return command

        units = self.effective_gcode_units(context.get("units"))
        factor = 25.4 if units == "inch" else 1.0
        zcut_mm = context.get("zcut_override_mm")
        try:
            zcut_mm = float(zcut_mm)
        except (TypeError, ValueError):
            zcut_mm = float(zcut_override) * factor

        match = re.search(r"Z_CUT\s*:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", str(command), flags=re.IGNORECASE)
        if match:
            return "(Z_Cut Override: %.4f mm; original Z_Cut: %s mm)" % (
                zcut_mm,
                match.group(1)
            )
        return "(Z_Cut Override: %.4f mm)" % zcut_mm

    def transform_stream_command(self, command, context):
        clean_line = self.clean_gcode_line(command)
        if not clean_line:
            return self.zcut_override_comment(command, context)

        upper_line = clean_line.upper()
        words = self.gcode_words(upper_line)
        g_code_values = self.raw_g_code_values(upper_line)
        g_codes = self.modal_g_codes(upper_line)
        if 20 in g_codes:
            context["units"] = "inch"
        if 21 in g_codes:
            context["units"] = "mm"
        if 90 in g_codes:
            context["absolute"] = True
        if 91 in g_codes:
            context["absolute"] = False
        if 17 in g_codes:
            context["plane"] = "XY"
        elif 18 in g_codes:
            context["plane"] = "ZX"
        elif 19 in g_codes:
            context["plane"] = "YZ"

        if upper_line.startswith("$") or any(
                math.isclose(code, 10.0) or math.isclose(code, 53.0) or int(code) == 92
                for code in g_code_values
        ):
            return command

        x_anchor = float(context.get("x_anchor", 0.0))
        y_anchor = float(context.get("y_anchor", 0.0))
        controller_wcs_offset = context.get("controller_wcs_offset") or [0.0, 0.0]
        try:
            controller_x_offset = float(controller_wcs_offset[0])
            controller_y_offset = float(controller_wcs_offset[1])
        except (TypeError, ValueError, IndexError):
            controller_x_offset = 0.0
            controller_y_offset = 0.0
        absolute = bool(context.get("absolute", True))
        transformed = clean_line
        modified = False
        axis_values = {}
        position = context.setdefault("position", {"X": None, "Y": None, "Z": None})

        if context.get("enabled") or context.get("apply_controller_wcs") or context.get("live_placement_enabled"):
            l_rot = context.get("live_rotation", 0.0) if context.get("live_placement_enabled") else 0.0
            force_coupled_xy = abs(float(l_rot or 0.0)) > 1e-9

            # 1. Handle X and Y
            new_x = words.get("X")
            new_y = words.get("Y")

            if new_x is not None or new_y is not None:
                # Fill missing values with current tracked position
                curr_x = new_x if new_x is not None else position.get("X")
                curr_y = new_y if new_y is not None else position.get("Y")
                curr_x_f = self.finite_motion_float(curr_x)
                curr_y_f = self.finite_motion_float(curr_y)

                if absolute and curr_x_f is not None and curr_y_f is not None:
                    curr_x, curr_y = self.mapped_job_xy(
                        context, curr_x_f, curr_y_f, controller_x_offset, controller_y_offset
                    )
                else:
                    # Incremental: Only rotate the delta vector
                    if l_rot != 0 and curr_x_f is not None and curr_y_f is not None:
                        rad = math.radians(l_rot)
                        tx, ty = curr_x_f, curr_y_f
                        curr_x = tx * math.cos(rad) - ty * math.sin(rad)
                        curr_y = tx * math.sin(rad) + ty * math.cos(rad)

                if self.finite_motion_float(curr_x) is not None and (new_x is not None or force_coupled_xy):
                    axis_values["X"] = curr_x
                    transformed = self.replace_axis_word(transformed, "X", curr_x)
                    modified = True
                if self.finite_motion_float(curr_y) is not None and (new_y is not None or force_coupled_xy):
                    axis_values["Y"] = curr_y
                    transformed = self.replace_axis_word(transformed, "Y", curr_y)
                    modified = True

            # 2. Handle I and J (Arc centers - always relative deltas)
            if l_rot != 0 and ("I" in words or "J" in words):
                rad = math.radians(l_rot)
                i_val = words.get("I", 0.0)
                j_val = words.get("J", 0.0)
                new_i = i_val * math.cos(rad) - j_val * math.sin(rad)
                new_j = i_val * math.sin(rad) + j_val * math.cos(rad)

                transformed = self.replace_axis_word(transformed, "I", new_i)
                transformed = self.replace_axis_word(transformed, "J", new_j)
                modified = True

        next_position = dict(position)
        for axis in "XYZ":
            if axis in words:
                # Track position in UNANCHORED (project) space
                value = words[axis]
                if absolute:
                    next_position[axis] = value
                else:
                    previous = self.finite_motion_float(position.get(axis))
                    next_position[axis] = value if previous is None else previous + value

        motion = None
        for g_code in g_codes:
            if g_code in [0, 1, 2, 3]:
                motion = g_code
                context["current_motion"] = g_code
        if motion is None:
            motion = context.get("current_motion")

        has_xy = "X" in words or "Y" in words
        has_z = "Z" in words
        program_z = self.finite_motion_float(next_position.get("Z"))
        if program_z is None:
            previous_z = self.finite_motion_float(position.get("Z"))
            program_z = previous_z if previous_z is not None else 0.0
        settle_after_plunge = bool(motion == 1 and has_z and not has_xy and program_z < 0.0)
        zcut_override = context.get("zcut_override")
        zcut_override_applied = False
        if (
                zcut_override is not None and has_z and motion in [1, 2, 3] and
                program_z < 0.0 and (absolute or context.get("autolevel_enabled"))
        ):
            try:
                program_z = float(zcut_override)
                next_position["Z"] = program_z
                zcut_override_applied = True
            except (TypeError, ValueError):
                pass
        settle_after_plunge = bool(motion == 1 and has_z and not has_xy and program_z < 0.0)

        if (
                zcut_override is not None and has_z and motion in [1, 2, 3] and
                program_z < 0.0 and not absolute and not context.get("autolevel_enabled")
        ):
            if not context.get("zcut_incremental_warned"):
                self.append_console_sig.emit(
                    _("Z Cut Override skipped for incremental G91 cutting moves without Auto Level."),
                    "warn"
                )
                context["zcut_incremental_warned"] = True

        if context.get("autolevel_enabled") and (has_xy or has_z):
            # Segment long XY moves for leveling in both G90 and G91 (incremental) modes.
            if has_xy and motion in [0, 1, 2, 3]:
                start_x = self.finite_motion_float(position.get("X"))
                start_y = self.finite_motion_float(position.get("Y"))
                start_z = self.finite_motion_float(position.get("Z"))
                next_x = self.finite_motion_float(next_position.get("X"))
                next_y = self.finite_motion_float(next_position.get("Y"))
                can_subdivide = (
                    start_x is not None and start_y is not None and
                    start_z is not None and next_x is not None and next_y is not None
                )
                
                if motion in [2, 3] and context.get("plane", "XY") != "XY":
                    can_subdivide = False

                if can_subdivide and motion in [0, 1]:
                    dx = next_x - start_x
                    dy = next_y - start_y
                    dist = math.hypot(dx, dy)
                elif can_subdivide:
                    if "R" in words and "I" not in words and "J" not in words:
                        arc = self.arc_center_from_radius(
                            start_x, start_y, next_x, next_y, words["R"], motion == 2
                        )
                        if arc is None:
                            can_subdivide = False
                            dist = 0.0
                        else:
                            cx, cy, angular_dist = arc
                            r = abs(float(words["R"]))
                            start_angle = math.atan2(start_y - cy, start_x - cx)
                    else:
                        i_val = words.get("I", 0.0)
                        j_val = words.get("J", 0.0)
                        cx = start_x + i_val
                        cy = start_y + j_val
                        r = math.hypot(i_val, j_val)
                        start_angle = math.atan2(start_y - cy, start_x - cx)
                        end_angle = math.atan2(next_y - cy, next_x - cx)

                        angular_dist = end_angle - start_angle
                        if abs(angular_dist) < 1e-6 and (abs(i_val) > 1e-6 or abs(j_val) > 1e-6):
                            angular_dist = -2 * math.pi if motion == 2 else 2 * math.pi
                        else:
                            if motion == 2 and angular_dist >= 0:
                                angular_dist -= 2 * math.pi
                            elif motion == 3 and angular_dist <= 0:
                                angular_dist += 2 * math.pi
                    dist = abs(angular_dist) * r if can_subdivide else 0.0
                else:
                    dist = 0.0

                max_seg = 1.0 if context.get("units", "mm") == "mm" else (1.0 / 25.4)
                
                if can_subdivide and (dist > max_seg or motion in [2, 3]):
                    segments = max(1, int(math.ceil(dist / max_seg)))
                    sub_lines = []
                    dz = program_z - start_z
                    
                    for i in range(1, segments + 1):
                        fraction = i / segments
                        if motion in [0, 1]:
                            sub_x = start_x + dx * fraction
                            sub_y = start_y + dy * fraction
                        else:
                            angle = start_angle + angular_dist * fraction
                            sub_x = cx + r * math.cos(angle)
                            sub_y = cy + r * math.sin(angle)
                            
                        sub_z = start_z + dz * fraction
                        
                        # auto_level_offset_at expects UNANCHORED coordinates
                        z_offset = self.auto_level_offset_at(context, sub_x, sub_y)
                        adj_z = sub_z + z_offset
                        adj_z = self.auto_level_depth_clamped_z(context, sub_z, adj_z)

                        # Machine/work coordinates for the sender after job anchoring and live placement.
                        phys_sub_x, phys_sub_y = self.mapped_job_xy(
                            context, sub_x, sub_y, controller_x_offset, controller_y_offset
                        )
                        
                        cmd_motion = 1 if motion in [2, 3] else motion
                        if i == 1:
                            sub_cmd = transformed
                            if motion in [2, 3]:
                                sub_cmd = re.sub(r'G0?[23]', 'G1', sub_cmd)
                                sub_cmd = re.sub(r'[IJR]\s*[-+]?[0-9]*\.?[0-9]*', '', sub_cmd)
                            if "X" in words or self.live_rotation_active(context):
                                sub_cmd = self.replace_axis_word(sub_cmd, "X", phys_sub_x)
                            if "Y" in words or self.live_rotation_active(context):
                                sub_cmd = self.replace_axis_word(sub_cmd, "Y", phys_sub_y)
                            sub_cmd = self.replace_axis_word(sub_cmd, "Z", adj_z)
                            # Cleanup multiple spaces left by I/J removal
                            sub_cmd = re.sub(r'\s+', ' ', sub_cmd).strip()
                        else:
                            sub_cmd = "G%02d X%.4f Y%.4f Z%.4f" % (cmd_motion, phys_sub_x, phys_sub_y, adj_z)
                        sub_lines.append(sub_cmd)

                    context["position"] = next_position
                    if not absolute:
                        # Emitted segments are absolute XY; restore G91 if the source line was incremental.
                        sub_lines[0] = "G90 " + re.sub(r"(?i)^G\s*91(?![\d.])\s+", "", sub_lines[0]).strip()
                        sub_lines.append("G91")
                    return "\n".join(sub_lines)

            # Apply offset to maintain surface following
            next_x = self.finite_motion_float(next_position.get("X"))
            next_y = self.finite_motion_float(next_position.get("Y"))
            if next_x is None or next_y is None:
                context["position"] = next_position
                return transformed if modified else command

            z_offset = self.auto_level_offset_at(context, next_x, next_y)
            adjusted_z = program_z + z_offset
            adjusted_z = self.auto_level_depth_clamped_z(context, program_z, adjusted_z)

            if not absolute:
                inc_transformed = transformed
                if re.search(r"(?i)\bG\s*91(?![\d.])", inc_transformed):
                    inc_transformed = re.sub(r"(?i)\bG\s*91(?![\d.])", "G90", inc_transformed, count=1)
                elif not re.search(r"(?i)\bG\s*90(?![\d.])", inc_transformed):
                    inc_transformed = "G90 " + inc_transformed

                mapped_x, mapped_y = self.mapped_job_xy(
                    context, next_x, next_y,
                    controller_x_offset, controller_y_offset
                )
                force_xy = self.live_rotation_active(context)
                if "X" in words or force_xy:
                    inc_transformed = self.replace_axis_word(
                        inc_transformed,
                        "X",
                        mapped_x
                    )
                if "Y" in words or force_xy:
                    inc_transformed = self.replace_axis_word(
                        inc_transformed,
                        "Y",
                        mapped_y
                    )
                inc_transformed = self.replace_axis_word(inc_transformed, "Z", adjusted_z)
                context["position"] = next_position
                return inc_transformed + "\nG91"

            transformed = self.replace_axis_word(transformed, "Z", adjusted_z)
            modified = True
            
            # Print Z-plunge transformations to console for debugging air-cutting issues
            if program_z < 0.0 and bool(self.app.options.get("cnc_debug_autolevel", False)):
                msg = "[DEBUG-AL] G-code Z: %.3f | Offset: %+.3f | Adjusted Z: %.3f" % (program_z, z_offset, adjusted_z)
                self.append_console_sig.emit(msg, "info")

        elif zcut_override_applied:
            transformed = self.replace_axis_word(transformed, "Z", program_z)
            modified = True

        context["position"] = next_position
        result = transformed if modified else command
        if settle_after_plunge:
            return "%s\nG4 P0.10" % result
        return result

    def transformed_gcode_lines(self, lines, name=None, apply_auto_level=True, apply_live_placement=True):
        if not lines:
            return []
        context = self.stream_transform_context(lines, name=name, apply_live_placement=apply_live_placement)
        if apply_auto_level:
            self.attach_auto_level_context(context)
        transformed = []
        if context.get("autolevel_enabled") and context.get("autolevel_depth_clamp_z_mm") is not None:
            transformed.append(
                "(Auto Level Depth Guard: PCB isolation cutting Z clamped to %.4f mm)" %
                float(context.get("autolevel_depth_clamp_z_mm"))
            )
        transformed.extend(self.transform_stream_command(line, context) for line in lines)
        return transformed

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

            # Dynamic sleep: Poll much faster during active probing to avoid timeouts
            if not self.probe_result_event.is_set():
                time.sleep(0.005)
            else:
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
            if self.is_streaming:
                try:
                    self.stream_ack_queue.put_nowait(lower)
                except Exception:
                    pass

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
        self.set_controller_state(parts[0])
        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                data[key] = value
        self.update_status_sig.emit(data)

    def set_controller_state(self, state):
        new_state = self.normalized_controller_state(state)
        old_state = getattr(self, "controller_state", "Offline")
        self.controller_state = new_state

        with self.jog_lock:
            if self.jog_in_flight and new_state in {"Jog", "Run"}:
                self.jog_motion_seen = True
            should_finish_jog = self.jog_in_flight and self.jog_motion_seen and new_state == "Idle"

        if should_finish_jog:
            self.finish_jog()
        elif old_state != new_state:
            self.jog_controls_update_sig.emit()

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
        self.set_controller_state("Idle")
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
        self.set_controller_state(state)
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
        self.update_live_simulation()

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
        self.stream_mode = "job"
        self.streaming_paused = False
        self.ui.pause_btn.setText("PAUSE")
        self.jog_controls_update_sig.emit()
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
        self.stream_mode = "job"
        self.streaming_paused = False
        self.ui.pause_btn.setText("PAUSE")
        self.jog_controls_update_sig.emit()

        # 1. Immediate motion stop (Feed Hold)
        self.send_profile_command("hold")

        # 2. Reset controller to clear internal hardware buffer
        # (Necessary for GRBL/FluidNC to abort queued moves)
        self.send_profile_command("reset")

        # 3. Stop spindle
        self.send_profile_command("spindle_stop")

        # 4. Lift Z to safe clearance height
        try:
            safe_z = self.simulation_safe_z_value()
            # Unlock if needed (some controllers require $X after soft-reset to allow movement)
            self.send_profile_command("unlock", log=False)
            self.send_command("G21", log=True)
            self.send_command("G90", log=True)
            self.send_command("G0 Z%s" % self.format_gcode_number(safe_z))
        except Exception:
            pass

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

    def clear_stream_ack_queue(self):
        try:
            while True:
                self.stream_ack_queue.get_nowait()
        except queue.Empty:
            pass

    @staticmethod
    def stream_line_length(command):
        return len(str(command or "").rstrip().encode("utf-8", errors="ignore")) + 1

    @staticmethod
    def stream_pause_or_end_code(command):
        clean = ToolCNCControl.clean_gcode_line(command).upper()
        return bool(re.search(r"(?<![A-Z])M0*([026]|30|25)(?!\d)", clean))

    def wait_for_buffered_stream_ack(self, command, timeout=None, warn_after=5.0):
        started = time.time()
        warned = False

        while self.is_streaming and self.is_connected:
            try:
                ack = self.stream_ack_queue.get(timeout=0.1)
            except queue.Empty:
                ack = None

            if ack:
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

    def drain_buffered_stream_ack(self, in_flight, buffer_bytes, sent, total):
        if not in_flight:
            return buffer_bytes, sent, False

        first = in_flight[0]
        if not self.wait_for_buffered_stream_ack(first["command"], timeout=900.0, warn_after=5.0):
            return buffer_bytes, sent, True

        in_flight.pop(0)
        buffer_bytes = max(0, buffer_bytes - first["length"])
        sent += 1
        self.update_progress_sig.emit((sent / total * 100.0) if total else 0.0, first["command"])
        return buffer_bytes, sent, False

    def stream_lines_unbuffered(self, stream_lines, total, sent):
        for line_idx, sent_command in enumerate(stream_lines):
            if not self.is_streaming:
                return sent, True

            while self.streaming_paused and self.is_streaming:
                time.sleep(0.1)

            self.current_line_idx = line_idx
            self.ok_received.clear()
            if not str(sent_command).strip():
                continue
            self.last_controller_ack = ""
            self.send_command(sent_command, log=True)
            if not self.wait_for_stream_ack(sent_command, timeout=900.0, warn_after=5.0):
                return sent, True
            sent += 1
            self.update_progress_sig.emit((sent / total * 100.0) if total else 0.0, sent_command)

        return sent, False

    def stream_lines_buffered(self, stream_lines, total, sent):
        if isinstance(self.transport, HttpTransport):
            return self.stream_lines_unbuffered(stream_lines, total, sent)

        self.clear_stream_ack_queue()
        self.ok_received.clear()
        self.last_controller_ack = ""

        in_flight = []
        buffer_bytes = 0
        buffer_limit = max(32, int(self.stream_buffer_length or 127))

        for line_idx, sent_command in enumerate(stream_lines):
            if not self.is_streaming:
                return sent, True

            command = str(sent_command or "").strip()
            if not command:
                continue

            while self.streaming_paused and self.is_streaming:
                time.sleep(0.1)
            if not self.is_streaming:
                return sent, True

            command_len = self.stream_line_length(command)
            while in_flight and (buffer_bytes + command_len) > buffer_limit:
                buffer_bytes, sent, aborted = self.drain_buffered_stream_ack(
                    in_flight, buffer_bytes, sent, total
                )
                if aborted:
                    return sent, True

            self.current_line_idx = line_idx
            self.send_command(command, log=True)
            if not self.is_connected:
                return sent, True

            in_flight.append({
                "command": command,
                "length": command_len,
                "line_idx": line_idx,
            })
            buffer_bytes += command_len

            if self.stream_pause_or_end_code(command):
                while in_flight:
                    buffer_bytes, sent, aborted = self.drain_buffered_stream_ack(
                        in_flight, buffer_bytes, sent, total
                    )
                    if aborted:
                        return sent, True

        while in_flight:
            buffer_bytes, sent, aborted = self.drain_buffered_stream_ack(
                in_flight, buffer_bytes, sent, total
            )
            if aborted:
                return sent, True

        return sent, False

    def stream_worker(self):
        total = sum(len(item.get("lines", [])) for item in self.job_queue)
        sent = 0
        stream_aborted = False
        previous_status_poll = self.status_poll_enabled
        if not self.current_profile().get("status_raw") or isinstance(self.transport, HttpTransport):
            self.status_poll_enabled = False
        for job_idx, item in enumerate(self.job_queue):
            if not self.is_streaming:
                break

            self.current_queue_idx = job_idx
            item["status"] = _("Running")
            self.queue_update_sig.emit()

            lines = item.get("lines", [])

            wcs_label, _p_num = self.selected_work_offset()
            transform_context = self.stream_transform_context(lines, name=item.get("name"))
            self.attach_auto_level_context(transform_context)
            wcs_ready = False

            if transform_context.get("autolevel_enabled"):
                auto_level_ok, auto_level_message = self.validate_auto_level_context(transform_context)
                if not auto_level_ok:
                    self.append_console_sig.emit(auto_level_message, "error")
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    stream_aborted = True
                    break

                setup_commands = ["G90", "G92.1", "G49", wcs_label]
                self.work_offsets = {}
                self.g92_offset = [0.0, 0.0, 0.0]
                self.tool_length_offset = [0.0, 0.0, 0.0]

                for setup_command in setup_commands:
                    self.ok_received.clear()
                    self.last_controller_ack = ""
                    self.send_command(setup_command, log=True)
                    if not self.wait_for_stream_ack(setup_command, timeout=10.0):
                        item["status"] = _("Stopped")
                        self.queue_update_sig.emit()
                        stream_aborted = True
                        break

                if stream_aborted:
                    break

                self.ok_received.clear()
                self.last_controller_ack = ""
                self.send_command("$#", log=True)
                if not self.wait_for_stream_ack("$#", timeout=10.0):
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    stream_aborted = True
                    break

                wcs_ready = True
                self.append_console_sig.emit(
                    _("Auto level XY uses selected %s work coordinates.") % wcs_label,
                    "info"
                )
            
            # Candle starts parsing with unknown XYZ. Keep the sender transform
            # in that same model so preview and real streaming are generated
            # from the same G-code state, not from the controller's live DRO.
            transform_context["position"] = {"X": None, "Y": None, "Z": None}
            
            raw_stream_lines = [
                self.transform_stream_command(command, transform_context)
                for command in lines
            ]
            stream_lines = []
            for cmd in raw_stream_lines:
                if cmd:
                    stream_lines.extend(str(cmd).split('\n'))

            # Log transform/auto-level info BEFORE sending WCS to avoid blocking the send loop.
            if transform_context.get("enabled"):
                mode_labels = {
                    "top_left": _("Back-Left"),
                    "bottom_left": _("Bottom-Left"),
                    "center": _("Center"),
                }
                mode_label = mode_labels.get(transform_context.get("mode"), _("Job Origin"))
                placement_label = self.job_placement_label(transform_context.get("placement"))
                if transform_context.get("placement") == "canvas":
                    self.append_console_sig.emit(
                        _("CNCJob uses its canvas XY; saved Live Placement offset/rotation is applied."),
                        "info"
                    )
                else:
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
            if transform_context.get("zcut_override") is not None:
                try:
                    zcut_mm = float(transform_context.get("zcut_override_mm"))
                except (TypeError, ValueError):
                    zcut_mm = float(transform_context.get("zcut_override")) * (
                        25.4 if self.effective_gcode_units(transform_context.get("units")) == "inch" else 1.0
                    )
                if transform_context.get("autolevel_enabled"):
                    self.append_console_sig.emit(
                        _("Z Cut Override active: base cut Z %.4f mm. Sent Z values include Auto Level surface correction, so they will vary.") % zcut_mm,
                        "info"
                    )
                else:
                    self.append_console_sig.emit(
                        _("Z Cut Override active: cutting Z moves use %.4f mm.") % zcut_mm,
                        "info"
                    )
                for level, _line_no, message in self.zcut_override_warnings(lines, zcut_mm):
                    self.append_console_sig.emit(message, "warn" if level == "WARN" else "info")
            if transform_context.get("autolevel_enabled") and transform_context.get("autolevel_depth_clamp_z_mm") is not None:
                self.append_console_sig.emit(
                    _("PCB isolation depth guard active: Auto Level will not command cutting Z below %.4f mm. "
                      "This prevents V-bit isolation from becoming wider than the generated tool diameter.") %
                    float(transform_context.get("autolevel_depth_clamp_z_mm")),
                    "warn"
                )
            if transform_context.get("autolevel_enabled"):
                height_map = transform_context.get("autolevel_map", {})
                z_values = self.auto_level_map_z_values(height_map)
                mode_label = height_map.get("probe_coordinate_mode") or _("unknown")
                if any(abs(float(value or 0.0)) > 0.0005 for value in (self.g92_offset or [])):
                    self.append_console_sig.emit(
                        _("Warning: G92 temporary offset is active while auto-level is enabled. "
                          "Clear G92 or re-probe before engraving if Z depth looks wrong."),
                        "warn"
                    )
                if z_values:
                    self.append_console_sig.emit(
                        _("Auto level map is active: %d points. Delta Z range %.4f..%.4f mm; interpolation: %s; probe mode: %s.") % (
                            int(height_map.get("point_count", 0) or 0),
                            min(z_values),
                            max(z_values),
                            height_map.get("interpolation", "candle_bicubic"),
                            mode_label
                        ),
                        "info"
                    )
                else:
                    self.append_console_sig.emit(
                        _("Auto level map is active: %d points.") % int(height_map.get("point_count", 0) or 0),
                        "info"
                    )
                tb = transform_context.get("target_bounds")
                xv = height_map.get("x_values") or []
                yv = height_map.get("y_values") or []
                if tb and xv and yv:
                    mx0, mx1 = min(xv), max(xv)
                    my0, my1 = min(yv), max(yv)
                    jx0, jx1 = tb["X"][0], tb["X"][1]
                    jy0, jy1 = tb["Y"][0], tb["Y"][1]
                    tol = 0.05
                    covers = (
                        mx0 <= jx0 + tol and mx1 >= jx1 - tol and
                        my0 <= jy0 + tol and my1 >= jy1 - tol
                    )
                    if covers:
                        self.append_console_sig.emit(
                            _("Auto level: probe map XY covers the mapped job."), "info"
                        )
                    else:
                        self.append_console_sig.emit(
                            _("Auto level: map X%.3f..%.3f Y%.3f..%.3f may be smaller than job X%.3f..%.3f Y%.3f..%.3f — re-run Fit Area if needed.") % (
                                mx0, mx1, my0, my1, jx0, jx1, jy0, jy1
                            ),
                            "warn"
                        )

            # Non-leveled jobs only need the selected work offset before streaming.
            if not wcs_ready:
                self.ok_received.clear()
                self.last_controller_ack = ""
                self.send_command(wcs_label, log=True)
                if not self.wait_for_stream_ack(wcs_label, timeout=10.0):
                    item["status"] = _("Stopped")
                    self.queue_update_sig.emit()
                    stream_aborted = True

            if stream_aborted:
                break

            total = max(total, sent + len([line for line in stream_lines if str(line).strip()]))
            sent, stream_aborted = self.stream_lines_buffered(stream_lines, total, sent)
            if stream_aborted:
                item["status"] = _("Stopped")
                self.queue_update_sig.emit()

            if stream_aborted:
                break

            if self.is_streaming:
                item["status"] = _("Done")
                self.queue_update_sig.emit()

        completed = self.is_streaming and not stream_aborted
        self.is_streaming = False
        self.status_poll_enabled = previous_status_poll
        self.streaming_paused = False
        self.current_queue_idx = -1
        self.stream_mode = "job"
        self.jog_controls_update_sig.emit()
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





    def on_full_screen_preview(self):
        if not hasattr(self, 'preview_modal'):
            self.preview_modal = CNCPreviewModal(self.app.ui)
        
        # Get current preview data
        name, lines = self.selected_preview_job()
        preview_lines = self.transformed_gcode_lines(lines, name=name)
        canvas_preview = self.build_job_canvas_preview(name, lines, preview_lines)

        self.preview_modal.canvas.edit_mode = False
        self.preview_modal.set_placement(0.0, 0.0, 0.0)
        self.preview_modal.set_preview(canvas_preview)
        self.preview_modal.show()

    def update_live_simulation(self):
        try:
            wpos = {'X': float(self.ui.x_val.text()), 'Y': float(self.ui.y_val.text()), 'Z': float(self.ui.z_val.text())}
            if hasattr(self.ui, 'live_simulation_canvas'):
                self.ui.live_simulation_canvas.preview['live_pos'] = wpos
                self.ui.live_simulation_canvas.update()
            if hasattr(self, 'preview_modal') and self.preview_modal.isVisible():
                self.preview_modal.canvas.preview['live_pos'] = wpos
                self.preview_modal.canvas.update()
        except Exception: pass


