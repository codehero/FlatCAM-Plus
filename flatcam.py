
import sys
import os
import traceback
import json
import gettext
import builtins
from datetime import datetime

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import QSettings, QTimer, QStandardPaths
import appTranslation as fcTranslate
from appMain import App
from appGUI import VisPyPatches
from appVersion import APP_NAME, APP_VERSION

from appGUI.GUIElements import FCMessageBox

from multiprocessing import freeze_support

MIN_VERSION_MAJOR = 3
MIN_VERSION_MINOR = 6

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    builtins._ = gettext.gettext
_ = builtins._


class StartupProjectLauncher(QtWidgets.QDialog):
    def __init__(self, data_path, parent=None):
        super().__init__(parent)

        self.data_path = data_path
        self.selection = None
        self.base_path = os.path.dirname(os.path.realpath(__file__))
        self.resource_location = os.path.join(self.base_path, "assets", "resources")

        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Dialog
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(1040, 586)

        root = QtWidgets.QFrame(self)
        root.setObjectName("launcher_root")
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(36, 28, 36, 36)
        root_layout.setSpacing(18)

        top_row = QtWidgets.QHBoxLayout()
        top_row.addStretch(1)
        close_btn = QtWidgets.QToolButton(root)
        close_btn.setObjectName("launcher_close")
        close_btn.setText("X")
        close_btn.clicked.connect(self.reject)
        top_row.addWidget(close_btn)
        root_layout.addLayout(top_row)

        content_row = QtWidgets.QHBoxLayout()
        content_row.setContentsMargins(228, 0, 228, 0)
        content_row.setSpacing(0)

        panel = QtWidgets.QFrame(root)
        panel.setObjectName("launcher_panel")
        panel.setFixedWidth(512)
        panel.setMaximumHeight(270)
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(14)

        self.new_project_btn = QtWidgets.QPushButton(_("Create New Project"), panel)
        self.new_project_btn.setObjectName("launcher_primary")
        self.new_project_btn.setIcon(QtGui.QIcon(os.path.join(self.resource_location, "new_file32.png")))
        self.new_project_btn.setIconSize(QtCore.QSize(26, 26))
        self.new_project_btn.clicked.connect(self.on_new_project)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(12)
        button_row.addWidget(self.new_project_btn, 1)

        self.open_project_btn = QtWidgets.QPushButton(_("Open Project"), panel)
        self.open_project_btn.setObjectName("launcher_secondary")
        self.open_project_btn.setIcon(QtGui.QIcon(os.path.join(self.resource_location, "folder32.png")))
        self.open_project_btn.setIconSize(QtCore.QSize(26, 26))
        self.open_project_btn.clicked.connect(self.on_open_project)
        button_row.addWidget(self.open_project_btn, 1)
        panel_layout.addLayout(button_row)

        recent_label = QtWidgets.QLabel(_("Recent Projects"), panel)
        recent_label.setObjectName("launcher_recent_title")
        panel_layout.addWidget(recent_label)

        recent_projects = self.load_recent_projects()
        if recent_projects:
            for project_path in recent_projects[:3]:
                recent_btn = QtWidgets.QPushButton(os.path.basename(project_path), panel)
                recent_btn.setObjectName("launcher_recent_item")
                recent_btn.setToolTip(project_path)
                recent_btn.clicked.connect(lambda checked=False, path=project_path: self.accept_open_project(path))
                panel_layout.addWidget(recent_btn)
        else:
            empty_recent = QtWidgets.QLabel(_("No recent projects yet."), panel)
            empty_recent.setObjectName("launcher_empty_recent")
            panel_layout.addWidget(empty_recent)

        panel_layout.addStretch(1)

        content_row.addWidget(panel)
        root_layout.addLayout(content_row, 1)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(root)

        self.apply_style()
        self.center_on_screen()

    def apply_style(self):
        splash_path = os.path.join(self.resource_location, "splash.png").replace("\\", "/")
        self.setStyleSheet(f"""
            QFrame#launcher_root {{
                background-color: #0f172a;
                background-image: url("{splash_path}");
                background-position: center;
                background-repeat: no-repeat;
                border: 1px solid rgba(226, 232, 240, 90);
                border-radius: 20px;
            }}
            QFrame#launcher_panel {{
                background: rgba(8, 12, 20, 190);
                border: 1px solid rgba(255, 255, 255, 70);
                border-radius: 18px;
            }}
            QLabel#launcher_title {{
                color: #0f172a;
                font-size: 34px;
                font-weight: 800;
            }}
            QLabel#launcher_subtitle {{
                color: #475569;
                font-size: 13px;
            }}
            QLabel#launcher_recent_title {{
                color: #f8fafc;
                font-size: 12px;
                font-weight: 700;
                padding-top: 8px;
            }}
            QLabel#launcher_empty_recent,
            QLabel#launcher_version {{
                color: #cbd5e1;
                font-size: 12px;
            }}
            QPushButton#launcher_primary,
            QPushButton#launcher_secondary {{
                min-height: 58px;
                border-radius: 13px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: 700;
                text-align: left;
            }}
            QPushButton#launcher_primary {{
                color: #0f172a;
                background: rgba(255, 255, 255, 230);
                border: 1px solid rgba(255, 255, 255, 220);
            }}
            QPushButton#launcher_primary:hover {{
                background: #ffffff;
                border-color: #ffffff;
            }}
            QPushButton#launcher_secondary {{
                color: #0f172a;
                background: rgba(255, 255, 255, 220);
                border: 1px solid rgba(255, 255, 255, 205);
            }}
            QPushButton#launcher_secondary:hover,
            QPushButton#launcher_recent_item:hover {{
                background: #ffffff;
                border-color: #ffffff;
            }}
            QPushButton#launcher_recent_item {{
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 12px;
                color: #1e293b;
                background: rgba(255, 255, 255, 190);
                border: 1px solid rgba(203, 213, 225, 210);
                text-align: left;
                font-size: 12px;
                font-weight: 600;
            }}
            QToolButton#launcher_close {{
                color: #ffffff;
                background: rgba(15, 23, 42, 150);
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 12px;
                min-width: 32px;
                min-height: 32px;
                font-weight: 700;
            }}
            QToolButton#launcher_close:hover {{
                background: rgba(220, 38, 38, 190);
            }}
        """)

    def center_on_screen(self):
        screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def default_project_folder(self):
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        if not folder:
            folder = os.path.expanduser("~")
        return folder

    def load_recent_projects(self):
        recent_path = os.path.join(self.data_path, "recent_projects.json")
        try:
            with open(recent_path, "r", encoding="utf-8") as recent_file:
                records = json.load(recent_file)
        except (OSError, json.JSONDecodeError):
            return []

        projects = []
        for record in records:
            if not isinstance(record, dict):
                continue
            if str(record.get("kind", "")).lower() != "project":
                continue
            filename = record.get("filename")
            if filename and os.path.exists(filename):
                projects.append(filename)
        return projects

    def on_new_project(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(_("Create New Project"))
        dialog.setModal(True)
        dialog.setMinimumWidth(460)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        name_entry = QtWidgets.QLineEdit(_("New Project"), dialog)

        location_row = QtWidgets.QHBoxLayout()
        location_row.setContentsMargins(0, 0, 0, 0)
        location_row.setSpacing(8)

        location_entry = QtWidgets.QLineEdit(self.default_project_folder(), dialog)
        browse_btn = QtWidgets.QPushButton(_("Choose"), dialog)
        browse_btn.setMinimumWidth(72)

        def browse_location():
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                dialog,
                _("Choose Save Location"),
                location_entry.text().strip() or self.default_project_folder()
            )
            if folder:
                location_entry.setText(folder)

        browse_btn.clicked.connect(browse_location)
        location_row.addWidget(location_entry, 1)
        location_row.addWidget(browse_btn)

        form_layout.addRow(_("Project Name"), name_entry)
        form_layout.addRow(_("Save Location"), location_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(_("Create"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        project_name = name_entry.text().strip()
        project_folder = location_entry.text().strip()
        if not project_name or not project_folder:
            QtWidgets.QMessageBox.warning(
                self,
                _("Missing Information"),
                _("Project name and save location are required.")
            )
            return

        filename = project_name
        if not filename.lower().endswith(".flatprj"):
            filename += ".FlatPrj"

        self.selection = {
            "action": "new",
            "project_name": project_name,
            "filename": os.path.join(project_folder, filename)
        }
        self.accept()

    def on_open_project(self):
        filename, filter_ext = QtWidgets.QFileDialog.getOpenFileName(
            self,
            _("Open Project"),
            self.default_project_folder(),
            "FlatCAM Project (*.FlatPrj);;All Files (*.*)"
        )
        if filename:
            self.accept_open_project(filename)

    def accept_open_project(self, filename):
        self.selection = {
            "action": "open",
            "filename": filename
        }
        self.accept()


def debug_trace():
    """
    Set a tracepoint in the Python debugger that works with Qt
    :return: None
    """
    from PyQt6.QtCore import pyqtRemoveInputHook
    # from pdb import set_trace
    pyqtRemoveInputHook()
    # set_trace()


if __name__ == '__main__':
    # All X11 calling should be thread safe otherwise we have strange issues
    # QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_X11InitThreads)
    # NOTE: Never talk to the GUI from threads! This is why I commented the above.
    freeze_support()

    portable = False
    # Folder for user settings.
    if sys.platform == 'win32':
        # #######################################################################################################
        # ####### CONFIG FILE WITH PARAMETERS REGARDING PORTABILITY #############################################
        # #######################################################################################################
        config_file = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\config\\configuration.txt'
        try:
            with open(config_file, 'r'):
                pass
        except FileNotFoundError:
            config_file = os.path.dirname(os.path.realpath(__file__)) + '\\config\\configuration.txt'

        with open(config_file, 'r') as f:
            for line in f:
                param = str(line).replace('\n', '').rpartition('=')

                if param[0] == 'portable':
                    try:
                        portable = eval(param[2])
                    except NameError:
                        portable = False

        if portable is False:
            # data_path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, None, 0) + '\\FlatCAM'
            data_path = os.path.join(os.getenv('appdata'), 'FlatCAM')
        else:
            data_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\config'
    else:
        data_path = os.path.expanduser('~') + '/.FlatCAM'

    if not os.path.exists(data_path):
        os.makedirs(data_path)

    log_file_path = os.path.join(data_path, "log.txt")

    major_v = sys.version_info.major
    minor_v = sys.version_info.minor

    v_msg = "FlatCAM Plus uses PYTHON 3 or later. The version minimum is %s.%s\n"\
            "Your Python version is: %s.%s" % (MIN_VERSION_MAJOR, MIN_VERSION_MINOR, str(major_v), str(minor_v))

    # Supported Python version is >= 3.6
    if major_v < MIN_VERSION_MAJOR or (major_v >= MIN_VERSION_MAJOR and minor_v < MIN_VERSION_MINOR):
        print(v_msg)
        msg = '%s\n' % str(datetime.today())
        msg += v_msg

        try:
            with open(log_file_path) as f:
                log_file = f.read()
            log_file += '\n' + msg

            with open(log_file_path, 'w') as f:
                f.write(log_file)
        except IOError:
            with open(log_file_path, 'w') as f:
                f.write(msg)

        # if minor_v >= 8:
        #     os._exit(0)
        # else:
        #     sys.exit(0)
        sys.exit(0)

    debug_trace()
    VisPyPatches.apply_patches()

    def excepthook(exc_type, exc_value, exc_tb):
        msg = '%s\n' % str(datetime.today())
        if exc_type != KeyboardInterrupt:
            msg += "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

            try:
                with open(log_file_path) as f:
                    log_file = f.read()
                log_file += '\n' + msg

                with open(log_file_path, 'w') as f:
                    f.write(log_file)
            except IOError:
                with open(log_file_path, 'w') as f:
                    f.write(msg)

            # show the message
            try:
                msgbox = FCMessageBox()
                displayed_msg = "The application encountered a critical error and it will close.\n"\
                                "Please report this error to the developers."
                title = "Critical Error"
                msgbox.setWindowTitle(title)  # taskbar still shows it
                ic = QtGui.QIcon()
                ic.addPixmap(QtGui.QPixmap("assets/resources/warning.png"), QtGui.QIcon.Mode.Normal)
                msgbox.setWindowIcon(ic)
                msgbox.setText('<b>%s</b>' % displayed_msg)
                msgbox.setDetailedText(msg)
                msgbox.setIcon(QtWidgets.QMessageBox.Icon.Critical)

                bt_yes = msgbox.addButton("Quit", QtWidgets.QMessageBox.ButtonRole.YesRole)
                bt_ret = msgbox.addButton("Return", QtWidgets.QMessageBox.ButtonRole.NoRole)

                msgbox.setDefaultButton(bt_yes)
                # msgbox.setTextFormat(Qt.TextFormat.RichText)
                msgbox.exec()

                response = msgbox.clickedButton()
                if response == bt_ret:
                    pass
            except Exception:
                QtWidgets.QApplication.quit()
        else:
            QtWidgets.QApplication.quit()
        # or QtWidgets.QApplication.exit(0)

    sys.excepthook = excepthook

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("%s %s" % (APP_NAME, APP_VERSION))

    # apply style
    settings = QSettings("Open Source", "FlatCAM_Plus")
    if settings.contains("style"):
        style_index = settings.value('style', type=str)
        try:
            idx = int(style_index)
        except Exception:
            idx = 0
        style = QtWidgets.QStyleFactory.keys()[idx]
        app.setStyle(style)
    else:
        app.setStyle('windowsvista')

    if settings.contains("font_size"):
        font_size = int(settings.value("font_size", type=str))      # noqa
        font = QtGui.QFont()
        font.setPointSize(font_size)
        app.setFont(font)

    # Start directly in the main window. The project create/open actions are now
    # shown inside the workspace start screen instead of blocking startup.
    fc = App(qapp=app, startup_project_request=None)

    # interrupt the Qt loop such that Python events have a chance to be responsive
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    try:
        sys.exit(app.exec())
    except SystemError:
        pass
    # app.exec()
