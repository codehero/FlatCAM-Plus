# ##########################################################
# FlatCAM PLUS: AI Assistant Plugin                        #
# File Updated By Sadri ERCAN - 2026                       #
# License:  FlatCAM Plus AI Assistant Module Non-Commercial License #
# See:      appPlugins/ai_assistant/LICENSE                #
# ##########################################################

import builtins
import gettext
import threading

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal

from appGUI.GUIElements import VerticalScrollArea
from appTool import AppTool
from appPlugins.ai_assistant.dialogs import AIAssistantSettingsDialog
from appPlugins.ai_assistant.providers import default_settings, provider_spec, request_completion, test_connection
from appPlugins.ai_assistant.ui import AIAssistantUI

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class ToolAIAssistant(AppTool):
    append_chat_sig = pyqtSignal(str, str)
    busy_sig = pyqtSignal(bool, str)
    provider_status_sig = pyqtSignal(bool, str)
    context_summary_sig = pyqtSignal(str)
    worker_success_sig = pyqtSignal(object, object)
    worker_error_sig = pyqtSignal(object, str)

    def __init__(self, app):
        self.app = app
        AppTool.__init__(self, app)

        self.ui = AIAssistantUI(layout=self.layout, app=self.app)
        self.settings_dialog = AIAssistantSettingsDialog(app=self.app, parent=self.app.ui)
        self.pluginName = self.ui.pluginName
        self.settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
        self.current_provider_id = ""
        self.chat_history = []
        self._worker_lock = threading.Lock()

        self.connect_signals_at_init()
        self.load_initial_settings()
        self.refresh_object_list()
        self.update_scope_controls()
        self.update_context_labels()
        self.append_welcome_message()

    def connect_signals_at_init(self):
        self.ui.send_btn.clicked.connect(self.on_send_clicked)
        self.ui.clear_chat_btn.clicked.connect(self.on_clear_chat_clicked)

        self.settings_dialog.provider_combo.currentIndexChanged.connect(lambda *_args: self.on_provider_changed())
        self.settings_dialog.scope_combo.currentIndexChanged.connect(lambda *_args: self.on_scope_changed())
        self.settings_dialog.object_combo.currentIndexChanged.connect(lambda *_args: self.update_context_labels())
        self.settings_dialog.refresh_context_btn.clicked.connect(self.on_refresh_context_clicked)
        self.settings_dialog.save_settings_btn.clicked.connect(self.save_current_provider_settings)
        self.settings_dialog.save_footer_btn.clicked.connect(self.save_current_provider_settings)
        self.settings_dialog.test_connection_btn.clicked.connect(self.on_test_connection_clicked)
        self.settings_dialog.test_footer_btn.clicked.connect(self.on_test_connection_clicked)
        self.settings_dialog.analyze_btn.clicked.connect(self.on_summarize_clicked)

        self.append_chat_sig.connect(self.ui.append_chat_message)
        self.busy_sig.connect(self.ui.set_busy)
        self.provider_status_sig.connect(self.on_provider_status_changed)
        self.context_summary_sig.connect(self.settings_dialog.context_summary_label.setText)
        self.worker_success_sig.connect(self._finish_async)
        self.worker_error_sig.connect(self._finish_async)

        collection = getattr(self.app, "collection", None)
        if collection is not None and hasattr(collection, "item_selected"):
            collection.item_selected.connect(lambda *_args: self.update_context_labels())

    def append_welcome_message(self):
        if self.ui.chat_view.toPlainText().strip():
            return
        self.ui.append_chat_message(
            "assistant",
            _("Select a provider, test the connection, then ask about the current project or the object on the canvas.")
        )

    def open_settings_dialog(self):
        self.refresh_object_list()
        self.update_scope_controls()
        self.update_context_labels()
        self.settings_dialog.exec()

    def run(self, toggle=True):
        if self.app.plugin_tab_locked is True:
            return

        if toggle:
            if self.app.ui.splitter.sizes()[0] == 0:
                self.app.ui.splitter.setSizes([1, 1])

            found_idx = None
            for idx in range(self.app.ui.notebook.count()):
                if self.app.ui.notebook.widget(idx).objectName() == "plugin_tab":
                    found_idx = idx
                    break

            if found_idx is None:
                try:
                    self.app.ui.notebook.addTab(self.app.ui.plugin_tab, _("Plugin"))
                except RuntimeError:
                    self.app.ui.plugin_tab = QtWidgets.QWidget()
                    self.app.ui.plugin_tab.setObjectName("plugin_tab")
                    self.app.ui.plugin_tab_layout = QtWidgets.QVBoxLayout(self.app.ui.plugin_tab)
                    self.app.ui.plugin_tab_layout.setContentsMargins(2, 2, 2, 2)

                    self.app.ui.plugin_scroll_area = VerticalScrollArea()
                    self.app.ui.plugin_tab_layout.addWidget(self.app.ui.plugin_scroll_area)
                    self.app.ui.notebook.addTab(self.app.ui.plugin_tab, _("Plugin"))
                self.app.ui.notebook.setCurrentWidget(self.app.ui.plugin_tab)

            try:
                current_widget = self.app.ui.plugin_scroll_area.widget()
                if current_widget is not None and current_widget.objectName() == self.pluginName and found_idx is not None:
                    if self.app.ui.notebook.currentWidget() is not self.app.ui.plugin_tab:
                        self.app.ui.notebook.setCurrentWidget(self.app.ui.plugin_tab)
                    else:
                        self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)
                        self.app.ui.notebook.removeTab(2)
                        if not self.app.collection.get_list():
                            self.app.ui.splitter.setSizes([0, 1])
                        return
            except AttributeError:
                pass
        else:
            if self.app.ui.splitter.sizes()[0] == 0:
                self.app.ui.splitter.setSizes([1, 1])

        self.refresh_object_list()
        self.update_scope_controls()
        self.update_context_labels()
        super().run()
        self.app.ui.notebook.setTabText(2, self.pluginName)

    def load_initial_settings(self):
        provider_id = self.settings.value("plugin_ai_assistant/current_provider", "openai", type=str)
        index = self.settings_dialog.provider_combo.findData(provider_id)
        if index < 0:
            index = 0
        self.settings_dialog.provider_combo.blockSignals(True)
        self.settings_dialog.provider_combo.setCurrentIndex(index)
        self.settings_dialog.provider_combo.blockSignals(False)
        self.current_provider_id = self.settings_dialog.provider_combo.currentData()
        self.load_provider_settings(self.current_provider_id)
        self.update_provider_details()

    def on_provider_changed(self):
        previous_provider = self.current_provider_id
        if previous_provider:
            self._store_provider_settings(previous_provider)
        self.current_provider_id = self.settings_dialog.provider_combo.currentData()
        self.load_provider_settings(self.current_provider_id)
        self.update_provider_details()

    def update_provider_details(self):
        provider_id = self.settings_dialog.provider_combo.currentData()
        spec = provider_spec(provider_id)
        note = _("%s endpoint and model settings for FlatCAM project analysis.") % spec["label"]
        self.settings_dialog.set_provider_details(
            label_text=note,
            api_key_label=spec["api_key_label"],
            endpoint_placeholder=spec["base_url"],
            model_placeholder=spec["model"] or _("Enter model name")
        )

    def load_provider_settings(self, provider_id):
        stored = default_settings(provider_id)
        prefix = "plugin_ai_assistant/%s/" % provider_id
        stored["base_url"] = self.settings.value(prefix + "base_url", stored["base_url"], type=str)
        stored["model"] = self.settings.value(prefix + "model", stored["model"], type=str)
        stored["api_key"] = self.settings.value(prefix + "api_key", stored["api_key"], type=str)
        stored["timeout"] = self.settings.value(prefix + "timeout", stored["timeout"], type=int)
        stored["temperature"] = self.settings.value(prefix + "temperature", stored["temperature"], type=float)
        stored["system_prompt"] = self.settings.value(
            prefix + "system_prompt",
            _("You are an expert PCB and CAM assistant inside FlatCAM. Use the provided object and project context to answer precisely."),
            type=str
        )

        self.settings_dialog.endpoint_entry.setText(stored["base_url"])
        self.settings_dialog.model_entry.setText(stored["model"])
        self.settings_dialog.api_key_entry.setText(stored["api_key"])
        self.settings_dialog.timeout_spin.setValue(int(stored["timeout"]))
        self.settings_dialog.temperature_spin.setValue(float(stored["temperature"]))
        self.settings_dialog.system_prompt_entry.setPlainText(stored["system_prompt"])

    def save_current_provider_settings(self):
        provider_id = self.settings_dialog.provider_combo.currentData()
        self._store_provider_settings(provider_id)
        self.settings.setValue("plugin_ai_assistant/current_provider", provider_id)
        self.settings_dialog.provider_status_label.setText(
            _("Settings saved for %s.") % provider_spec(provider_id)["label"]
        )

    def _store_provider_settings(self, provider_id):
        prefix = "plugin_ai_assistant/%s/" % provider_id
        self.settings.setValue(prefix + "base_url", self.settings_dialog.endpoint_entry.text().strip())
        self.settings.setValue(prefix + "model", self.settings_dialog.model_entry.text().strip())
        self.settings.setValue(prefix + "api_key", self.settings_dialog.api_key_entry.text())
        self.settings.setValue(prefix + "timeout", int(self.settings_dialog.timeout_spin.value()))
        self.settings.setValue(prefix + "temperature", float(self.settings_dialog.temperature_spin.value()))
        self.settings.setValue(prefix + "system_prompt", self.settings_dialog.system_prompt_entry.toPlainText().strip())

    def current_provider_settings(self):
        return {
            "provider": self.settings_dialog.provider_combo.currentData(),
            "base_url": self.settings_dialog.endpoint_entry.text().strip(),
            "model": self.settings_dialog.model_entry.text().strip(),
            "api_key": self.settings_dialog.api_key_entry.text(),
            "timeout": int(self.settings_dialog.timeout_spin.value()),
            "temperature": float(self.settings_dialog.temperature_spin.value()),
        }

    def on_scope_changed(self):
        self.update_scope_controls()
        self.update_context_labels()

    def update_scope_controls(self):
        self.settings_dialog.set_scope_controls_enabled()

    def refresh_object_list(self):
        current_object_name = self.settings_dialog.object_combo.currentData()
        self.settings_dialog.object_combo.blockSignals(True)
        self.settings_dialog.object_combo.clear()
        collection = getattr(self.app, "collection", None)
        if collection is not None:
            for obj in collection.get_list():
                name = obj.obj_options.get("name", "")
                label = "%s (%s)" % (name, getattr(obj, "kind", "object"))
                self.settings_dialog.object_combo.addItem(label, name)
        if current_object_name:
            idx = self.settings_dialog.object_combo.findData(current_object_name)
            if idx >= 0:
                self.settings_dialog.object_combo.setCurrentIndex(idx)
        self.settings_dialog.object_combo.blockSignals(False)
        self.update_context_labels()

    def on_refresh_context_clicked(self):
        self.refresh_object_list()
        self.context_summary_sig.emit(self.context_summary_text())

    def current_canvas_object(self):
        plot_tab_area = getattr(self.app.ui, "plot_tab_area", None)
        collection = getattr(self.app, "collection", None)
        if plot_tab_area is None or collection is None:
            return None
        index = plot_tab_area.currentIndex()
        if index < 0:
            return None
        tab_name = plot_tab_area.tabText(index).strip()
        if not tab_name:
            return None
        return collection.get_by_name(tab_name, isCaseSensitive=False)

    def selected_object(self):
        collection = getattr(self.app, "collection", None)
        if collection is None:
            return None
        return collection.get_active()

    def named_object(self):
        name = self.settings_dialog.object_combo.currentData() or self.settings_dialog.object_combo.currentText()
        if not name:
            return None
        return self.app.collection.get_by_name(name, isCaseSensitive=False)

    def object_for_scope(self, scope):
        if scope == "canvas":
            return self.current_canvas_object()
        if scope == "selected":
            return self.selected_object()
        if scope == "named":
            return self.named_object()
        return None

    def update_context_labels(self):
        canvas_obj = self.current_canvas_object()
        selected_obj = self.selected_object()
        self.settings_dialog.current_canvas_label.setText(
            _("Current canvas object: %s") % (canvas_obj.obj_options["name"] if canvas_obj else _("none"))
        )
        self.settings_dialog.selection_label.setText(
            _("Selected object: %s") % (selected_obj.obj_options["name"] if selected_obj else _("none"))
        )
        self.settings_dialog.context_summary_label.setText(self.context_summary_text())

    def context_summary_text(self):
        scope = self.settings_dialog.scope_combo.currentData()
        if scope == "project":
            obj_count = len(self.app.collection.get_list()) if getattr(self.app, "collection", None) else 0
            return _("Project context selected. %d loaded object(s) will be summarized.") % obj_count
        obj = self.object_for_scope(scope)
        if obj is None:
            return _("No object is currently available for the selected context.")
        return _("Context will use %s (%s).") % (obj.obj_options.get("name", _("unnamed")), getattr(obj, "kind", "object"))

    def on_test_connection_clicked(self):
        self.save_current_provider_settings()
        provider_id = self.settings_dialog.provider_combo.currentData()
        settings = self.current_provider_settings()
        self.run_in_thread(
            busy_message=_("Testing provider connection..."),
            worker=lambda: test_connection(provider_id, settings),
            on_success=self.on_connection_test_success,
            on_error=self.on_async_error
        )

    def on_connection_test_success(self, result):
        ok, details = result
        self.provider_status_sig.emit(ok, details)

    def on_provider_status_changed(self, ok, details):
        if ok:
            self.settings_dialog.provider_status_label.setText(_("Connection OK. Models: %s") % details)
        else:
            self.settings_dialog.provider_status_label.setText(_("Connection failed: %s") % details)

    def on_summarize_clicked(self):
        self.settings_dialog.accept()
        self.run(toggle=False)
        self.ui.prompt_entry.setPlainText(
            _("Analyze this context. Summarize the PCB/CAM structure, likely manufacturing risks, and the next recommended steps.")
        )
        self.on_send_clicked()

    def on_send_clicked(self):
        user_prompt = self.ui.prompt_entry.toPlainText().strip()
        if not user_prompt:
            self.ui.chat_status_label.setText(_("Enter a message first."))
            return

        self.save_current_provider_settings()
        provider_id = self.settings_dialog.provider_combo.currentData()
        settings = self.current_provider_settings()

        try:
            context_text = self.build_context_text()
        except Exception as exc:
            self.ui.chat_status_label.setText(str(exc))
            return

        self.append_chat_sig.emit("user", user_prompt)
        self.ui.prompt_entry.clear()

        history = list(self.chat_history)
        system_prompt = self.settings_dialog.system_prompt_entry.toPlainText().strip() or _(
            "You are an expert PCB and CAM assistant inside FlatCAM. Use the provided object and project context to answer precisely."
        )

        def worker():
            return request_completion(
                provider_id=provider_id,
                settings=settings,
                system_prompt=system_prompt,
                context_text=context_text,
                history=history,
                user_prompt=user_prompt
            )

        self.run_in_thread(
            busy_message=_("Waiting for AI response..."),
            worker=worker,
            on_success=lambda reply: self.on_chat_success(user_prompt, reply),
            on_error=self.on_async_error
        )

    def on_chat_success(self, user_prompt, reply):
        self.chat_history.append({"role": "user", "content": user_prompt})
        self.chat_history.append({"role": "assistant", "content": reply})
        self.chat_history = self.chat_history[-12:]
        self.append_chat_sig.emit("assistant", reply)
        self.ui.chat_status_label.setText(_("Reply received."))

    def on_clear_chat_clicked(self):
        self.chat_history = []
        self.ui.chat_view.clear()
        self.append_welcome_message()
        self.ui.chat_status_label.setText(_("Chat cleared."))

    def build_context_text(self):
        scope = self.settings_dialog.scope_combo.currentData()
        collection = getattr(self.app, "collection", None)
        if collection is None:
            raise RuntimeError(_("No FlatCAM collection is available."))

        if scope == "project":
            objects = collection.get_list()
            if not objects:
                raise RuntimeError(_("There are no loaded objects in the current project."))
            parts = [
                "Scope: current project",
                "Loaded object count: %d" % len(objects),
            ]
            current_tab = self.current_canvas_object()
            selected_obj = self.selected_object()
            if current_tab is not None:
                parts.append("Current canvas object: %s" % current_tab.obj_options.get("name", ""))
            if selected_obj is not None:
                parts.append("Selected object: %s" % selected_obj.obj_options.get("name", ""))
            parts.append("")
            for obj in objects:
                include_source = False
                if current_tab is not None and obj.obj_options.get("name") == current_tab.obj_options.get("name"):
                    include_source = True
                elif selected_obj is not None and obj.obj_options.get("name") == selected_obj.obj_options.get("name"):
                    include_source = True
                parts.append(self.describe_object(obj, include_source=include_source, source_limit=2200))
            return "\n\n".join(parts)

        obj = self.object_for_scope(scope)
        if obj is None:
            raise RuntimeError(_("No object is available for the selected context."))
        return "Scope: %s\n\n%s" % (scope, self.describe_object(obj, include_source=True, source_limit=5000))

    def describe_object(self, obj, include_source=False, source_limit=3000):
        lines = [
            "Object: %s" % obj.obj_options.get("name", ""),
            "Kind: %s" % getattr(obj, "kind", "object"),
        ]

        bounds = self.object_bounds(obj)
        if bounds is not None:
            xmin, ymin, xmax, ymax = bounds
            width = xmax - xmin
            height = ymax - ymin
            lines.append("Bounds: xmin=%.4f ymin=%.4f xmax=%.4f ymax=%.4f" % (xmin, ymin, xmax, ymax))
            lines.append("Size: width=%.4f height=%.4f" % (width, height))

        units = getattr(obj, "units", None) or getattr(obj, "units_found", None)
        if units:
            lines.append("Units: %s" % units)

        kind = getattr(obj, "kind", "")
        if kind == "gerber":
            lines.append("Aperture count: %d" % len(getattr(obj, "tools", {}) or {}))
            lines.append("Solid geometry count: %d" % self.geometry_count(getattr(obj, "solid_geometry", None)))
        elif kind == "excellon":
            tool_data = getattr(obj, "tools", {}) or {}
            drill_count = 0
            slot_count = 0
            for tool in tool_data.values():
                drill_count += len(tool.get("drills", []) or [])
                slot_count += len(tool.get("slots", []) or [])
            lines.append("Tool count: %d" % len(tool_data))
            lines.append("Drill count: %d" % drill_count)
            lines.append("Slot count: %d" % slot_count)
        elif kind == "geometry":
            lines.append("Tool count: %d" % len(getattr(obj, "tools", {}) or {}))
            lines.append("Solid geometry count: %d" % self.geometry_count(getattr(obj, "solid_geometry", None)))
        elif kind == "cncjob":
            source = self.object_source_text(obj)
            if source:
                lines.append("G-code line count: %d" % len([line for line in source.splitlines() if line.strip()]))
            lines.append("Tool entries: %d" % len(getattr(obj, "tools", {}) or {}))
        else:
            source = self.object_source_text(obj)
            if source:
                lines.append("Source line count: %d" % len([line for line in source.splitlines() if line.strip()]))

        if include_source:
            source_text = self.object_source_text(obj)
            if source_text:
                snippet = source_text[:source_limit]
                if len(source_text) > source_limit:
                    snippet += "\n...[truncated]..."
                lines.append("Source snippet:\n%s" % snippet)

        return "\n".join(lines)

    def object_source_text(self, obj):
        source = getattr(obj, "source_file", "")
        if hasattr(source, "getvalue"):
            try:
                source = source.getvalue()
            except Exception:
                source = ""
        if isinstance(source, (list, tuple)):
            source = "\n".join(str(item) for item in source)
        return str(source or "").strip()

    def object_bounds(self, obj):
        bounds_fn = getattr(obj, "bounds", None)
        if not callable(bounds_fn):
            return None
        try:
            bounds = bounds_fn()
        except Exception:
            return None
        if not bounds or len(bounds) != 4:
            return None
        try:
            return [float(value) for value in bounds]
        except Exception:
            return None

    def geometry_count(self, geometry):
        if geometry is None:
            return 0
        if isinstance(geometry, (list, tuple)):
            return len(geometry)
        if hasattr(geometry, "geoms"):
            try:
                return len(list(geometry.geoms))
            except Exception:
                return 1
        return 1

    def run_in_thread(self, busy_message, worker, on_success, on_error):
        if not self._worker_lock.acquire(blocking=False):
            self.ui.chat_status_label.setText(_("Another AI task is already running."))
            return

        self.busy_sig.emit(True, busy_message)
        self.settings_dialog.set_busy(True)

        def task():
            try:
                result = worker()
                self.worker_success_sig.emit(on_success, result)
            except Exception as exc:
                self.worker_error_sig.emit(on_error, str(exc))

        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    def _finish_async(self, callback, payload):
        try:
            callback(payload)
        finally:
            if self._worker_lock.locked():
                self._worker_lock.release()
            self.busy_sig.emit(False, _("Ready"))
            self.settings_dialog.set_busy(False)

    def on_async_error(self, message):
        self.ui.chat_status_label.setText(message)
        self.settings_dialog.provider_status_label.setText(message)
