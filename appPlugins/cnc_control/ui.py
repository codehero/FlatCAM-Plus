# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import builtins
import gettext
import html
import os
import time

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from appGUI.GUIElements import (
    FCLabel, FCComboBox, FCSpinner, FCEntry, FCTable
)

from .dialogs import FileSystemDialog
from .profiles import CNC_PROFILES
from .sections import DEFAULT_CNC_SECTIONS
from .widgets import FluidStyleButton, GCodeJobCanvas

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class CNCControlUI:
    pluginName = _("CNC Control")

    def __init__(self, layout, app):
        self.app = app
        self.layout = layout
        self.current_path = "/"
        self.primary = "#31b0d5"
        self.primary_dark = "#269abc"
        self.section_plugins = {
            key: section_cls() for key, section_cls in DEFAULT_CNC_SECTIONS.items()
        }

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("cnc_root")
        self.container.setStyleSheet(self.stylesheet())
        self.layout.addWidget(self.container)

        self.main_lay = QtWidgets.QVBoxLayout(self.container)
        self.main_lay.setContentsMargins(8, 8, 8, 8)
        self.main_lay.setSpacing(8)

        self.build_connection_dialog()
        self.build_connection_state_cache()
        self.build_file_system_dialog()

        # Vertical Scrollable Area
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.main_lay.addWidget(self.scroll)

        self.content_widget = QtWidgets.QWidget()
        self.content_lay = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_lay.setContentsMargins(0, 0, 0, 0)
        self.content_lay.setSpacing(12)
        self.scroll.setWidget(self.content_widget)

        self.build_dashboard_layout()

        self.on_connection_mode_changed()

    def stylesheet(self):
        theme = self.app.options.get('global_theme', 'default')
        if theme in ['default', 'light']:
            surface = "#ffffff"
            subtle = "#f8fafc"
            text = "#263244"
            selected_text = "#111827"
            border = "#dfe4ec"
            separator = "#e3e8f0"
            hover = "#eef4ff"
            hover_border = "#d9e6fb"
            active = "#dfeafe"
            active_border = "#b9d1ff"
            disabled = "#a8b2c1"
            hint = "#6f7b8e"
            console_bg = "#1e1e1e"
            console_text = "#d4d4d4"
        else:
            surface = "#262626"
            subtle = "#171717"
            text = "#f0f0f0"
            selected_text = "#ffffff"
            border = "#444444"
            separator = "#323232"
            hover = "#323232"
            hover_border = "#444444"
            active = "#2b2b2b"
            active_border = "#ff6900"
            disabled = "#777777"
            hint = "#999999"
            console_bg = "#171717"
            console_text = "#f0f0f0"

        arrow_icon = os.path.join(self.app.resource_location, "down-arrow32.png").replace("\\", "/")

        return f"""
            QWidget#cnc_root {{
                background: transparent;
                color: {text};
            }}
            QDialog {{
                background: {surface};
                color: {text};
            }}
            QScrollArea {{
                background: transparent;
                border: 0px;
            }}
            QLabel {{
                color: {text};
            }}
            QGroupBox,
            QGroupBox#cnc_panel {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 13px;
                padding: 9px 8px 8px 8px;
                font-weight: 600;
            }}
            QGroupBox::title,
            QGroupBox#cnc_panel::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 5px;
                color: {text};
            }}
            QFrame#cnc_strip,
            QFrame#cnc_field_cell,
            QFrame#cnc_dro_row,
            QFrame#cnc_segment,
            QFrame#cnc_jog_pad,
            QFrame#cnc_status_pill {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QFrame#cnc_button_help_pair {{
                background: transparent;
                border: 0px;
            }}
            QLabel#cnc_field_label {{
                font-weight: 600;
                padding-right: 4px;
            }}
            QLabel#cnc_axis_label {{
                font-weight: 700;
                font-size: 12pt;
                min-width: 24px;
            }}
            QLabel#cnc_jog_group_label {{
                font-weight: 700;
                padding: 3px 0;
            }}
            QLabel#cnc_jog_center {{
                color: {hint};
                font-weight: 700;
                min-width: 44px;
            }}
            QLabel#cnc_hint_label {{
                color: {hint};
                font-weight: 600;
            }}
            QToolButton,
            QPushButton {{
                background: {subtle};
                color: {text};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 7px;
                font-weight: 600;
                min-height: 24px;
            }}
            QToolButton:hover,
            QPushButton:hover {{
                background: {hover};
                border-color: {hover_border};
            }}
            QToolButton:pressed,
            QToolButton:checked,
            QPushButton:pressed {{
                background: {active};
                border-color: {active_border};
            }}
            QToolButton:disabled,
            QPushButton:disabled {{
                background: {surface};
                color: {disabled};
                border-color: {separator};
            }}
            QToolButton#cnc_segment_button {{
                background: {subtle};
                color: {text};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 12px;
                font-weight: 700;
                min-width: 42px;
            }}
            QToolButton#cnc_segment_button:hover {{
                background: {hover};
                border-color: {hover_border};
            }}
            QToolButton#cnc_segment_button:checked {{
                background: {active};
                border: 1px solid {active_border};
            }}
            QToolButton#cnc_axis_button {{
                background: {subtle};
                color: {text};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 8px;
                min-width: 62px;
                min-height: 38px;
                font-weight: 700;
            }}
            QToolButton#cnc_axis_button:hover {{
                background: {hover};
                border-color: {hover_border};
            }}
            QToolButton#cnc_axis_button:pressed,
            QToolButton#cnc_axis_button:checked {{
                background: {active};
                border-color: {active_border};
            }}
            QToolButton#cnc_help_button {{
                background: {subtle};
                color: {text};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 4px;
                min-width: 24px;
                min-height: 24px;
            }}
            QToolButton#cnc_help_button:hover {{
                background: {hover};
                border-color: {hover_border};
            }}
            QToolButton::menu-button {{
                border: 0px;
                width: 14px;
            }}
            QComboBox#cnc_input,
            QLineEdit#cnc_input,
            QSpinBox#cnc_input,
            QDoubleSpinBox#cnc_input,
            QDialog QComboBox,
            QDialog QLineEdit,
            QDialog QSpinBox,
            QDialog QDoubleSpinBox,
            QPlainTextEdit {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 7px;
                min-height: 28px;
                selection-background-color: {active};
                selection-color: {selected_text};
            }}
            QComboBox#cnc_input,
            QDialog QComboBox {{
                padding-right: 28px;
            }}
            QComboBox#cnc_input:focus,
            QLineEdit#cnc_input:focus,
            QSpinBox#cnc_input:focus,
            QDoubleSpinBox#cnc_input:focus,
            QDialog QComboBox:focus,
            QDialog QLineEdit:focus,
            QDialog QSpinBox:focus,
            QDialog QDoubleSpinBox:focus,
            QPlainTextEdit:focus {{
                border-color: {active_border};
            }}
            QComboBox#cnc_input:disabled,
            QLineEdit#cnc_input:disabled,
            QSpinBox#cnc_input:disabled,
            QDoubleSpinBox#cnc_input:disabled,
            QDialog QComboBox:disabled,
            QDialog QLineEdit:disabled,
            QDialog QSpinBox:disabled,
            QDialog QDoubleSpinBox:disabled {{
                color: {disabled};
                border-color: {separator};
            }}
            QComboBox#cnc_input::drop-down,
            QDialog QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                border-left: 0px;
                width: 26px;
            }}
            QComboBox#cnc_input::down-arrow,
            QDialog QComboBox::down-arrow {{
                image: url({arrow_icon});
                width: 10px;
                height: 10px;
            }}
            QComboBox#cnc_input QAbstractItemView,
            QDialog QComboBox QAbstractItemView {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
                outline: 0px;
                selection-background-color: {hover};
                selection-color: {selected_text};
            }}
            QSpinBox#cnc_input::up-button,
            QSpinBox#cnc_input::down-button,
            QDoubleSpinBox#cnc_input::up-button,
            QDoubleSpinBox#cnc_input::down-button,
            QDialog QSpinBox::up-button,
            QDialog QSpinBox::down-button,
            QDialog QDoubleSpinBox::up-button,
            QDialog QDoubleSpinBox::down-button {{
                background: transparent;
                border: 0px;
                width: 18px;
            }}
            QCheckBox {{
                color: {text};
                font-weight: 600;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 4px;
                width: 15px;
                height: 15px;
            }}
            QCheckBox::indicator:hover {{
                background: {hover};
                border-color: {hover_border};
            }}
            QCheckBox::indicator:checked {{
                background: {active};
                border-color: {active_border};
            }}
            QListWidget,
            QTableWidget {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                gridline-color: {separator};
                alternate-background-color: {subtle};
                selection-background-color: {hover};
                selection-color: {selected_text};
                outline: 0px;
            }}
            QListWidget::item,
            QTableWidget::item {{
                border: 0px;
                padding: 5px;
            }}
            QListWidget::item:selected,
            QTableWidget::item:selected {{
                background: {hover};
                color: {selected_text};
            }}
            QListWidget::item:hover,
            QTableWidget::item:hover {{
                background: {hover};
                color: {selected_text};
            }}
            QHeaderView::section {{
                background: {subtle};
                color: {text};
                border: 0px;
                border-bottom: 1px solid {separator};
                padding: 6px;
                font-weight: 600;
            }}
            QProgressBar#cnc_progress {{
                border: 1px solid {border};
                border-radius: 5px;
                background: {surface};
                color: {text};
                text-align: center;
                min-height: 18px;
            }}
            QProgressBar#cnc_progress::chunk {{
                background: {active_border};
                border-radius: 3px;
            }}
            QTextEdit#cnc_console {{
                background: {console_bg};
                color: {console_text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
                font-family: Consolas, monospace;
            }}
            QMenu {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                background: transparent;
                color: {text};
                padding: 6px 22px 6px 28px;
                border-radius: 5px;
            }}
            QMenu::item:selected {{
                background: {hover};
                color: {selected_text};
            }}
            QMenu::item:disabled {{
                color: {disabled};
            }}
            QMenu::separator {{
                height: 1px;
                background: {separator};
                margin: 5px 8px;
            }}
            QMenu::icon {{
                padding-left: 4px;
            }}
        """

    def icon(self, filename):
        return QtGui.QIcon(os.path.join(self.app.resource_location, filename))

    def setup_button(self, button, icon_file=None, tooltip=None, text_beside=True):
        button.setObjectName("cnc_button")
        button.setAutoRaise(False)
        if icon_file:
            button.setIcon(self.icon(icon_file))
        button.setIconSize(QtCore.QSize(18, 18))
        button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if text_beside else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def setup_icon_button(self, button, icon_file=None, tooltip=None):
        self.setup_button(button, icon_file, tooltip, text_beside=False)
        button.setFixedSize(34, 32)
        button.setText(button.text())
        return button

    def setup_input(self, widget):
        widget.setObjectName("cnc_input")
        return widget

    def setup_connection_input(self, widget, min_width=None, fixed_width=None):
        self.setup_input(widget)
        widget.setFixedHeight(34)
        widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        if min_width is not None:
            widget.setMinimumWidth(min_width)
        if fixed_width is not None:
            widget.setFixedWidth(fixed_width)
        return widget

    def field_label(self, text):
        label = FCLabel(text)
        label.setObjectName("cnc_field_label")
        return label

    def connection_field_label(self, text):
        label = self.field_label(text)
        label.setFixedHeight(34)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    def field_cell(self, label_text, widget):
        frame = QtWidgets.QFrame()
        frame.setObjectName("cnc_field_cell")
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(3)
        lay.addWidget(self.field_label(label_text))
        lay.addWidget(widget)
        return frame

    def help_button(self, tooltip):
        button = QtWidgets.QToolButton()
        button.setObjectName("cnc_help_button")
        button.setAutoRaise(False)
        button.setIcon(self.icon("help.png"))
        button.setIconSize(QtCore.QSize(14, 14))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setToolTip(tooltip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def action_with_help(self, button, tooltip):
        frame = QtWidgets.QFrame()
        frame.setObjectName("cnc_button_help_pair")
        lay = QtWidgets.QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        lay.addWidget(button, 1)
        lay.addWidget(self.help_button(tooltip))
        return frame

    def override_stepper(self, minus_btn, reset_btn, plus_btn):
        lay = QtWidgets.QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(minus_btn)
        lay.addWidget(reset_btn)
        lay.addWidget(plus_btn)
        lay.addStretch()
        return lay

    def build_dashboard_layout(self):
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self.content_lay.addLayout(top_row)

        top_row.addWidget(self.section_plugins["gauges"].build_panel(self), 1)
        top_row.addWidget(self.section_plugins["machine_profiles"].build_panel(self), 1)
        top_row.addWidget(self.section_plugins["job_streaming"].build_panel(self), 2)

        machine_grid = QtWidgets.QGridLayout()
        machine_grid.setContentsMargins(0, 0, 0, 0)
        machine_grid.setSpacing(8)
        self.content_lay.addLayout(machine_grid)

        machine_grid.addWidget(self.section_plugins["position"].build_panel(self), 0, 0)
        machine_grid.addWidget(self.section_plugins["jog"].build_panel(self), 0, 1)
        machine_grid.addWidget(self.section_plugins["overrides_system"].build_panel(self), 0, 2)
        machine_grid.addWidget(self.section_plugins["macros"].build_panel(self), 0, 3)
        for column in range(4):
            machine_grid.setColumnStretch(column, 1)

        probing_preview_row = QtWidgets.QHBoxLayout()
        probing_preview_row.setContentsMargins(0, 0, 0, 0)
        probing_preview_row.setSpacing(8)
        self.content_lay.addLayout(probing_preview_row)

        probing_preview_row.addWidget(self.section_plugins["probing_work_offset"].build_panel(self), 1)
        probing_preview_row.addWidget(self.section_plugins["auto_level"].build_panel(self), 1)
        probing_preview_row.addWidget(self.section_plugins["gcode_preview_verification"].build_panel(self), 2)

        self.content_lay.addWidget(self.section_plugins["terminal_simulation"].build_panel(self), 1)
        self.content_lay.addWidget(self.section_plugins["modal_actions"].build_widget(self))

    def build_file_system_dialog(self):
        self.file_system_dialog = FileSystemDialog(self)
        for attr in [
            "files_fs_combo", "files_refresh_btn", "files_upload_btn", "files_mkdir_btn",
            "files_delete_btn", "files_root_btn", "files_up_btn", "files_table",
            "path_label", "file_status", "busy_label"
        ]:
            setattr(self, attr, getattr(self.file_system_dialog, attr))

    def show_file_system_dialog(self):
        self.file_system_dialog.show()
        self.file_system_dialog.raise_()
        self.file_system_dialog.activateWindow()

    def update_machine_profiles(self, profiles, active_name):
        if not hasattr(self, "machine_profile_combo"):
            return

        self.machine_profile_combo.blockSignals(True)
        self.machine_profile_combo.clear()
        active_index = 0
        for idx, profile in enumerate(profiles):
            name = profile.get("name", "")
            self.machine_profile_combo.addItem(name, name)
            if name == active_name:
                active_index = idx
        if self.machine_profile_combo.count():
            self.machine_profile_combo.setCurrentIndex(active_index)
            self.update_machine_profile_summary(profiles[active_index])
        else:
            self.update_machine_profile_summary({})
        self.machine_profile_combo.blockSignals(False)

    def update_machine_profile_summary(self, profile):
        if not hasattr(self, "machine_safe_z_value"):
            return

        if not profile:
            for label in [
                self.machine_safe_z_value, self.machine_jog_feed_value, self.machine_spindle_max_value,
                self.machine_travel_value
            ]:
                label.setText("-")
            return

        self.machine_safe_z_value.setText(f"{profile.get('safe_z', 0):.3f} mm")
        self.machine_jog_feed_value.setText(f"{profile.get('jog_feed', 0)} mm/min")
        self.machine_spindle_max_value.setText(f"{profile.get('spindle_max', 0)} RPM")
        if hasattr(self, "probe_feed"):
            self.probe_feed.setValue(int(profile.get("probe_feed", 100)))
        if hasattr(self, "autolevel_probe_feed"):
            self.autolevel_probe_feed.setValue(int(profile.get("probe_feed", 100)))
        if hasattr(self, "autolevel_safe_z"):
            self.autolevel_safe_z.set_value(float(profile.get("safe_z", 5.0)))
        travel = (
            f"X{profile.get('travel_x', 0):.0f} "
            f"Y{profile.get('travel_y', 0):.0f} "
            f"Z{profile.get('travel_z', 0):.0f} mm"
        )
        self.machine_travel_value.setText(travel)

    def build_connection_state_cache(self):
        self.state_indicator = QtWidgets.QFrame()
        self.state_indicator.setFixedSize(12, 12)
        self.state_indicator.setStyleSheet("background-color: #999999; border-radius: 6px;")
        self.state_label = FCLabel("OFFLINE", bold=True)
        self.connection_desc = FCLabel(_("Offline"), color="#777777")
        self.controller_info_label = FCLabel("", color="#777777")

    def build_connection_dialog(self):
        self.connection_dialog = QtWidgets.QDialog(self.app.ui)
        self.connection_dialog.setWindowTitle(_("Connection Settings"))
        self.connection_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.connection_dialog.setMinimumWidth(620)
        self.connection_dialog.setStyleSheet(self.stylesheet())

        dialog_lay = QtWidgets.QVBoxLayout(self.connection_dialog)
        dialog_lay.setContentsMargins(10, 10, 10, 10)
        dialog_lay.setSpacing(8)
        dialog_lay.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetFixedSize)

        self.dialog_status_frame = QtWidgets.QFrame()
        self.dialog_status_frame.setObjectName("cnc_strip")
        dialog_status_lay = QtWidgets.QVBoxLayout(self.dialog_status_frame)
        dialog_status_lay.setContentsMargins(8, 6, 8, 6)
        dialog_status_lay.setSpacing(3)

        self.dialog_state_label = FCLabel(_("Connect"), bold=True)
        self.dialog_connection_desc = FCLabel("", color="#777777")
        dialog_status_lay.addWidget(self.dialog_state_label)
        dialog_status_lay.addWidget(self.dialog_connection_desc)
        dialog_lay.addWidget(self.dialog_status_frame)

        self.connection_fields_widget = QtWidgets.QWidget()
        fields_lay = QtWidgets.QVBoxLayout(self.connection_fields_widget)
        fields_lay.setContentsMargins(0, 0, 0, 0)
        fields_lay.setSpacing(8)

        self.connection_mode_combo = FCComboBox()
        self.setup_connection_input(self.connection_mode_combo, min_width=210)
        self.connection_mode_combo.addItem(_("COM / USB"), "serial")
        self.connection_mode_combo.addItem(_("WiFi TCP/Telnet"), "tcp")
        self.connection_mode_combo.addItem(_("FluidNC Web"), "http")

        self.profile_combo = FCComboBox()
        self.setup_connection_input(self.profile_combo, min_width=210)
        for key, profile in CNC_PROFILES.items():
            self.profile_combo.addItem(profile["label"], key)

        selector_lay = QtWidgets.QHBoxLayout()
        selector_lay.setSpacing(8)
        selector_lay.addWidget(self.connection_field_label(_("Mode")))
        selector_lay.addWidget(self.connection_mode_combo, 1)
        selector_lay.addWidget(self.connection_field_label(_("Controller")))
        selector_lay.addWidget(self.profile_combo, 1)
        fields_lay.addLayout(selector_lay)

        self.connection_stack = QtWidgets.QStackedWidget()
        self.connection_stack.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        fields_lay.addWidget(self.connection_stack)
        dialog_lay.addWidget(self.connection_fields_widget)

        self.connect_btn = FluidStyleButton(_("Connect"), "#337ab7", "#286090")
        self.setup_button(self.connect_btn, "link32.png", _("Connect to the CNC controller."))
        self.test_connection_btn = FluidStyleButton(_("Test Connection"), "#5bc0de", "#31b0d5")
        self.setup_button(self.test_connection_btn, "replot16.png", _("Test the selected connection."))
        self.disconnect_btn = FluidStyleButton(_("Disconnect"), "#d9534f", "#c9302c")
        self.setup_button(self.disconnect_btn, "power16.png", _("Disconnect the CNC controller."))
        self.com_refresh = FluidStyleButton(_("Refresh"), "#5bc0de", "#31b0d5")
        self.setup_button(self.com_refresh, "replot16.png", _("Refresh COM ports."))
        self.close_connection_btn = FluidStyleButton(_("Close"), "#777777", "#666666")
        self.setup_button(self.close_connection_btn, None, _("Close this window."))
        self.close_connection_btn.clicked.connect(self.connection_dialog.hide)

        action_lay = QtWidgets.QHBoxLayout()
        action_lay.setSpacing(6)
        action_lay.addWidget(self.com_refresh)
        action_lay.addStretch()
        action_lay.addWidget(self.test_connection_btn)
        action_lay.addWidget(self.connect_btn)
        action_lay.addWidget(self.disconnect_btn)
        action_lay.addWidget(self.close_connection_btn)
        dialog_lay.addLayout(action_lay)

        self.build_serial_connection_page()
        self.build_tcp_connection_page()
        self.build_http_connection_page()

    def show_connection_dialog(self, connected=False):
        self.sync_connection_dialog(connected)
        self.connection_dialog.adjustSize()
        self.connection_dialog.show()
        self.connection_dialog.raise_()
        self.connection_dialog.activateWindow()

    def sync_connection_dialog(self, connected=False):
        description = self.connection_desc.text().strip() if hasattr(self, "connection_desc") else ""
        controller = self.controller_info_label.text().strip() if hasattr(self, "controller_info_label") else ""
        mode = self.connection_mode_combo.currentText()
        profile = self.profile_combo.currentText()

        if connected:
            self.dialog_state_label.setText(_("Connected"))
            info = description or _("Connected")
            details = [info, mode, profile]
            if controller:
                details.append(controller)
            self.dialog_connection_desc.setText(" | ".join(details))
        else:
            self.dialog_state_label.setText(_("Connect"))
            self.dialog_connection_desc.setText("%s | %s" % (mode, profile))

        self.connection_fields_widget.setEnabled(not connected)
        self.connect_btn.setVisible(not connected)
        self.test_connection_btn.setVisible(not connected)
        self.disconnect_btn.setVisible(connected)
        self.com_refresh.setEnabled(not connected and self.connection_mode_combo.currentData() == "serial")

    def set_connection_actions_enabled(self, enabled):
        self.connect_btn.setEnabled(enabled)
        self.test_connection_btn.setEnabled(enabled)
        self.disconnect_btn.setEnabled(enabled)
        self.com_refresh.setEnabled(enabled and self.connection_mode_combo.currentData() == "serial")

    def build_serial_connection_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.com_port = FCComboBox()
        self.setup_connection_input(self.com_port, min_width=320)
        self.com_port.setEditable(True)
        self.baudrate_combo = FCComboBox()
        self.setup_connection_input(self.baudrate_combo, fixed_width=135)
        for baud in ["115200", "250000", "230400", "57600", "38400", "19200", "9600"]:
            self.baudrate_combo.addItem(baud)
        self.baudrate_combo.setCurrentText("115200")

        lay.addWidget(self.connection_field_label(_("Port")))
        lay.addWidget(self.com_port, 1)
        lay.addWidget(self.connection_field_label(_("Baud")))
        lay.addWidget(self.baudrate_combo)
        self.connection_stack.addWidget(page)

    def build_tcp_connection_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.tcp_host = FCEntry()
        self.setup_connection_input(self.tcp_host, min_width=340)
        self.tcp_host.setPlaceholderText("192.168.0.10")
        self.tcp_host.setText("fluidnc.local")
        self.tcp_port = FCSpinner()
        self.setup_connection_input(self.tcp_port, fixed_width=115)
        self.tcp_port.set_range(1, 65535)
        self.tcp_port.setValue(23)

        lay.addWidget(self.connection_field_label(_("Host")))
        lay.addWidget(self.tcp_host, 1)
        lay.addWidget(self.connection_field_label(_("Port")))
        lay.addWidget(self.tcp_port)
        self.connection_stack.addWidget(page)

    def build_http_connection_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QGridLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(6)

        self.web_url = FCEntry()
        self.setup_connection_input(self.web_url, min_width=500)
        self.web_url.setText("http://fluidnc.local")
        self.web_user = FCEntry()
        self.setup_connection_input(self.web_user, min_width=500)
        self.web_password = FCEntry()
        self.setup_connection_input(self.web_password, min_width=500)
        self.web_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        lay.addWidget(self.connection_field_label(_("URL")), 0, 0)
        lay.addWidget(self.web_url, 0, 1)
        lay.addWidget(self.connection_field_label(_("User")), 1, 0)
        lay.addWidget(self.web_user, 1, 1)
        lay.addWidget(self.connection_field_label(_("Password")), 2, 0)
        lay.addWidget(self.web_password, 2, 1)
        lay.setColumnStretch(1, 1)
        self.connection_stack.addWidget(page)

    def build_dro(self, body):
        self.dro_grid = QtWidgets.QGridLayout()
        self.dro_grid.setContentsMargins(8, 8, 8, 8)
        self.dro_grid.setSpacing(10)
        body.addLayout(self.dro_grid)

        # Headers
        self.dro_grid.addWidget(FCLabel(_("Work"), bold=True, size=11), 0, 1, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(FCLabel(_("Machine"), bold=True, size=11), 0, 2, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(FCLabel(_("Zero"), bold=True, size=11), 0, 3, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(FCLabel(_("Limit"), bold=True, size=11), 0, 4, Qt.AlignmentFlag.AlignCenter)

        # Rows
        self.zero_x, self.x_val, self.mx_val, self.limit_x = self.add_dro_row(1, "X", "#d9534f")
        self.zero_y, self.y_val, self.my_val, self.limit_y = self.add_dro_row(2, "Y", "#5cb85c")
        self.zero_z, self.z_val, self.mz_val, self.limit_z = self.add_dro_row(3, "Z", "#337ab7")

        # Bottom Buttons
        buttons = QtWidgets.QHBoxLayout()
        self.zero_all = FluidStyleButton(_("ZERO ALL"), "#444444", "#222222")
        self.home_btn = FluidStyleButton(_("HOME"), "#337ab7", "#286090")
        self.unlock_btn = FluidStyleButton(_("UNLOCK"), "#f0ad4e", "#ec971f")
        self.setup_button(self.zero_all, "origin16.png", _("Set work position to zero."))
        self.setup_button(self.home_btn, "home16.png", _("Home the machine."))
        self.setup_button(self.unlock_btn, "power16.png", _("Unlock the controller."))
        buttons.addWidget(self.zero_all)
        buttons.addWidget(self.home_btn)
        buttons.addWidget(self.unlock_btn)
        body.addLayout(buttons)

    def add_dro_row(self, row, axis, color):
        axis_label = FCLabel(axis, bold=True, size=15, color=color)
        work = FCLabel("0.000", bold=True, size=22)
        machine = FCLabel("0.000", color="#666666", size=14)
        zero = FluidStyleButton(f"{axis}0", "#444444", "#222222")
        limit = FCLabel("-")
        self.setup_button(zero, "origin16.png", _("Zero this axis."))
        zero.setFixedWidth(60)

        work.setAlignment(Qt.AlignmentFlag.AlignCenter)
        machine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        work.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-weight: bold;")
        machine.setStyleSheet("font-family: 'Consolas', 'Monospace';")
        limit.setStyleSheet("color: #777777; font-weight: 700;")

        self.dro_grid.addWidget(axis_label, row, 0, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(work, row, 1, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(machine, row, 2, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(zero, row, 3, Qt.AlignmentFlag.AlignCenter)
        self.dro_grid.addWidget(limit, row, 4, Qt.AlignmentFlag.AlignCenter)

        return zero, work, machine, limit

    def build_jog(self, body):
        settings_lay = QtWidgets.QHBoxLayout()
        settings_lay.setContentsMargins(0, 0, 0, 0)
        settings_lay.setSpacing(8)

        step_frame = QtWidgets.QFrame()
        step_frame.setObjectName("cnc_segment")
        step_frame.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        step_lay = QtWidgets.QHBoxLayout(step_frame)
        step_lay.setContentsMargins(2, 2, 2, 2)
        step_lay.setSpacing(2)
        self.step_group = QtWidgets.QButtonGroup(step_frame)
        self.step_group.setExclusive(True)
        self.step_buttons = []
        for idx, value in enumerate(["0.1", "1", "10", "100"]):
            step_btn = FluidStyleButton(value)
            step_btn.setObjectName("cnc_segment_button")
            step_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            step_btn.setCheckable(True)
            step_btn.setProperty("step_value", value)
            step_btn.setAutoRaise(False)
            if value == "1":
                step_btn.setChecked(True)
            self.step_group.addButton(step_btn, idx)
            self.step_buttons.append(step_btn)
            step_lay.addWidget(step_btn)

        self.jog_feed = FCSpinner()
        self.setup_input(self.jog_feed)
        self.jog_feed.setFixedSize(150, 34)
        self.jog_feed.set_range(1, 60000)
        self.jog_feed.setValue(1000)
        self.jog_feed.setSuffix(" mm/min")
        self.jog_feed.setToolTip(_("Jog feed rate."))

        settings_lay.addWidget(self.field_label(_("Step")))
        settings_lay.addWidget(step_frame)
        settings_lay.addSpacing(8)
        settings_lay.addWidget(self.field_label(_("Feed")))
        settings_lay.addWidget(self.jog_feed)
        settings_lay.addStretch()
        body.addLayout(settings_lay)

        jog_wrap = QtWidgets.QHBoxLayout()
        jog_wrap.setContentsMargins(0, 0, 0, 0)
        jog_wrap.setSpacing(8)
        body.addLayout(jog_wrap)

        xy_pad = QtWidgets.QFrame()
        xy_pad.setObjectName("cnc_jog_pad")
        xy_pad.setMinimumSize(282, 218)
        xy_pad.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        xy_lay = QtWidgets.QGridLayout(xy_pad)
        xy_lay.setContentsMargins(12, 10, 12, 10)
        xy_lay.setHorizontalSpacing(8)
        xy_lay.setVerticalSpacing(7)

        z_pad = QtWidgets.QFrame()
        z_pad.setObjectName("cnc_jog_pad")
        z_pad.setFixedSize(108, 218)
        z_lay = QtWidgets.QVBoxLayout(z_pad)
        z_lay.setContentsMargins(12, 10, 12, 10)
        z_lay.setSpacing(7)

        self.jog_up = FluidStyleButton("Y+")
        self.jog_down = FluidStyleButton("Y-")
        self.jog_left = FluidStyleButton("X-")
        self.jog_right = FluidStyleButton("X+")
        self.jog_z_up = FluidStyleButton("Z+")
        self.jog_z_down = FluidStyleButton("Z-")
        self.setup_button(self.jog_up, "up-arrow32.png", _("Jog Y+"))
        self.setup_button(self.jog_down, "down-arrow32.png", _("Jog Y-"))
        self.setup_button(self.jog_left, "left_arrow32.png", _("Jog X-"))
        self.setup_button(self.jog_right, "right_arrow32.png", _("Jog X+"))
        self.setup_button(self.jog_z_up, "up-arrow32.png", _("Jog Z+"))
        self.setup_button(self.jog_z_down, "down-arrow32.png", _("Jog Z-"))
        for button in [self.jog_up, self.jog_down, self.jog_left, self.jog_right, self.jog_z_up, self.jog_z_down]:
            button.setObjectName("cnc_axis_button")
            button.setFixedSize(78, 40)

        xy_title = FCLabel(_("XY Axes"), bold=True)
        xy_title.setObjectName("cnc_jog_group_label")
        xy_center = FCLabel("X / Y")
        xy_center.setObjectName("cnc_jog_center")
        xy_center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        xy_lay.addWidget(xy_title, 0, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignCenter)
        xy_lay.addWidget(self.jog_up, 1, 1)
        xy_lay.addWidget(self.jog_left, 2, 0)
        xy_lay.addWidget(xy_center, 2, 1)
        xy_lay.addWidget(self.jog_right, 2, 2)
        xy_lay.addWidget(self.jog_down, 3, 1)

        z_title = FCLabel(_("Z Axis"), bold=True)
        z_title.setObjectName("cnc_jog_group_label")
        z_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        z_lay.addWidget(z_title)
        z_lay.addWidget(self.jog_z_up)
        z_mid = FCLabel("Z")
        z_mid.setObjectName("cnc_jog_center")
        z_mid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        z_lay.addWidget(z_mid)
        z_lay.addWidget(self.jog_z_down)
        z_lay.addStretch()

        jog_wrap.addWidget(xy_pad, 1)
        jog_wrap.addWidget(z_pad)

    def build_system(self, body):
        values = QtWidgets.QGridLayout()
        values.setHorizontalSpacing(8)
        body.addLayout(values)

        self.feed_value = FCLabel("0", bold=True)
        self.spindle_value = FCLabel("0", bold=True)
        self.feed_override_value = FCLabel("100%")
        self.rapid_override_value = FCLabel("100%")
        self.spindle_override_value = FCLabel("100%")

        values.addWidget(FCLabel(_("Feed"), bold=True), 0, 0)
        values.addWidget(self.feed_value, 0, 1)
        values.addWidget(FCLabel(_("Spindle"), bold=True), 0, 2)
        values.addWidget(self.spindle_value, 0, 3)
        values.addWidget(FCLabel(_("Feed %"), bold=True), 1, 0)
        values.addWidget(self.feed_override_value, 1, 1)
        values.addWidget(FCLabel(_("Rapid %"), bold=True), 1, 2)
        values.addWidget(self.rapid_override_value, 1, 3)
        values.addWidget(FCLabel(_("Spindle %"), bold=True), 2, 0)
        values.addWidget(self.spindle_override_value, 2, 1)

        ov_grid = QtWidgets.QGridLayout()
        ov_grid.setSpacing(6)
        body.addLayout(ov_grid)

        self.feed_override_entry = FCSpinner()
        self.setup_connection_input(self.feed_override_entry, fixed_width=112)
        self.feed_override_entry.set_range(10, 200)
        self.feed_override_entry.setValue(100)
        self.feed_override_entry.setSuffix("%")
        self.feed_override_entry.setToolTip(_("Target feed override percent."))
        self.feed_set_btn = FluidStyleButton("SET", "#337ab7", "#286090")
        self.setup_button(self.feed_set_btn, "apply32.png", _("Set feed override percent."))

        self.spindle_override_entry = FCSpinner()
        self.setup_connection_input(self.spindle_override_entry, fixed_width=112)
        self.spindle_override_entry.set_range(10, 200)
        self.spindle_override_entry.setValue(100)
        self.spindle_override_entry.setSuffix("%")
        self.spindle_override_entry.setToolTip(_("Target spindle override percent."))
        self.spindle_override_set_btn = FluidStyleButton("SET", "#337ab7", "#286090")
        self.setup_button(self.spindle_override_set_btn, "apply32.png", _("Set spindle override percent."))

        self.feed_minus = FluidStyleButton("-")
        self.feed_reset = FluidStyleButton("100")
        self.feed_plus = FluidStyleButton("+")
        self.spindle_minus = FluidStyleButton("-")
        self.spindle_reset = FluidStyleButton("100")
        self.spindle_plus = FluidStyleButton("+")
        self.setup_icon_button(self.feed_minus, None, _("Decrease feed override."))
        self.setup_icon_button(self.feed_reset, None, _("Reset feed override."))
        self.setup_icon_button(self.feed_plus, None, _("Increase feed override."))
        self.setup_icon_button(self.spindle_minus, None, _("Decrease spindle override."))
        self.setup_icon_button(self.spindle_reset, None, _("Reset spindle override."))
        self.setup_icon_button(self.spindle_plus, None, _("Increase spindle override."))

        self.spindle_rpm = FCSpinner()
        self.setup_connection_input(self.spindle_rpm, fixed_width=150)
        self.spindle_rpm.set_range(0, 60000)
        self.spindle_rpm.setValue(12000)
        self.spindle_rpm.setSuffix(" RPM")
        self.spindle_rpm.setToolTip(_("Target spindle RPM."))
        self.spindle_set_btn = FluidStyleButton("SET RPM", "#337ab7", "#286090")
        self.spindle_stop_btn = FluidStyleButton("STOP", "#d9534f", "#c9302c")
        self.setup_button(self.spindle_set_btn, "apply32.png", _("Set spindle speed with the selected RPM."))
        self.setup_button(self.spindle_stop_btn, "power16.png", _("Stop spindle."))

        ov_grid.addWidget(FCLabel(_("RPM"), bold=True), 0, 0)
        ov_grid.addWidget(self.spindle_rpm, 0, 1)
        ov_grid.addWidget(self.spindle_set_btn, 0, 2)
        ov_grid.addWidget(self.spindle_stop_btn, 0, 3)
        ov_grid.addWidget(FCLabel(_("FEED"), bold=True), 1, 0)
        ov_grid.addWidget(self.feed_override_entry, 1, 1)
        ov_grid.addWidget(self.feed_set_btn, 1, 2)
        ov_grid.addLayout(self.override_stepper(self.feed_minus, self.feed_reset, self.feed_plus), 1, 3)
        ov_grid.addWidget(FCLabel(_("SPINDLE %"), bold=True), 2, 0)
        ov_grid.addWidget(self.spindle_override_entry, 2, 1)
        ov_grid.addWidget(self.spindle_override_set_btn, 2, 2)
        ov_grid.addLayout(self.override_stepper(self.spindle_minus, self.spindle_reset, self.spindle_plus), 2, 3)

        sys_lay = QtWidgets.QGridLayout()
        sys_lay.setSpacing(6)
        body.addLayout(sys_lay)

        self.info_btn = FluidStyleButton("INFO", "#5bc0de", "#31b0d5")
        self.cfg_dump = FluidStyleButton("CFG", "#444444", "#222222")
        self.reset_btn = FluidStyleButton("RESET", "#5cb85c", "#449d44")
        self.estop_btn = FluidStyleButton("HOLD", "#d9534f", "#c9302c")
        self.resume_btn = FluidStyleButton("RESUME", "#5bc0de", "#31b0d5")
        self.macro_laser = FluidStyleButton("LASER ON", "#d9534f", "#c9302c")
        self.setup_button(self.info_btn, "info16.png", _("Request controller info."))
        self.setup_button(self.cfg_dump, "settings18.png", _("Request controller settings."))
        self.setup_button(self.reset_btn, "reset32.png", _("Reset controller."))
        self.setup_button(self.estop_btn, "warning.png", _("Feed hold."))
        self.setup_button(self.resume_btn, "apply32.png", _("Resume motion."))
        self.setup_button(self.macro_laser, "warning.png", _("Toggle laser output."))
        self.macro_laser.setCheckable(True)

        sys_lay.addWidget(self.action_with_help(
            self.info_btn, _("Request controller status and firmware information.")
        ), 0, 0)
        sys_lay.addWidget(self.action_with_help(
            self.cfg_dump, _("Request controller configuration dump.")
        ), 0, 1)
        sys_lay.addWidget(self.action_with_help(
            self.reset_btn, _("Reset the controller connection.")
        ), 0, 2)
        sys_lay.addWidget(self.action_with_help(
            self.estop_btn, _("Pause motion with feed hold.")
        ), 1, 0)
        sys_lay.addWidget(self.action_with_help(
            self.resume_btn, _("Resume motion after hold.")
        ), 1, 1)
        sys_lay.addWidget(self.action_with_help(
            self.macro_laser, _("Toggle laser output on or off.")
        ), 1, 2)

        for col in range(3):
            sys_lay.setColumnStretch(col, 1)

    def build_direct_job(self, body):
        job_frame = QtWidgets.QFrame()
        job_frame.setObjectName("cnc_strip")
        job_lay = QtWidgets.QHBoxLayout(job_frame)
        job_lay.setContentsMargins(8, 6, 8, 6)
        job_lay.setSpacing(8)
        self.object_combo = FCComboBox()
        self.setup_input(self.object_combo)
        self.object_combo.setMinimumWidth(240)
        self.refresh_jobs_btn = FluidStyleButton(_("Refresh Jobs"), "#ffffff", "#f5f5f5", "#333333")
        self.queue_add_btn = FluidStyleButton(_("ADD"), "#337ab7", "#286090")
        self.queue_remove_btn = FluidStyleButton(_("REMOVE"), "#d9534f", "#c9302c")
        self.queue_up_btn = FluidStyleButton(_("UP"), "#444444", "#222222")
        self.queue_down_btn = FluidStyleButton(_("DOWN"), "#444444", "#222222")
        self.play_btn = FluidStyleButton(_("START QUEUE"), "#5cb85c", "#449d44")
        self.pause_btn = FluidStyleButton(_("PAUSE"), "#f0ad4e", "#ec971f")
        self.stop_btn = FluidStyleButton(_("STOP"), "#d9534f", "#c9302c")
        self.setup_button(self.refresh_jobs_btn, "replot16.png", _("Refresh CNCJob list."))
        self.setup_button(self.queue_add_btn, "plus16.png", _("Add selected CNCJob to the queue."))
        self.setup_button(self.queue_remove_btn, "trash16.png", _("Remove selected queue item."))
        self.setup_button(self.queue_up_btn, "up-arrow32.png", _("Move selected queue item up."))
        self.setup_button(self.queue_down_btn, "down-arrow32.png", _("Move selected queue item down."))
        self.setup_button(self.play_btn, "cnc16.png", _("Stream the queued G-code jobs to the controller."))
        self.setup_button(self.pause_btn, "warning.png", _("Pause queue streaming."))
        self.setup_button(self.stop_btn, "power16.png", _("Stop queue streaming."))

        job_lay.addWidget(FCLabel(_("CNCJob"), bold=True))
        job_lay.addWidget(self.object_combo, 1)
        job_lay.addWidget(self.refresh_jobs_btn)
        job_lay.addWidget(self.queue_add_btn)
        job_lay.addWidget(self.queue_remove_btn)
        job_lay.addWidget(self.queue_up_btn)
        job_lay.addWidget(self.queue_down_btn)
        job_lay.addWidget(self.play_btn)
        job_lay.addWidget(self.pause_btn)
        job_lay.addWidget(self.stop_btn)
        body.addWidget(job_frame)

        self.queue_table = FCTable()
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["#", _("Job"), _("Lines"), _("Status")])
        self.queue_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.queue_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setMinimumHeight(128)
        self.queue_table.verticalHeader().hide()
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.queue_table.horizontalHeader().resizeSection(0, 28)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        body.addWidget(self.queue_table)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setObjectName("cnc_progress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        body.addWidget(self.progress)

    def build_sd_job(self, body):
        row_frame = QtWidgets.QFrame()
        row_frame.setObjectName("cnc_strip")
        lay = QtWidgets.QHBoxLayout(row_frame)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        self.sd_combo = FCComboBox()
        self.setup_input(self.sd_combo)
        self.sd_combo.setMinimumWidth(240)
        self.sd_list_btn = FluidStyleButton(_("Refresh SD"), "#444444", "#222222")
        self.run_sd_btn = FluidStyleButton(_("Run SD"), "#5cb85c", "#449d44")
        self.setup_button(self.sd_list_btn, "replot16.png", _("Refresh SD file list."))
        self.setup_button(self.run_sd_btn, "apply32.png", _("Run selected SD file."))
        lay.addWidget(FCLabel("SD:", bold=True))
        lay.addWidget(self.sd_combo, 1)
        lay.addWidget(self.sd_list_btn)
        lay.addWidget(self.run_sd_btn)
        body.addWidget(row_frame)

    def build_gcode_preview_verification(self, body):
        action_frame = QtWidgets.QFrame()
        action_frame.setObjectName("cnc_strip")
        action_lay = QtWidgets.QHBoxLayout(action_frame)
        action_lay.setContentsMargins(8, 6, 8, 6)
        action_lay.setSpacing(8)

        self.preview_source_label = FCLabel(_("Select a CNCJob or queue item."), bold=True)
        self.preview_refresh_btn = FluidStyleButton(_("Preview"), "#337ab7", "#286090")
        self.preview_verify_btn = FluidStyleButton(_("Verify"), "#5cb85c", "#449d44")
        self.setup_button(self.preview_refresh_btn, "replot16.png", _("Refresh G-code preview."))
        self.setup_button(self.preview_verify_btn, "apply32.png", _("Run G-code verification checks."))
        action_lay.addWidget(self.preview_source_label, 1)
        action_lay.addWidget(self.preview_refresh_btn)
        action_lay.addWidget(self.preview_verify_btn)
        self.live_placement_btn = FluidStyleButton(_("Live Placement"), "#ff6900", "#e65c00")
        self.setup_button(self.live_placement_btn, "edit16.png", _("Interactive mode to drag/rotate the job."))
        action_lay.addWidget(self.live_placement_btn)
        body.addWidget(action_frame)

        stats_grid = QtWidgets.QGridLayout()
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(4)
        body.addLayout(stats_grid)

        self.preview_lines_value = FCLabel("-")
        self.preview_motion_value = FCLabel("-")
        self.preview_distance_value = FCLabel("-")
        self.preview_bounds_value = FCLabel("-")
        self.preview_time_value = FCLabel("-")
        self.preview_warnings_value = FCLabel("-")
        stats = [
            (_("Lines"), self.preview_lines_value),
            (_("Motion"), self.preview_motion_value),
            (_("Distance"), self.preview_distance_value),
            (_("Bounds"), self.preview_bounds_value),
            (_("Est. Time"), self.preview_time_value),
            (_("Warnings"), self.preview_warnings_value),
        ]
        for index, (label, widget) in enumerate(stats):
            row = index // 3
            col = (index % 3) * 2
            stats_grid.addWidget(FCLabel(label, bold=True), row, col)
            stats_grid.addWidget(widget, row, col + 1)
        stats_grid.setColumnStretch(1, 1)
        stats_grid.setColumnStretch(3, 1)
        stats_grid.setColumnStretch(5, 1)

        preview_split_lay = QtWidgets.QHBoxLayout()
        preview_split_lay.setContentsMargins(0, 0, 0, 0)
        preview_split_lay.setSpacing(8)
        body.addLayout(preview_split_lay, 2)

        self.gcode_job_canvas = GCodeJobCanvas()
        self.gcode_job_canvas.setMinimumHeight(300)
        self.gcode_job_canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        preview_split_lay.addWidget(self.gcode_job_canvas, 1)

        preview_detail_lay = QtWidgets.QVBoxLayout()
        preview_detail_lay.setContentsMargins(0, 0, 0, 0)
        preview_detail_lay.setSpacing(8)
        preview_split_lay.addLayout(preview_detail_lay, 1)

        self.gcode_preview_text = QtWidgets.QTextEdit()
        self.gcode_preview_text.setObjectName("cnc_console")
        self.gcode_preview_text.setReadOnly(True)
        self.gcode_preview_text.setMinimumHeight(190)
        self.gcode_preview_text.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        preview_detail_lay.addWidget(self.gcode_preview_text, 2)

        self.gcode_warning_table = FCTable()
        self.gcode_warning_table.setColumnCount(3)
        self.gcode_warning_table.setHorizontalHeaderLabels([_("Level"), _("Line"), _("Message")])
        self.gcode_warning_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.gcode_warning_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.gcode_warning_table.setMinimumHeight(120)
        self.gcode_warning_table.verticalHeader().hide()
        self.gcode_warning_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.gcode_warning_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.gcode_warning_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        preview_detail_lay.addWidget(self.gcode_warning_table, 1)

    def build_terminal_console(self, body):
        options = QtWidgets.QHBoxLayout()
        self.poll_status_cb = QtWidgets.QCheckBox(_("Poll status"))
        self.poll_status_cb.setChecked(True)
        self.hide_status_reports_cb = QtWidgets.QCheckBox(_("Hide status reports"))
        self.hide_status_reports_cb.setChecked(True)
        options.addWidget(self.poll_status_cb)
        options.addWidget(self.hide_status_reports_cb)
        options.addStretch()
        body.addLayout(options)

        self.console = QtWidgets.QTextEdit()
        self.console.setObjectName("cnc_console")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(360)
        self.console.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        body.addWidget(self.console, 1)

        terminal_panel = body.parentWidget()
        if terminal_panel is not None:
            terminal_panel.setMinimumHeight(450)

        command_lay = QtWidgets.QHBoxLayout()
        self.command_entry = FCEntry()
        self.setup_input(self.command_entry)
        self.command_entry.setMinimumHeight(30)
        self.command_entry.setPlaceholderText(_("G-code / controller command"))
        command_lay.addWidget(self.command_entry, 1)
        body.addLayout(command_lay)

    def create_panel(self, title):
        panel = QtWidgets.QGroupBox(title)
        panel.setObjectName("cnc_panel")
        body_lay = QtWidgets.QVBoxLayout(panel)
        body_lay.setContentsMargins(8, 10, 8, 8)
        body_lay.setSpacing(6)
        return panel, body_lay

    def connection_config(self):
        port = self.com_port.currentText().strip().split(" - ", 1)[0]
        return {
            "mode": self.connection_mode_combo.currentData(),
            "port": port,
            "baudrate": int(self.baudrate_combo.currentText()),
            "host": self.tcp_host.text().strip(),
            "tcp_port": int(self.tcp_port.value()),
            "web_url": self.web_url.text().strip(),
            "user": self.web_user.text().strip(),
            "password": self.web_password.text(),
        }

    def get_jog_step(self):
        checked = self.step_group.checkedButton()
        if checked:
            return checked.property("step_value") or "1"
        return "1"

    def on_connection_mode_changed(self):
        index = self.connection_mode_combo.currentIndex()
        self.connection_stack.setCurrentIndex(index)

        mode = self.connection_mode_combo.currentData()
        self.connection_stack.setFixedHeight(120 if mode == "http" else 38)
        self.com_refresh.setVisible(mode == "serial")
        self.com_refresh.setEnabled(mode == "serial")
        if mode == "http":
            fluid_idx = self.profile_combo.findData("fluidnc")
            if fluid_idx >= 0:
                self.profile_combo.setCurrentIndex(fluid_idx)
        elif mode == "tcp":
            grbl_idx = self.profile_combo.findData("grbl")
            if grbl_idx >= 0:
                self.profile_combo.setCurrentIndex(grbl_idx)
        self.sync_connection_dialog(False)
        self.connection_dialog.adjustSize()
        self.set_file_tools_enabled(self.disconnect_btn.isVisible())

    def set_connected(self, connected):
        self.state_label.setText("IDLE" if connected else "OFFLINE")
        if not connected:
            self.state_indicator.setStyleSheet("background-color: #999999; border-radius: 6px;")
            if hasattr(self, 'feed_gauge'):
                self.update_dashboard_gauges(0, 0)
            if hasattr(self, "set_limit_pins"):
                self.set_limit_pins("")
        self.sync_connection_dialog(connected)

        controls = [
            self.play_btn, self.pause_btn, self.stop_btn,
            self.jog_up, self.jog_down, self.jog_left, self.jog_right, self.jog_z_up, self.jog_z_down,
            self.zero_x, self.zero_y, self.zero_z, self.zero_all, self.home_btn, self.unlock_btn,
            self.reset_btn, self.estop_btn, self.resume_btn, self.cfg_dump, self.info_btn,
            self.sd_list_btn, self.run_sd_btn, self.feed_override_entry, self.feed_set_btn,
            self.feed_plus, self.feed_minus, self.feed_reset, self.spindle_override_entry,
            self.spindle_override_set_btn, self.spindle_plus, self.spindle_minus, self.spindle_reset,
            self.spindle_rpm, self.spindle_set_btn, self.spindle_stop_btn, self.macro_laser,
            self.autolevel_probe_btn, self.autolevel_stop_btn,
            self.command_entry,
            self.files_refresh_btn, self.files_upload_btn, self.files_mkdir_btn,
            self.files_delete_btn, self.files_up_btn, self.files_root_btn
        ]
        for control in controls:
            if control is not None and hasattr(control, 'setEnabled'):
                control.setEnabled(connected)

        offline_controls = [
            self.object_combo, self.refresh_jobs_btn, self.queue_add_btn, self.queue_remove_btn,
            self.queue_up_btn, self.queue_down_btn, self.preview_refresh_btn, self.preview_verify_btn,
            self.queue_table, self.gcode_job_canvas, self.gcode_preview_text, self.gcode_warning_table,
            self.autolevel_enable_cb, self.autolevel_fit_btn, self.autolevel_clear_btn
        ]
        for control in offline_controls:
            if control is not None and hasattr(control, 'setEnabled'):
                control.setEnabled(True)

        self.set_file_tools_enabled(connected)

    def set_file_tools_enabled(self, enabled):
        for widget in [
            self.files_refresh_btn, self.files_upload_btn, self.files_mkdir_btn, self.files_delete_btn,
            self.files_root_btn, self.files_up_btn, self.files_fs_combo
        ]:
            widget.setEnabled(enabled)

    def update_files_table(self, data):
        self.files_table.setRowCount(0)

        path = data.get("path", self.current_path) or "/"
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path += "/"
        self.current_path = path
        self.path_label.setText(path)

        files = data.get("files", [])
        files = sorted(files, key=lambda f: (str(f.get("size")) != "-1", str(f.get("name", "")).lower()))

        for file_info in files:
            name = str(file_info.get("name", ""))
            size = str(file_info.get("size", ""))
            is_dir = size == "-1"
            row = self.files_table.rowCount()
            self.files_table.insertRow(row)

            type_item = QtWidgets.QTableWidgetItem("DIR" if is_dir else "FILE")
            name_item = QtWidgets.QTableWidgetItem(name)
            size_item = QtWidgets.QTableWidgetItem("" if is_dir else size)
            time_item = QtWidgets.QTableWidgetItem(str(file_info.get("time", "")))

            payload = {"name": name, "is_dir": is_dir, "raw": file_info}
            for item in [type_item, name_item, size_item, time_item]:
                item.setData(Qt.ItemDataRole.UserRole, payload)

            self.files_table.setItem(row, 0, type_item)
            self.files_table.setItem(row, 1, name_item)
            self.files_table.setItem(row, 2, size_item)
            self.files_table.setItem(row, 3, time_item)

        status = data.get("status", "OK")
        total = data.get("total", "")
        used = data.get("used", "")
        occupation = data.get("occupation", "")
        parts = [f"Status: {status}"]
        if total:
            parts.append(f"Total: {total}")
        if used:
            parts.append(f"Used: {used}")
        if occupation:
            parts.append(f"Occupation: {occupation}%")
        self.file_status.setText(" | ".join(parts))

    def selected_file_item(self):
        selected = self.files_table.selectedItems()
        if not selected:
            return None
        return selected[0].data(Qt.ItemDataRole.UserRole)

    def clear_sd_files(self):
        self.sd_combo.clear()

    def add_sd_file(self, filename):
        if filename and self.sd_combo.findText(filename) < 0:
            self.sd_combo.addItem(filename)

    def update_controller_info(self, info):
        hostname = info.get("hostname", "")
        target = info.get("FW target", "")
        details = " | ".join(value for value in [hostname, target] if value)
        self.controller_info_label.setText(details)
        self.sync_connection_dialog(self.disconnect_btn.isVisible())

    def update_dashboard_gauges(self, feed, spindle):
        if hasattr(self, 'feed_gauge'):
            self.feed_gauge.set_value(feed)
        if hasattr(self, 'spindle_gauge'):
            self.spindle_gauge.set_value(spindle)

    def set_limit_pins(self, pins):
        pins = set(str(pins or "").upper())
        for axis, label in [
            ("X", getattr(self, "limit_x", None)),
            ("Y", getattr(self, "limit_y", None)),
            ("Z", getattr(self, "limit_z", None)),
        ]:
            if label is None:
                continue
            if axis in pins:
                label.setText(_("TRIG"))
                label.setToolTip(_("%s limit input is active.") % axis)
                label.setStyleSheet("color: #d9534f; font-weight: 800;")
            else:
                label.setText("-")
                label.setToolTip("")
                label.setStyleSheet("color: #777777; font-weight: 700;")

    def set_busy(self, busy, message):
        self.busy_label.setText(message if busy else "")

    def append_console(self, text, entry_type):
        color = {
            "tx": "#569cd6",
            "rx": "#d4d4d4",
            "info": "#6a9955",
            "warn": "#d7ba7d",
            "error": "#f44747",
        }.get(entry_type, "#d4d4d4")

        safe_text = html.escape(str(text))
        timestamp = time.strftime("%H:%M:%S")
        self.console.append(
            f'<span style="color:#808080;">[{timestamp}]</span> '
            f'<span style="color:{color};">{safe_text}</span>'
        )
        self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)


class CNCPreviewModal(QtWidgets.QDialog):
    placement_changed = QtCore.pyqtSignal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_('CNC Live Placement & Simulation'))
        self.setMinimumSize(1200, 900)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self._syncing_placement = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.canvas = GCodeJobCanvas()
        self.canvas.enable_fs_button = False  # No recursive full screen
        self.canvas.placement_changed.connect(self.on_canvas_placement_changed)
        layout.addWidget(self.canvas)

        bottom_lay = QtWidgets.QHBoxLayout()

        def placement_spinner(minimum, maximum, decimals, step, suffix=""):
            spinner = QtWidgets.QDoubleSpinBox()
            spinner.setRange(minimum, maximum)
            spinner.setDecimals(decimals)
            spinner.setSingleStep(step)
            spinner.setSuffix(suffix)
            spinner.setKeyboardTracking(False)
            spinner.setFixedWidth(118)
            spinner.valueChanged.connect(self.on_placement_input_changed)
            return spinner

        self.place_x_spin = placement_spinner(-100000.0, 100000.0, 3, 0.1, " mm")
        self.place_y_spin = placement_spinner(-100000.0, 100000.0, 3, 0.1, " mm")
        self.place_rotation_spin = placement_spinner(-3600.0, 3600.0, 2, 1.0, " deg")

        bottom_lay.addWidget(FCLabel(_("X"), bold=True))
        bottom_lay.addWidget(self.place_x_spin)
        bottom_lay.addWidget(FCLabel(_("Y"), bold=True))
        bottom_lay.addWidget(self.place_y_spin)
        bottom_lay.addWidget(FCLabel(_("Angle"), bold=True))
        bottom_lay.addWidget(self.place_rotation_spin)

        self.save_btn = FluidStyleButton(_("SAVE PLACEMENT"), "#ff6900", "#e65c00")
        self.save_btn.clicked.connect(self.accept)

        close_btn = FluidStyleButton(_("Close"), "#777777", "#666666")
        close_btn.clicked.connect(self.reject)

        bottom_lay.addStretch()
        bottom_lay.addWidget(self.save_btn)
        bottom_lay.addWidget(close_btn)
        layout.addLayout(bottom_lay)

    def set_preview(self, preview):
        self.canvas.set_preview(preview)

    def set_placement(self, dx, dy, rotation, emit=False):
        self._syncing_placement = True
        try:
            self.place_x_spin.setValue(float(dx or 0.0))
            self.place_y_spin.setValue(float(dy or 0.0))
            self.place_rotation_spin.setValue(float(rotation or 0.0))
            self.canvas.sync_placement(dx, dy, rotation)
        finally:
            self._syncing_placement = False
        if emit:
            self.placement_changed.emit(float(dx or 0.0), float(dy or 0.0), float(rotation or 0.0))

    def on_canvas_placement_changed(self, dx, dy, rotation):
        self.set_placement(dx, dy, rotation, emit=False)
        self.placement_changed.emit(dx, dy, rotation)

    def on_placement_input_changed(self, *_args):
        if self._syncing_placement:
            return
        dx = float(self.place_x_spin.value())
        dy = float(self.place_y_spin.value())
        rotation = float(self.place_rotation_spin.value())
        self.canvas.sync_placement(dx, dy, rotation)
        self.placement_changed.emit(dx, dy, rotation)
