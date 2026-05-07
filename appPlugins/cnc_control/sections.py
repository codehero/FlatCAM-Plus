# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import builtins
import gettext

from PyQt6 import QtWidgets

from appGUI.GUIElements import FCComboBox, FCDoubleSpinner, FCLabel

from .widgets import DashboardGauge, FluidStyleButton

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class CNCSectionPlugin:
    section_id = ""
    title = ""

    def build_panel(self, ui):
        panel, body = ui.create_panel(self.title)
        self.build(ui, body)
        return panel

    def build(self, ui, body):
        raise NotImplementedError


class GaugeSection(CNCSectionPlugin):
    section_id = "gauges"
    title = _("Feed / Spindle")

    def build(self, ui, body):
        gauge_lay = QtWidgets.QHBoxLayout()
        gauge_lay.setContentsMargins(0, 0, 0, 0)
        gauge_lay.setSpacing(8)
        body.addLayout(gauge_lay)

        ui.feed_gauge = DashboardGauge(_("Feed"), "mm/min", 6000, "#31b0d5")
        ui.spindle_gauge = DashboardGauge(_("Spindle"), "RPM", 24000, "#d9534f")
        ui.feed_gauge.setToolTip(_("Live feed rate from controller status."))
        ui.spindle_gauge.setToolTip(_("Live spindle speed from controller status."))
        gauge_lay.addWidget(ui.feed_gauge, 1)
        gauge_lay.addWidget(ui.spindle_gauge, 1)


class JobStreamingSection(CNCSectionPlugin):
    section_id = "job_streaming"
    title = _("Job Queue / Sender")

    def build(self, ui, body):
        ui.build_direct_job(body)
        ui.build_sd_job(body)


class GCodePreviewVerificationSection(CNCSectionPlugin):
    section_id = "gcode_preview_verification"
    title = _("G-Code Preview / Verification")

    def build(self, ui, body):
        ui.build_gcode_preview_verification(body)


class MachineProfileSection(CNCSectionPlugin):
    section_id = "machine_profiles"
    title = _("Machine Profile")

    def build(self, ui, body):
        selector_lay = QtWidgets.QHBoxLayout()
        selector_lay.setContentsMargins(0, 0, 0, 0)
        selector_lay.setSpacing(6)

        ui.machine_profile_combo = FCComboBox()
        ui.setup_input(ui.machine_profile_combo)
        ui.machine_profile_combo.setMinimumWidth(180)
        ui.manage_machine_profiles_btn = FluidStyleButton(_("Manage"), "#337ab7", "#286090")
        ui.setup_button(ui.manage_machine_profiles_btn, "settings18.png", _("Open Machine Profiles."))

        selector_lay.addWidget(ui.machine_profile_combo, 1)
        selector_lay.addWidget(ui.manage_machine_profiles_btn)
        body.addLayout(selector_lay)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        body.addLayout(grid)

        ui.machine_safe_z_value = FCLabel("-")
        ui.machine_jog_feed_value = FCLabel("-")
        ui.machine_spindle_max_value = FCLabel("-")
        ui.machine_travel_value = FCLabel("-")

        rows = [
            (_("Safe Z"), ui.machine_safe_z_value),
            (_("Jog Feed"), ui.machine_jog_feed_value),
            (_("Max Spindle"), ui.machine_spindle_max_value),
            (_("Travel"), ui.machine_travel_value),
        ]
        for row, (label, value) in enumerate(rows):
            grid.addWidget(FCLabel(label, bold=True), row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)


class PositionSection(CNCSectionPlugin):
    section_id = "position"
    title = _("Position")

    def build(self, ui, body):
        ui.build_dro(body)


class JogSection(CNCSectionPlugin):
    section_id = "jog"
    title = _("Jog")

    def build(self, ui, body):
        ui.build_jog(body)


