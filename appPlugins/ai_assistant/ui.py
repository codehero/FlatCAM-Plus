# FlatCAM Plus AI Assistant Module
# License: FlatCAM Plus AI Assistant Module Non-Commercial License.
# See appPlugins/ai_assistant/LICENSE.

import builtins
import gettext
import html

from PyQt6 import QtGui, QtWidgets

from appGUI.PanelStyles import apply_modern_panel_style
from appPlugins.cnc_control.widgets import FluidStyleButton

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class AIAssistantUI:
    pluginName = _("AI Assistant")

    def __init__(self, layout, app):
        self.app = app
        self.layout = layout

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.container = QtWidgets.QWidget()
        self.layout.addWidget(self.container)

        self.main_lay = QtWidgets.QVBoxLayout(self.container)
        self.main_lay.setContentsMargins(8, 8, 8, 8)
        self.main_lay.setSpacing(8)

        self.header_frame = QtWidgets.QFrame()
        self.header_lay = QtWidgets.QVBoxLayout(self.header_frame)
        self.header_lay.setContentsMargins(10, 10, 10, 10)
        self.header_lay.setSpacing(4)

        self.title_label = QtWidgets.QLabel(_("AI Chat"))
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel(
            _("Ask questions about the current project or the configured analysis context.")
        )
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 11px;")
        self.header_lay.addWidget(self.title_label)
        self.header_lay.addWidget(self.subtitle_label)
        self.main_lay.addWidget(self.header_frame)

        self.chat_panel = QtWidgets.QGroupBox(_("Chat"))
        self.chat_lay = QtWidgets.QVBoxLayout(self.chat_panel)
        self.chat_lay.setContentsMargins(10, 12, 10, 10)
        self.chat_lay.setSpacing(8)
        self.main_lay.addWidget(self.chat_panel, 1)

        self.chat_view = QtWidgets.QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setMinimumHeight(320)
        self.chat_view.document().setDocumentMargin(8)
        self.chat_lay.addWidget(self.chat_view, 1)

        input_label = QtWidgets.QLabel(_("Message"))
        self.chat_lay.addWidget(input_label)

        self.prompt_entry = QtWidgets.QPlainTextEdit()
        self.prompt_entry.setMinimumHeight(120)
        self.prompt_entry.setPlaceholderText(
            _("Ask about clearances, drill map, layers, manufacturability, toolpaths or next CAM steps.")
        )
        self.chat_lay.addWidget(self.prompt_entry)

        btn_lay = QtWidgets.QHBoxLayout()
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(6)

        self.send_btn = FluidStyleButton(_("Send"), "#2563eb", "#1d4ed8")
        self.clear_chat_btn = FluidStyleButton(_("Clear Chat"), "#b45309", "#92400e")
        self.chat_status_label = QtWidgets.QLabel(_("Ready"))
        self.chat_status_label.setWordWrap(True)

        btn_lay.addWidget(self.send_btn)
        btn_lay.addWidget(self.clear_chat_btn)
        btn_lay.addStretch()
        self.chat_lay.addLayout(btn_lay)
        self.chat_lay.addWidget(self.chat_status_label)
        apply_modern_panel_style(self.container, self.app)

    def set_busy(self, busy, message=""):
        self.prompt_entry.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.clear_chat_btn.setEnabled(True)
        if message:
            self.chat_status_label.setText(message)

    def append_chat_message(self, role, text):
        role = role or "assistant"
        safe_text = html.escape(str(text or ""))
        label = _("User") if role == "user" else _("Assistant")
        color = "#2563eb" if role == "user" else "#0f766e"
        message_html = (
            '<div style="margin-bottom:10px;">'
            '<div style="font-weight:700; color:%s; margin-bottom:3px;">%s</div>'
            '<div style="white-space:pre-wrap;">%s</div>'
            '</div>'
        ) % (color, label, safe_text.replace("\n", "<br>"))
        self.chat_view.append(message_html)
        self.chat_view.moveCursor(QtGui.QTextCursor.MoveOperation.End)
