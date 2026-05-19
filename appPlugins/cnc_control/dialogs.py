# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import builtins
import gettext

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal

from appGUI.GUIElements import FCComboBox, FCLabel, FCTable

from .machine_profiles import normalize_machine_profile, normalize_machine_profiles
from .widgets import FluidStyleButton

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class FileSystemDialog(QtWidgets.QDialog):
    def __init__(self, owner, parent=None):
        parent_widget = parent if parent is not None else owner.app.ui
        super().__init__(parent_widget)
        self.owner = owner
        self.setWindowTitle(_("Flash Filesystem"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(owner.stylesheet())

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        panel, body = owner.create_panel(_("Flash Filesystem"))
        lay.addWidget(panel, 1)

        toolbar = QtWidgets.QHBoxLayout()
        self.files_fs_combo = FCComboBox()
        owner.setup_input(self.files_fs_combo)
        self.files_fs_combo.setMinimumWidth(160)
        self.files_fs_combo.addItem(_("Flash filesystem"), "/files")
        self.files_fs_combo.addItem(_("Direct SD"), "/upload")

        self.files_refresh_btn = FluidStyleButton(_("Refresh"), "#337ab7", "#286090")
        self.files_upload_btn = FluidStyleButton(_("Upload"), "#5bc0de", "#31b0d5")
        self.files_mkdir_btn = FluidStyleButton(_("New folder"), "#5bc0de", "#31b0d5")
        self.files_delete_btn = FluidStyleButton(_("Delete"), "#d9534f", "#c9302c")
        self.files_root_btn = FluidStyleButton("/", "#ffffff", "#f5f5f5", "#333333")
        self.files_up_btn = FluidStyleButton(_("Up"), "#ffffff", "#f5f5f5", "#333333")

        owner.setup_button(self.files_refresh_btn, "replot16.png", _("Refresh file list."))
        owner.setup_button(self.files_upload_btn, "folder16.png", _("Upload files to the controller."))
        owner.setup_button(self.files_mkdir_btn, "plus16.png", _("Create a folder."))
        owner.setup_button(self.files_delete_btn, "trash16.png", _("Delete selected file or folder."))
        owner.setup_button(self.files_root_btn, "home16.png", _("Go to root folder."))
        owner.setup_button(self.files_up_btn, "up-arrow32.png", _("Go to parent folder."))

        self.path_label = FCLabel("/", color="#31708f")
        toolbar.addWidget(self.files_fs_combo)
        toolbar.addWidget(self.files_refresh_btn)
        toolbar.addWidget(self.files_upload_btn)
        toolbar.addWidget(self.files_mkdir_btn)
        toolbar.addWidget(self.files_delete_btn)
        toolbar.addWidget(self.files_root_btn)
        toolbar.addWidget(self.files_up_btn)
        toolbar.addWidget(self.path_label, 1)
        body.addLayout(toolbar)

        self.files_table = FCTable()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels([_("Type"), _("Name"), _("Size"), _("Time")])
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.files_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.files_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.files_table.verticalHeader().hide()
        body.addWidget(self.files_table, 1)

        self.file_status = FCLabel(_("HTTP file manager is available in FluidNC Web mode."), color="#31708f")
        self.busy_label = FCLabel("", color="#31708f")
        body.addWidget(self.file_status)
        body.addWidget(self.busy_label)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()
        close_btn = QtWidgets.QPushButton(_("Close"))
        close_btn.clicked.connect(self.hide)
        bottom.addWidget(close_btn)
        lay.addLayout(bottom)


class MacroDialog(QtWidgets.QDialog):
    macros_changed = pyqtSignal(list)

    def __init__(self, macros, parent=None):
        super().__init__(parent)
        self.macros = [dict(m) for m in macros] # Copy
        self.setWindowTitle("Macro Management")
        self.setMinimumSize(600, 400)

        # UI from parent theme
        if parent is not None and hasattr(parent, "ui"):
            self.setStyleSheet(parent.ui.stylesheet())

        lay = QtWidgets.QVBoxLayout(self)

        main_h = QtWidgets.QHBoxLayout()
        lay.addLayout(main_h)

        # List
        list_panel = QtWidgets.QGroupBox("Saved Macros")
        list_lay = QtWidgets.QVBoxLayout(list_panel)
        self.macro_list = QtWidgets.QListWidget()
        self.macro_add_btn = FluidStyleButton("NEW MACRO", "#5cb85c", "#449d44")
        list_lay.addWidget(self.macro_list)
        list_lay.addWidget(self.macro_add_btn)
        main_h.addWidget(list_panel, 1)

        # Editor
        edit_panel = QtWidgets.QGroupBox("Edit Macro")
        edit_lay = QtWidgets.QVBoxLayout(edit_panel)
        self.macro_name_edit = QtWidgets.QLineEdit()
        self.macro_content_edit = QtWidgets.QPlainTextEdit()
        self.macro_content_edit.setPlaceholderText("Enter G-Code commands...")
        edit_lay.addWidget(QtWidgets.QLabel("Name:"))
        edit_lay.addWidget(self.macro_name_edit)
        edit_lay.addWidget(QtWidgets.QLabel("Commands:"))
        edit_lay.addWidget(self.macro_content_edit)

        btn_lay = QtWidgets.QHBoxLayout()
        self.macro_save_btn = FluidStyleButton("SAVE", "#337ab7", "#286090")
        self.macro_delete_btn = FluidStyleButton("DELETE", "#d9534f", "#c9302c")
        btn_lay.addWidget(self.macro_save_btn)
        btn_lay.addWidget(self.macro_delete_btn)
        edit_lay.addLayout(btn_lay)
        main_h.addWidget(edit_panel, 2)

        # Bottom Buttons
        bottom = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        lay.addLayout(bottom)

        # Signals
        self.macro_add_btn.clicked.connect(self.on_add)
        self.macro_save_btn.clicked.connect(self.on_save)
        self.macro_delete_btn.clicked.connect(self.on_delete)
        self.macro_list.itemSelectionChanged.connect(self.on_selection_changed)

        self.refresh_list()

    def refresh_list(self):
        self.macro_list.clear()
        for m in self.macros:
            self.macro_list.addItem(m["name"])

    def on_add(self):
        self.macro_list.clearSelection()
        self.macro_name_edit.setText("New Macro")
        self.macro_content_edit.clear()

    def on_save(self):
        name = self.macro_name_edit.text().strip()
        content = self.macro_content_edit.toPlainText().strip()
        if not name: return

        sel = self.macro_list.selectedItems()
        if sel:
            idx = self.macro_list.row(sel[0])
            self.macros[idx] = {"name": name, "content": content}
        else:
            idx = len(self.macros)
            self.macros.append({"name": name, "content": content})
        self.refresh_list()
        self.macro_list.setCurrentRow(idx)
        self.macros_changed.emit([dict(m) for m in self.macros])

    def on_delete(self):
        sel = self.macro_list.selectedItems()
        if not sel: return
        idx = self.macro_list.row(sel[0])
        self.macros.pop(idx)
        self.refresh_list()
        next_row = min(idx, len(self.macros) - 1)
        if next_row >= 0:
            self.macro_list.setCurrentRow(next_row)
        else:
            self.macro_name_edit.clear()
            self.macro_content_edit.clear()
        self.macros_changed.emit([dict(m) for m in self.macros])

    def on_selection_changed(self):
        sel = self.macro_list.selectedItems()
        if not sel: return
        idx = self.macro_list.row(sel[0])
        m = self.macros[idx]
        self.macro_name_edit.setText(m["name"])
        self.macro_content_edit.setPlainText(m["content"])


class MachineProfileDialog(QtWidgets.QDialog):
    def __init__(self, profiles, active_name="", parent=None):
        super().__init__(parent)
        self.profiles = normalize_machine_profiles(profiles)
        self.active_name = active_name or self.profiles[0]["name"]
        self.setWindowTitle(_("Machine Profiles"))
        self.setMinimumSize(720, 430)

        if parent is not None and hasattr(parent, "ui"):
            self.setStyleSheet(parent.ui.stylesheet())

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        main_h = QtWidgets.QHBoxLayout()
        main_h.setSpacing(10)
        lay.addLayout(main_h, 1)

        list_panel = QtWidgets.QGroupBox(_("Profiles"))
        list_lay = QtWidgets.QVBoxLayout(list_panel)
        self.profile_list = QtWidgets.QListWidget()
        self.profile_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        list_lay.addWidget(self.profile_list, 1)

        self.new_btn = FluidStyleButton(_("New"), "#5cb85c", "#449d44")
        self.delete_btn = FluidStyleButton(_("Delete"), "#d9534f", "#c9302c")
        list_btns = QtWidgets.QHBoxLayout()
        list_btns.addWidget(self.new_btn)
        list_btns.addWidget(self.delete_btn)
        list_lay.addLayout(list_btns)
        main_h.addWidget(list_panel, 1)

        editor_panel = QtWidgets.QGroupBox(_("Profile Settings"))
        form = QtWidgets.QFormLayout(editor_panel)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)

        self.name_edit = QtWidgets.QLineEdit()
        self.safe_z = self.double_spin(-100000.0, 100000.0, " mm")
        self.jog_feed = self.int_spin(1, 60000, " mm/min")
        self.probe_feed = self.int_spin(1, 60000, " mm/min")
        self.spindle_max = self.int_spin(0, 100000, " RPM")
        self.travel_x = self.double_spin(0.0, 100000.0, " mm")
        self.travel_y = self.double_spin(0.0, 100000.0, " mm")
        self.travel_z = self.double_spin(0.0, 100000.0, " mm")

        form.addRow(_("Name:"), self.name_edit)
        form.addRow(_("Safe Z:"), self.safe_z)
        form.addRow(_("Default jog feed:"), self.jog_feed)
        form.addRow(_("Probe feed:"), self.probe_feed)
        form.addRow(_("Max spindle:"), self.spindle_max)
        form.addRow(_("Travel X:"), self.travel_x)
        form.addRow(_("Travel Y:"), self.travel_y)
        form.addRow(_("Travel Z:"), self.travel_z)

        self.save_btn = FluidStyleButton(_("Save Profile"), "#337ab7", "#286090")
        form.addRow("", self.save_btn)
        main_h.addWidget(editor_panel, 2)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()
        close_btn = QtWidgets.QPushButton(_("Close"))
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        lay.addLayout(bottom)

        self.new_btn.clicked.connect(self.on_new)
        self.delete_btn.clicked.connect(self.on_delete)
        self.save_btn.clicked.connect(self.on_save)
        self.profile_list.itemSelectionChanged.connect(self.on_selection_changed)

        self.refresh_list()
        self.select_profile(self.active_name)

    @staticmethod
    def double_spin(minimum, maximum, suffix):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSuffix(suffix)
        return spin

    @staticmethod
    def int_spin(minimum, maximum, suffix):
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        return spin

    def refresh_list(self):
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self.profiles:
            self.profile_list.addItem(profile["name"])
        self.profile_list.blockSignals(False)

    def select_profile(self, name):
        for row in range(self.profile_list.count()):
            if self.profile_list.item(row).text() == name:
                self.profile_list.setCurrentRow(row)
                return
        if self.profile_list.count():
            self.profile_list.setCurrentRow(0)

    def selected_index(self):
        row = self.profile_list.currentRow()
        return row if 0 <= row < len(self.profiles) else -1

    def on_new(self):
        base = _("New Machine")
        names = {profile["name"] for profile in self.profiles}
        name = base
        suffix = 2
        while name in names:
            name = f"{base} {suffix}"
            suffix += 1
        self.profiles.append(normalize_machine_profile({"name": name}, fallback_name=name))
        self.active_name = name
        self.refresh_list()
        self.select_profile(name)

    def on_delete(self):
        idx = self.selected_index()
        if idx < 0:
            return
        if len(self.profiles) == 1:
            QtWidgets.QMessageBox.warning(self, _("Machine Profiles"), _("At least one machine profile is required."))
            return
        removed = self.profiles.pop(idx)
        if self.active_name == removed["name"]:
            self.active_name = self.profiles[0]["name"]
        self.refresh_list()
        self.select_profile(self.active_name)

    def on_save(self):
        idx = self.selected_index()
        if idx < 0:
            return

        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, _("Machine Profiles"), _("Profile name is required."))
            return

        for row, profile in enumerate(self.profiles):
            if row != idx and profile["name"] == name:
                QtWidgets.QMessageBox.warning(self, _("Machine Profiles"), _("Profile name must be unique."))
                return

        old_name = self.profiles[idx]["name"]
        self.profiles[idx] = normalize_machine_profile({
            "name": name,
            "safe_z": self.safe_z.value(),
            "jog_feed": self.jog_feed.value(),
            "probe_feed": self.probe_feed.value(),
            "spindle_max": self.spindle_max.value(),
            "travel_x": self.travel_x.value(),
            "travel_y": self.travel_y.value(),
            "travel_z": self.travel_z.value(),
        }, fallback_name=old_name)
        self.active_name = name
        self.refresh_list()
        self.select_profile(name)

    def on_selection_changed(self):
        idx = self.selected_index()
        if idx < 0:
            return
        profile = self.profiles[idx]
        self.active_name = profile["name"]
        self.name_edit.setText(profile["name"])
        self.safe_z.setValue(profile["safe_z"])
        self.jog_feed.setValue(profile["jog_feed"])
        self.probe_feed.setValue(profile["probe_feed"])
        self.spindle_max.setValue(profile["spindle_max"])
        self.travel_x.setValue(profile["travel_x"])
        self.travel_y.setValue(profile["travel_y"])
        self.travel_z.setValue(profile["travel_z"])
