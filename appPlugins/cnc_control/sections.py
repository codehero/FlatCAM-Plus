# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import builtins
import gettext

from PyQt6 import QtWidgets

from appGUI.GUIElements import FCComboBox, FCDoubleSpinner, FCLabel, FCSpinner

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
        ui.machine_probe_feed_value = FCLabel("-")
        ui.machine_spindle_max_value = FCLabel("-")
        ui.machine_travel_value = FCLabel("-")

        rows = [
            (_("Safe Z"), ui.machine_safe_z_value),
            (_("Jog Feed"), ui.machine_jog_feed_value),
            (_("Probe Feed"), ui.machine_probe_feed_value),
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
    title = _("Probing / Work Offset")

    def build(self, ui, body):
        settings_grid = QtWidgets.QGridLayout()
        settings_grid.setHorizontalSpacing(8)
        settings_grid.setVerticalSpacing(6)
        body.addLayout(settings_grid)

        ui.work_offset_combo = FCComboBox()
        ui.setup_input(ui.work_offset_combo)
        for label, p_num in [
            ("G54", 1), ("G55", 2), ("G56", 3), ("G57", 4), ("G58", 5), ("G59", 6)
        ]:
            ui.work_offset_combo.addItem(label, p_num)
        ui.work_offset_combo.setToolTip(_("Work coordinate system used for zeroing commands."))

        ui.probe_distance = FCDoubleSpinner()
        ui.setup_input(ui.probe_distance)
        ui.probe_distance.set_precision(3)
        ui.probe_distance.set_range(0.1, 1000.0)
        ui.probe_distance.setSingleStep(1.0)
        ui.probe_distance.setValue(50.0)
        ui.probe_distance.setSuffix(" mm")
        ui.probe_distance.setToolTip(_("Maximum downward probe travel."))

        ui.probe_feed = FCSpinner()
        ui.setup_input(ui.probe_feed)
        ui.probe_feed.set_range(1, 60000)
        ui.probe_feed.setValue(100)
        ui.probe_feed.setSuffix(" mm/min")
        ui.probe_feed.setToolTip(_("Probe feed rate. Defaults from the active machine profile."))

        ui.touch_plate_thickness = FCDoubleSpinner()
        ui.setup_input(ui.touch_plate_thickness)
        ui.touch_plate_thickness.set_precision(3)
        ui.touch_plate_thickness.set_range(-1000.0, 1000.0)
        ui.touch_plate_thickness.setSingleStep(0.1)
        ui.touch_plate_thickness.setValue(0.0)
        ui.touch_plate_thickness.setSuffix(" mm")
        ui.touch_plate_thickness.setToolTip(_("Touch plate thickness used when setting Z after probing."))

        ui.probe_retract = FCDoubleSpinner()
        ui.setup_input(ui.probe_retract)
        ui.probe_retract.set_precision(3)
        ui.probe_retract.set_range(0.0, 1000.0)
        ui.probe_retract.setSingleStep(0.5)
        ui.probe_retract.setValue(5.0)
        ui.probe_retract.setSuffix(" mm")
        ui.probe_retract.setToolTip(_("Retract distance after probe and set."))

        settings = [
            (_("WCS"), ui.work_offset_combo),
            (_("Probe Travel"), ui.probe_distance),
            (_("Probe Feed"), ui.probe_feed),
            (_("Plate"), ui.touch_plate_thickness),
            (_("Retract"), ui.probe_retract),
        ]
        for idx, (label, widget) in enumerate(settings):
            settings_grid.addWidget(FCLabel(label, bold=True), idx // 2, (idx % 2) * 2)
            settings_grid.addWidget(widget, idx // 2, (idx % 2) * 2 + 1)

        button_grid = QtWidgets.QGridLayout()
        button_grid.setSpacing(6)
        body.addLayout(button_grid)

        ui.probe_z_btn = FluidStyleButton(_("Probe Z"), "#337ab7", "#286090")
        ui.probe_set_z_btn = FluidStyleButton(_("Probe + Set Z"), "#5cb85c", "#449d44")
        ui.set_xy_zero_btn = FluidStyleButton(_("Set XY Zero"), "#444444", "#222222")
        ui.set_z_zero_btn = FluidStyleButton(_("Set Z Zero"), "#444444", "#222222")
        ui.set_xyz_zero_btn = FluidStyleButton(_("Set XYZ Zero"), "#444444", "#222222")
        ui.apply_wcs_btn = FluidStyleButton(_("Use WCS"), "#5bc0de", "#31b0d5")

        ui.setup_button(ui.probe_z_btn, "machine16.png", _("Run a Z probe move."))
        ui.setup_button(ui.probe_set_z_btn, "apply32.png", _("Probe Z, set work Z to plate thickness, then retract."))
        ui.setup_button(ui.set_xy_zero_btn, "origin16.png", _("Set current X/Y position as work zero."))
        ui.setup_button(ui.set_z_zero_btn, "origin16.png", _("Set current Z position as work zero."))
        ui.setup_button(ui.set_xyz_zero_btn, "origin16.png", _("Set current X/Y/Z position as work zero."))
        ui.setup_button(ui.apply_wcs_btn, "apply32.png", _("Activate the selected work coordinate system."))

        button_grid.addWidget(ui.probe_z_btn, 0, 0)
        button_grid.addWidget(ui.probe_set_z_btn, 0, 1)
        button_grid.addWidget(ui.apply_wcs_btn, 0, 2)
        button_grid.addWidget(ui.set_xy_zero_btn, 1, 0)
        button_grid.addWidget(ui.set_z_zero_btn, 1, 1)
        button_grid.addWidget(ui.set_xyz_zero_btn, 1, 2)
        for column in range(3):
            button_grid.setColumnStretch(column, 1)


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
