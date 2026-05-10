# ##########################################################
# FlatCAM PLUS: CNC 3D Preview Plugin                     #
# File Updated By Sadri ERCAN - 2026                      #
# License:  FlatCAM Plus CNC 3D Preview Module Non-Commercial License #
# See:      appPlugins/cnc_preview_3d/LICENSE             #
# ##########################################################

import builtins
import gettext

from PyQt6 import QtWidgets

from appTool import AppTool
from appPlugins.cnc_preview_3d.ui import CNCPreview3DUI

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class ToolCNCPreview3D(AppTool):
    def __init__(self, app):
        self.app = app
        AppTool.__init__(self, app)
        self.ui = None
        self.pluginName = CNCPreview3DUI.pluginName

    def ensure_ui(self):
        if self.ui is not None:
            return
        self.ui = CNCPreview3DUI(layout=self.layout, app=self.app)
        self.connect_signals_at_init()

    def run(self, toggle=True):
        self.ensure_ui()
        tab_exists = False
        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == self.pluginName:
                self.app.ui.plot_tab_area.setCurrentIndex(idx)
                tab_exists = True
                break

        if not tab_exists:
            self.app.ui.plot_tab_area.addTab(self, self.pluginName)
            self.app.ui.plot_tab_area.setCurrentIndex(self.app.ui.plot_tab_area.count() - 1)

        self.update_job_list()
        self.render_selected_job()

    def connect_signals_at_init(self):
        self.ui.refresh_btn.clicked.connect(self.on_refresh_clicked)
        self.ui.job_combo.currentIndexChanged.connect(lambda *_args: self.render_selected_job())
        self.ui.top_btn.clicked.connect(self.ui.canvas.set_top_view)
        self.ui.fit_btn.clicked.connect(self.ui.canvas.fit_current_view)
        self.ui.orbit_btn.viewRequested.connect(self.on_gizmo_view_requested)

    def on_refresh_clicked(self):
        self.update_job_list()
        self.render_selected_job()

    def on_gizmo_view_requested(self, view_name):
        self.ui.canvas.set_named_view(view_name)

    def update_job_list(self):
        current_name = self.ui.job_combo.currentText().strip()
        self.ui.job_combo.blockSignals(True)
        try:
            self.ui.job_combo.clear()
            for obj in self.app.collection.get_list():
                if getattr(obj, "kind", None) == "cncjob":
                    name = obj.obj_options.get("name", "")
                    if name:
                        self.ui.job_combo.addItem(name, name)
            if current_name:
                idx = self.ui.job_combo.findText(current_name)
                if idx >= 0:
                    self.ui.job_combo.setCurrentIndex(idx)
        finally:
            self.ui.job_combo.blockSignals(False)

    def selected_job(self):
        name = self.ui.job_combo.currentData() or self.ui.job_combo.currentText().strip()
        if not name:
            return None
        return self.app.collection.get_by_name(name)

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
                self.app.log.warning("CNC 3D Preview export fallback failed: %s" % str(err))

        return self.gcode_text_from_source(getattr(obj, "gcode", ""))

    @staticmethod
    def cncjob_tool_diameter(obj):
        diameters = []
        for tool in getattr(obj, "tools", {}).values():
            data = tool.get("data", {}) if isinstance(tool, dict) else {}
            for key in ["tools_mill_tooldia", "tooldia", "tool_dia", "tools_drill_tooldia"]:
                value = data.get(key) if isinstance(data, dict) else None
                if value is None and isinstance(tool, dict):
                    value = tool.get(key)
                try:
                    if value not in [None, ""]:
                        diameters.append(float(str(value).replace(",", ".")))
                        break
                except (TypeError, ValueError):
                    continue

        for key in ["tools_mill_tooldia", "tooldia", "tool_dia", "tools_drill_tooldia"]:
            value = getattr(obj, "obj_options", {}).get(key)
            try:
                if value not in [None, ""]:
                    diameters.append(float(str(value).replace(",", ".")))
            except (TypeError, ValueError):
                continue

        return max(min(diameters), 0.001) if diameters else None

    def render_selected_job(self):
        obj = self.selected_job()
        if obj is None:
            self.ui.canvas.clear_preview()
            self.ui.set_status(_("No CNCJob object selected."))
            return
        if getattr(obj, "kind", None) != "cncjob":
            self.ui.canvas.clear_preview()
            self.ui.set_status(_("Selected object is not a CNCJob."))
            return

        gcode = self.cncjob_gcode_text(obj)
        if not gcode.strip():
            self.ui.canvas.clear_preview()
            self.ui.set_status(_("Selected CNCJob has no G-code to preview."))
            return

        result = self.ui.canvas.render_job(
            obj.obj_options.get("name", _("CNCJob")),
            gcode,
            tool_dia=self.cncjob_tool_diameter(obj),
            job_type=obj.obj_options.get("type")
        )
        self.ui.update_stats(result)
        try:
            self.app.inform.emit(
                "[success] %s: %s (%d %s, %d %s)" % (
                    _("CNC 3D Preview"),
                    result.get("name", ""),
                    result.get("cut_count", 0),
                    _("cut paths"),
                    result.get("drill_count", 0),
                    _("drills")
                )
            )
        except Exception:
            pass
