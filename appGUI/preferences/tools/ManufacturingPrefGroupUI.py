# ##########################################################
# FlatCAM PLUS: 2D Post-processing for Manufacturing       #
# File Updated By Sadri ERCAN - 2026                      #
# License:  MIT Licence                                   #
# ##########################################################

from PyQt6.QtCore import QSettings

from appGUI.GUIElements import FCButton, FCFrame, FCLabel, GLay
from appGUI.preferences.OptionsGroupUI import OptionsGroupUI
from appPlugins.cnc_control.dialogs import MachineProfileDialog
from appPlugins.cnc_control.machine_profiles import normalize_machine_profiles

import gettext
import appTranslation as fcTranslate
import builtins
import json

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class ManufacturingPrefGroupUI(OptionsGroupUI):
    def __init__(self, app, parent=None):
        super(ManufacturingPrefGroupUI, self).__init__(self, parent=parent)

        self.setTitle(str(_("Manufacturing Settings")))
        self.app = app

        self.machine_label = FCLabel('%s' % _("Machine Profiles"), color='darkblue', bold=True)
        self.machine_label.setToolTip(
            _("Machine profiles keep CNC limits, safe Z, jog feed and probing feed in one place.")
        )
        self.layout.addWidget(self.machine_label)

        machine_frame = FCFrame()
        self.layout.addWidget(machine_frame)

        machine_grid = GLay(v_spacing=5, h_spacing=3)
        machine_frame.setLayout(machine_grid)

        self.machine_profile_status = FCLabel("")
        self.machine_profile_status.setWordWrap(True)
        machine_grid.addWidget(self.machine_profile_status, 0, 0, 1, 2)

        self.manage_machine_profiles_btn = FCButton(_("Manage Machine Profiles"))
        self.manage_machine_profiles_btn.setToolTip(
            _("Create and edit CNC machine profiles without opening the CNC Control plugin.")
        )
        self.manage_machine_profiles_btn.clicked.connect(self.on_manage_machine_profiles)
        machine_grid.addWidget(self.manage_machine_profiles_btn, 2, 0, 1, 2)

        self.workflow_label = FCLabel('%s' % _("Fallback Defaults"), color='blue', bold=True)
        self.workflow_label.setToolTip(
            _("Tool-specific values should be stored in Tools Database presets. Preferences are fallback values.")
        )
        self.layout.addWidget(self.workflow_label)

        workflow_frame = FCFrame()
        self.layout.addWidget(workflow_frame)

        workflow_grid = GLay(v_spacing=5, h_spacing=3)
        workflow_frame.setLayout(workflow_grid)

        self.tooling_status = FCLabel(
            "%s\n%s\n%s" % (
                _("Tool presets: define cutting values in the Tools Database."),
                _("Fallback defaults: use Milling, Drilling, Cutout and engraving groups only for missing values."),
                _("Output defaults: use CNCJob preferences.")
            )
        )
        self.tooling_status.setWordWrap(True)
        workflow_grid.addWidget(self.tooling_status, 0, 0, 1, 2)

        self.refresh_machine_profile_status()
        self.layout.addStretch()

    def _load_machine_profiles(self):
        settings = QSettings("Open Source", "FlatCAM_Plus")
        profiles = []
        if settings.contains("cnc_machine_profiles"):
            try:
                profiles = json.loads(settings.value("cnc_machine_profiles"))
            except (TypeError, json.JSONDecodeError):
                profiles = []

        profiles = normalize_machine_profiles(profiles)
        active_name = settings.value("cnc_active_machine_profile", "")
        names = {profile["name"] for profile in profiles}
        if active_name not in names:
            active_name = profiles[0]["name"]
        return profiles, active_name

    def _save_machine_profiles(self, profiles, active_name):
        settings = QSettings("Open Source", "FlatCAM_Plus")
        settings.setValue("cnc_machine_profiles", json.dumps(profiles))
        settings.setValue("cnc_active_machine_profile", active_name)

    def refresh_machine_profile_status(self):
        profiles, active_name = self._load_machine_profiles()
        active_profile = None
        for profile in profiles:
            if profile["name"] == active_name:
                active_profile = profile
                break
        if active_profile is None:
            active_profile = profiles[0]

        self.machine_profile_status.setText(
            "%s: %s\n%s: %.3f mm   %s: %s mm/min   %s: %s mm/min   %s: %s RPM" % (
                _("Active profile"), active_profile["name"],
                _("Safe Z"), active_profile["safe_z"],
                _("Jog feed"), active_profile["jog_feed"],
                _("Probe feed"), active_profile["probe_feed"],
                _("Max spindle"), active_profile["spindle_max"]
            )
        )

    def on_manage_machine_profiles(self):
        profiles, active_name = self._load_machine_profiles()
        dialog = MachineProfileDialog(profiles, active_name, self)
        if dialog.exec():
            profiles = normalize_machine_profiles(dialog.profiles)
            active_name = dialog.active_name
            names = {profile["name"] for profile in profiles}
            if active_name not in names:
                active_name = profiles[0]["name"]
            self._save_machine_profiles(profiles, active_name)
            self.refresh_machine_profile_status()

            cnc_tool = getattr(self.app, "cnc_control_tool", None)
            if cnc_tool is not None and hasattr(cnc_tool, "load_machine_profiles"):
                cnc_tool.load_machine_profiles()