class ProbingWorkOffsetSection(CNCSectionPlugin):
    section_id = "probing_work_offset"
    title = _("Job Setup / Zero")

    def build(self, ui, body):
        def setup_job_input(widget):
            ui.setup_input(widget)
            widget.setFixedHeight(34)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            return widget

        job_grid = QtWidgets.QGridLayout()
        job_grid.setHorizontalSpacing(8)
        job_grid.setVerticalSpacing(6)
        body.addLayout(job_grid)

        ui.job_size_x = FCDoubleSpinner()
        setup_job_input(ui.job_size_x)
        ui.job_size_x.set_precision(3)
        ui.job_size_x.set_range(0.0, 100000.0)
        ui.job_size_x.setSingleStep(1.0)
        ui.job_size_x.setSuffix(" mm")
        ui.job_size_x.setToolTip(_("Job/material width used for origin mapping. Zero means fit the selected CNCJob."))

        ui.job_size_y = FCDoubleSpinner()
        setup_job_input(ui.job_size_y)
        ui.job_size_y.set_precision(3)
        ui.job_size_y.set_range(0.0, 100000.0)
        ui.job_size_y.setSingleStep(1.0)
        ui.job_size_y.setSuffix(" mm")
        ui.job_size_y.setToolTip(_("Job/material height used for origin mapping. Zero means fit the selected CNCJob."))

        ui.fit_job_size_btn = FluidStyleButton(_("Fit Size"), "#337ab7", "#286090")
        ui.setup_button(ui.fit_job_size_btn, "replot16.png", _("Set job size from the selected CNCJob bounds."))

        ui.job_margin_x = FCDoubleSpinner()
        setup_job_input(ui.job_margin_x)
        ui.job_margin_x.set_precision(3)
        ui.job_margin_x.set_range(0.0, 100000.0)
        ui.job_margin_x.setSingleStep(0.1)
        ui.job_margin_x.setSuffix(" mm")
        ui.job_margin_x.setToolTip(_("X clearance inside the selected job size."))

        ui.job_margin_y = FCDoubleSpinner()
        setup_job_input(ui.job_margin_y)
        ui.job_margin_y.set_precision(3)
        ui.job_margin_y.set_range(0.0, 100000.0)
        ui.job_margin_y.setSingleStep(0.1)
        ui.job_margin_y.setSuffix(" mm")
        ui.job_margin_y.setToolTip(_("Y clearance inside the selected job size."))

        ui.job_origin_combo = FCComboBox()
        setup_job_input(ui.job_origin_combo)
        ui.job_origin_combo.addItem(_("Origin: Back-Left"), "top_left")
        ui.job_origin_combo.addItem(_("Origin: Bottom-Left"), "bottom_left")
        ui.job_origin_combo.addItem(_("Origin: Center"), "center")
        ui.job_origin_combo.addItem(_("Use G-code Absolute XY"), "absolute")
        ui.job_origin_combo.setToolTip(_("Which point of the selected job size is mapped to the zeroed work point."))

        ui.job_placement_combo = FCComboBox()
        setup_job_input(ui.job_placement_combo)
        ui.job_placement_combo.addItem(_("Place: Same as Origin"), "origin")
        ui.job_placement_combo.addItem(_("Place: Center"), "center")
        ui.job_placement_combo.addItem(_("Place: Bottom-Left"), "bottom_left")
        ui.job_placement_combo.addItem(_("Place: Bottom-Center"), "bottom_center")
        ui.job_placement_combo.addItem(_("Place: Bottom-Right"), "bottom_right")
        ui.job_placement_combo.addItem(_("Place: Center-Left"), "center_left")
        ui.job_placement_combo.addItem(_("Place: Center-Right"), "center_right")
        ui.job_placement_combo.addItem(_("Place: Back-Left"), "top_left")
        ui.job_placement_combo.addItem(_("Place: Back-Center"), "top_center")
        ui.job_placement_combo.addItem(_("Place: Back-Right"), "top_right")
        ui.job_placement_combo.setToolTip(_("Where the selected CNCJob is placed inside the job/material size."))

        job_grid.addWidget(FCLabel(_("Job W"), bold=True), 0, 0)
        job_grid.addWidget(ui.job_size_x, 0, 1)
        job_grid.addWidget(FCLabel(_("Job H"), bold=True), 0, 2)
        job_grid.addWidget(ui.job_size_y, 0, 3)
        job_grid.addWidget(ui.fit_job_size_btn, 0, 4)
        job_grid.addWidget(FCLabel(_("Origin"), bold=True), 1, 0)
        job_grid.addWidget(ui.job_origin_combo, 1, 1, 1, 4)
        job_grid.addWidget(FCLabel(_("Placement"), bold=True), 2, 0)
        job_grid.addWidget(ui.job_placement_combo, 2, 1, 1, 4)
        job_grid.addWidget(FCLabel(_("Margin X"), bold=True), 3, 0)
        job_grid.addWidget(ui.job_margin_x, 3, 1)
        job_grid.addWidget(FCLabel(_("Margin Y"), bold=True), 3, 2)
        job_grid.addWidget(ui.job_margin_y, 3, 3, 1, 2)
        job_grid.setColumnStretch(1, 1)
        job_grid.setColumnStretch(3, 1)

        button_grid = QtWidgets.QGridLayout()
        button_grid.setSpacing(6)
        body.addLayout(button_grid)

        ui.set_xy_zero_btn = FluidStyleButton(_("Set XY Zero"), "#444444", "#222222")
        ui.set_z_zero_btn = FluidStyleButton(_("Set Z Zero"), "#444444", "#222222")
        ui.set_xyz_zero_btn = FluidStyleButton(_("Set XYZ Zero"), "#444444", "#222222")

        ui.setup_button(ui.set_xy_zero_btn, "origin16.png", _("Set current X/Y position as work zero."))
        ui.setup_button(ui.set_z_zero_btn, "origin16.png", _("Set current Z position as work zero."))
        ui.setup_button(ui.set_xyz_zero_btn, "origin16.png", _("Set current X/Y/Z position as work zero."))

        button_grid.addWidget(ui.set_xy_zero_btn, 0, 0)
        button_grid.addWidget(ui.set_z_zero_btn, 0, 1)
        button_grid.addWidget(ui.set_xyz_zero_btn, 0, 2)
        for column in range(3):
            button_grid.setColumnStretch(column, 1)
        body.addStretch(1)


