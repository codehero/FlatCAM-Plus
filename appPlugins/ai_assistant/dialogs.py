# FlatCAM Plus AI Assistant Module
# License: FlatCAM Plus AI Assistant Module Non-Commercial License.
# See appPlugins/ai_assistant/LICENSE.

import builtins
import gettext

from PyQt6 import QtWidgets

from appGUI.PanelStyles import apply_modern_panel_style
from appPlugins.ai_assistant.providers import provider_ids, provider_spec
from appPlugins.cnc_control.widgets import FluidStyleButton

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class AIAssistantSettingsDialog(QtWidgets.QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

        self.setWindowTitle(_("AI Settings"))
        self.setModal(True)
        self.resize(620, 700)

        self.main_lay = QtWidgets.QVBoxLayout(self)
        self.main_lay.setContentsMargins(10, 10, 10, 10)
        self.main_lay.setSpacing(8)

        provider_panel, provider_body = self.create_panel(_("Provider"))
        self.build_provider_panel(provider_body)
        self.main_lay.addWidget(provider_panel)

        context_panel, context_body = self.create_panel(_("Analysis Context"))
        self.build_context_panel(context_body)
        self.main_lay.addWidget(context_panel, 1)

        footer_lay = QtWidgets.QHBoxLayout()
        footer_lay.setContentsMargins(0, 0, 0, 0)
        footer_lay.setSpacing(6)
        self.save_footer_btn = FluidStyleButton(_("Save"), "#2563eb", "#1d4ed8")
        self.test_footer_btn = FluidStyleButton(_("Test Connection"), "#0f766e", "#115e59")
        self.close_btn = FluidStyleButton(_("Close"), "#475569", "#334155")
        footer_lay.addWidget(self.save_footer_btn)
        footer_lay.addWidget(self.test_footer_btn)
        footer_lay.addStretch()
        footer_lay.addWidget(self.close_btn)
        self.main_lay.addLayout(footer_lay)

        self.close_btn.clicked.connect(self.accept)
        apply_modern_panel_style(self, self.app)

    def create_panel(self, title):
        panel = QtWidgets.QGroupBox(title)
        body = QtWidgets.QVBoxLayout(panel)
        body.setContentsMargins(10, 12, 10, 10)
        body.setSpacing(8)
        return panel, body

    def build_provider_panel(self, body):
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        body.addLayout(grid)

        self.provider_combo = QtWidgets.QComboBox()
        for provider_id in provider_ids():
            spec = provider_spec(provider_id)
            self.provider_combo.addItem(spec["label"], provider_id)

        self.endpoint_entry = QtWidgets.QLineEdit()
        self.model_entry = QtWidgets.QLineEdit()
        self.api_key_entry = QtWidgets.QLineEdit()
        self.api_key_entry.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" s")

        self.temperature_spin = QtWidgets.QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 1.5)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setSingleStep(0.05)

        rows = [
            (_("Provider"), self.provider_combo),
            (_("Endpoint"), self.endpoint_entry),
            (_("Model"), self.model_entry),
            (_("API Key"), self.api_key_entry),
            (_("Timeout"), self.timeout_spin),
            (_("Temperature"), self.temperature_spin),
        ]
        for row, (label, widget) in enumerate(rows):
            grid.addWidget(QtWidgets.QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)

        self.provider_note_label = QtWidgets.QLabel("")
        self.provider_note_label.setWordWrap(True)
        self.provider_note_label.setStyleSheet("font-size: 11px;")
        body.addWidget(self.provider_note_label)

        body.addWidget(QtWidgets.QLabel(_("System Prompt")))
        self.system_prompt_entry = QtWidgets.QPlainTextEdit()
        self.system_prompt_entry.setMinimumHeight(100)
        self.system_prompt_entry.setPlaceholderText(
            _("You are an expert PCB/CAM assistant. Analyze Gerber, Excellon, Geometry and CNCJob data carefully.")
        )
        body.addWidget(self.system_prompt_entry)

        action_lay = QtWidgets.QHBoxLayout()
        action_lay.setContentsMargins(0, 0, 0, 0)
        action_lay.setSpacing(6)

        self.save_settings_btn = FluidStyleButton(_("Save"), "#2563eb", "#1d4ed8")
        self.test_connection_btn = FluidStyleButton(_("Test Connection"), "#0f766e", "#115e59")
        self.provider_status_label = QtWidgets.QLabel(_("Not connected"))
        self.provider_status_label.setWordWrap(True)

        action_lay.addWidget(self.save_settings_btn)
        action_lay.addWidget(self.test_connection_btn)
        action_lay.addStretch()
        body.addLayout(action_lay)
        body.addWidget(self.provider_status_label)

    def build_context_panel(self, body):
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        body.addLayout(grid)

        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItem(_("Current Project"), "project")
        self.scope_combo.addItem(_("Current Canvas Object"), "canvas")
        self.scope_combo.addItem(_("Selected Object"), "selected")
        self.scope_combo.addItem(_("Choose Object"), "named")

        self.object_combo = QtWidgets.QComboBox()
        self.object_combo.setEnabled(False)

        grid.addWidget(QtWidgets.QLabel(_("Scope")), 0, 0)
        grid.addWidget(self.scope_combo, 0, 1)
        grid.addWidget(QtWidgets.QLabel(_("Object")), 1, 0)
        grid.addWidget(self.object_combo, 1, 1)

        self.current_canvas_label = QtWidgets.QLabel(_("Current canvas object: none"))
        self.current_canvas_label.setWordWrap(True)
        self.selection_label = QtWidgets.QLabel(_("Selected object: none"))
        self.selection_label.setWordWrap(True)
        self.context_summary_label = QtWidgets.QLabel(_("Context summary will appear here."))
        self.context_summary_label.setWordWrap(True)
        self.context_summary_label.setStyleSheet("font-size: 11px;")

        body.addWidget(self.current_canvas_label)
        body.addWidget(self.selection_label)
        body.addWidget(self.context_summary_label)

        button_lay = QtWidgets.QHBoxLayout()
        button_lay.setContentsMargins(0, 0, 0, 0)
        button_lay.setSpacing(6)

        self.refresh_context_btn = FluidStyleButton(_("Refresh Objects"), "#475569", "#334155")
        self.analyze_btn = FluidStyleButton(_("Analyze Context"), "#7c3aed", "#6d28d9")

        button_lay.addWidget(self.refresh_context_btn)
        button_lay.addWidget(self.analyze_btn)
        button_lay.addStretch()
        body.addLayout(button_lay)

    def set_provider_details(self, label_text, api_key_label, endpoint_placeholder, model_placeholder):
        self.provider_note_label.setText(label_text)
        self.endpoint_entry.setPlaceholderText(endpoint_placeholder)
        self.model_entry.setPlaceholderText(model_placeholder)
        self.api_key_entry.setPlaceholderText(api_key_label)

    def set_scope_controls_enabled(self):
        self.object_combo.setEnabled(self.scope_combo.currentData() == "named")

    def set_busy(self, busy):
        widgets = [
            self.provider_combo,
            self.endpoint_entry,
            self.model_entry,
            self.api_key_entry,
            self.timeout_spin,
            self.temperature_spin,
            self.system_prompt_entry,
            self.scope_combo,
            self.object_combo,
            self.refresh_context_btn,
            self.analyze_btn,
            self.save_settings_btn,
            self.test_connection_btn,
            self.save_footer_btn,
            self.test_footer_btn,
        ]
        for widget in widgets:
            widget.setEnabled(not busy)
        self.close_btn.setEnabled(True)