class OverridesSystemSection(CNCSectionPlugin):
    section_id = "overrides_system"
    title = _("Overrides & System")

    def build(self, ui, body):
        ui.build_system(body)


class MacroSection(CNCSectionPlugin):
    section_id = "macros"
    title = _("Saved Macros")

    def build(self, ui, body):
        ui.macro_list = QtWidgets.QListWidget()
        ui.macro_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        ui.macro_list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        ui.macro_list.setMinimumHeight(140)
        body.addWidget(ui.macro_list, 1)

        ui.manage_macros_btn = FluidStyleButton(_("Manage Macros"), "#337ab7", "#286090")
        ui.setup_button(ui.manage_macros_btn, "settings18.png", _("Open Macro Management Dialog."))
        body.addWidget(ui.manage_macros_btn)


class TerminalSection(CNCSectionPlugin):
    section_id = "terminal"
    title = _("Terminal Console")

    def build(self, ui, body):
        ui.build_terminal_console(body)


class ModalActionsSection:
    section_id = "modal_actions"

    def build_widget(self, ui):
        actions_frame = QtWidgets.QFrame()
        actions_frame.setObjectName("cnc_strip")
        actions_lay = QtWidgets.QHBoxLayout(actions_frame)
        actions_lay.setContentsMargins(8, 6, 8, 6)
        actions_lay.setSpacing(8)

        ui.files_dialog_btn = FluidStyleButton(_("Flash File System"), "#337ab7", "#286090")
        ui.setup_button(ui.files_dialog_btn, "folder16.png", _("Open Flash Filesystem operations."))

        actions_lay.addWidget(ui.files_dialog_btn)
        actions_lay.addStretch()
        return actions_frame


DEFAULT_CNC_SECTIONS = {
    "gauges": GaugeSection,
    "job_streaming": JobStreamingSection,
    "gcode_preview_verification": GCodePreviewVerificationSection,
    "machine_profiles": MachineProfileSection,
    "position": PositionSection,
    "jog": JogSection,
    "probing_work_offset": ProbingWorkOffsetSection,
    "overrides_system": OverridesSystemSection,
    "macros": MacroSection,
    "terminal": TerminalSection,
    "modal_actions": ModalActionsSection,
}
