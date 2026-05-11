# ##########################################################
# FlatCAM PLUS: GitHub release auto-update helper          #
# ##########################################################

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser

import simplejson as json
from PyQt6 import QtCore, QtWidgets

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class UpdateDialog(QtWidgets.QDialog):
    def __init__(self, update_info, parent=None):
        super().__init__(parent=parent)
        self.update_info = update_info
        self.download_requested = False

        self.setWindowTitle(_("New Version Available"))
        self.setMinimumSize(560, 420)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QtWidgets.QLabel(
            _("FlatCAM Plus %s is available.") % update_info.get("version", "")
        )
        title.setWordWrap(True)
        font = title.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        current_version = update_info.get("current_version", "")
        release_name = update_info.get("name", "")
        detail = QtWidgets.QLabel(
            _("Installed version: %s\nRelease: %s") % (current_version, release_name)
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        changelog = QtWidgets.QPlainTextEdit()
        changelog.setReadOnly(True)
        changelog.setPlainText(update_info.get("body", "").strip() or _("No changelog information was provided."))
        layout.addWidget(changelog, 1)

        self.button_box = QtWidgets.QDialogButtonBox()
        self.later_btn = self.button_box.addButton(_("Later"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self.download_btn = self.button_box.addButton(
            _("Download Update"),
            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self.on_download_clicked)
        self.later_btn.clicked.connect(self.reject)
        layout.addWidget(self.button_box)

    def on_download_clicked(self):
        self.download_requested = True
        self.accept()


class AutoUpdater(QtCore.QObject):
    update_available = QtCore.pyqtSignal(dict)
    no_update_available = QtCore.pyqtSignal(bool)
    check_failed = QtCore.pyqtSignal(str, bool)
    download_progress = QtCore.pyqtSignal(int, str)
    download_finished = QtCore.pyqtSignal(str)
    download_failed = QtCore.pyqtSignal(str)

    RELEASES_API_URL = "https://api.github.com/repos/thebestgoodguy/FlatCAM-Plus/releases"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.progress_dialog = None

        self.update_available.connect(self.show_update_dialog)
        self.no_update_available.connect(self.on_no_update_available)
        self.check_failed.connect(self.on_check_failed)
        self.download_progress.connect(self.on_download_progress)
        self.download_finished.connect(self.on_download_finished)
        self.download_failed.connect(self.on_download_failed)

    @staticmethod
    def normalized_version(version):
        parts = re.findall(r"\d+", str(version or ""))
        if not parts:
            return (0,)
        return tuple(int(part) for part in parts[:4])

    @staticmethod
    def running_arch():
        if platform.architecture()[0].startswith("32"):
            return "x86"
        return "x64"

    @staticmethod
    def request_json(url):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "FlatCAMPlus-Updater"
            }
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def check_for_updates(self, silent=True):
        self.app.worker_task.emit({'fcn': self._check_for_updates_worker, 'params': [silent]})

    def _check_for_updates_worker(self, silent=True):
        try:
            releases = self.request_json(self.RELEASES_API_URL)
            if not isinstance(releases, list):
                if isinstance(releases, dict):
                    message = releases.get("message", _("Unexpected update server response."))
                else:
                    message = _("Unexpected update server response.")
                raise RuntimeError(message)

            release = self.select_latest_release(releases)
            if not release:
                self.no_update_available.emit(silent)
                return

            latest_version = self.release_version(release)
            current_version = str(getattr(self.app, "version", "0.0.0"))
            if self.normalized_version(latest_version) <= self.normalized_version(current_version):
                self.no_update_available.emit(silent)
                return

            asset = self.select_installer_asset(release.get("assets", []))
            update_info = {
                "name": release.get("name") or release.get("tag_name") or latest_version,
                "version": latest_version,
                "current_version": current_version,
                "body": release.get("body") or "",
                "html_url": release.get("html_url") or "",
                "asset_name": asset.get("name") if asset else "",
                "asset_url": asset.get("browser_download_url") if asset else "",
            }
            self.update_available.emit(update_info)
        except Exception as err:
            self.check_failed.emit(str(err), silent)

    def select_latest_release(self, releases):
        if not isinstance(releases, list):
            return None

        allow_prerelease = bool(getattr(self.app, "beta", False))
        for release in releases:
            if release.get("draft"):
                continue
            if release.get("prerelease") and allow_prerelease is not True:
                continue
            return release
        return None

    @staticmethod
    def release_version(release):
        tag = str(release.get("tag_name") or release.get("name") or "")
        return tag.lstrip("vV").strip()

    def select_installer_asset(self, assets):
        arch = self.running_arch()
        other_arch = "x86" if arch == "x64" else "x64"
        arch_patterns = {
            "x86": [
                r"(?<![a-z0-9])x86(?![_-]?64)(?![a-z0-9])",
                r"(?<![a-z0-9])x32(?![a-z0-9])",
                r"(?<![a-z0-9])win32(?![a-z0-9])",
                r"(?<![a-z0-9])32(?:bit|-bit)?(?![a-z0-9])"
            ],
            "x64": [
                r"(?<![a-z0-9])x64(?![a-z0-9])",
                r"(?<![a-z0-9])x86[_-]?64(?![a-z0-9])",
                r"(?<![a-z0-9])amd64(?![a-z0-9])",
                r"(?<![a-z0-9])64(?:bit|-bit)?(?![a-z0-9])"
            ]
        }
        own_arch_patterns = [re.compile(pattern) for pattern in arch_patterns.get(arch, [re.escape(arch)])]
        other_arch_patterns = [re.compile(pattern) for pattern in arch_patterns.get(other_arch, [re.escape(other_arch)])]
        best_asset = None
        best_score = -1

        for asset in assets or []:
            name = str(asset.get("name") or "").lower()
            if not name.endswith(".exe"):
                continue

            score = 0
            if any(pattern.search(name) for pattern in own_arch_patterns):
                score += 100
            if any(pattern.search(name) for pattern in other_arch_patterns):
                score -= 100
            if "setup" in name or "installer" in name:
                score += 20
            if "flatcamplus" in name or "flatcam-plus" in name:
                score += 10

            if score > best_score:
                best_score = score
                best_asset = asset

        return best_asset

    def show_update_dialog(self, update_info):
        if self.app.cmd_line_headless == 1:
            return

        dialog = UpdateDialog(update_info, parent=self.app.ui)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.download_requested:
            self.start_download(update_info)

    def start_download(self, update_info):
        asset_url = update_info.get("asset_url")
        if not asset_url:
            release_url = update_info.get("html_url")
            if release_url:
                webbrowser.open(release_url)
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("No Windows installer asset was found for this release."))
            return

        self.progress_dialog = QtWidgets.QProgressDialog(
            _("Downloading update..."),
            "",
            0,
            100,
            self.app.ui
        )
        self.progress_dialog.setWindowTitle(_("FlatCAM Plus Update"))
        self.progress_dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()

        self.app.worker_task.emit({'fcn': self._download_worker, 'params': [update_info]})

    def _download_worker(self, update_info):
        url = update_info.get("asset_url")
        asset_name = update_info.get("asset_name") or "FlatCAMPlus-Setup.exe"
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", asset_name)
        target_dir = tempfile.mkdtemp(prefix="FlatCAMPlusUpdate_")
        target_path = os.path.join(target_dir, safe_name)

        try:
            request = urllib.request.Request(url, headers={"User-Agent": "FlatCAMPlus-Updater"})
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                with open(target_path, "wb") as output:
                    while True:
                        chunk = response.read(1024 * 128)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total) if total else 0
                        self.download_progress.emit(min(percent, 100), safe_name)

            self.download_finished.emit(target_path)
        except Exception as err:
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except Exception:
                pass
            self.download_failed.emit(str(err))

    def on_download_progress(self, percent, filename):
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText(_("Downloading update: %s") % filename)
            if percent > 0:
                self.progress_dialog.setValue(percent)

    def on_download_finished(self, installer_path):
        if self.progress_dialog is not None:
            self.progress_dialog.setValue(100)
            self.progress_dialog.close()
            self.progress_dialog = None

        QtWidgets.QMessageBox.information(
            self.app.ui,
            _("FlatCAM Plus Update"),
            _("The update installer was downloaded. The installer will start now and FlatCAM Plus will close.")
        )
        self.launch_installer(installer_path)

    def launch_installer(self, installer_path):
        try:
            if sys.platform == "win32":
                os.startfile(installer_path)  # noqa
            else:
                subprocess.Popen([installer_path])
        except Exception as err:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not start update installer"), str(err)))
            return

        QtCore.QTimer.singleShot(1000, self.app.app_quit.emit)

    def on_download_failed(self, message):
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog = None
        QtWidgets.QMessageBox.warning(
            self.app.ui,
            _("FlatCAM Plus Update"),
            _("Update download failed:\n%s") % message
        )

    def on_no_update_available(self, silent):
        if silent is not True:
            self.app.inform.emit('[success] %s' % _("The application is up to date!"))

    def on_check_failed(self, message, silent):
        self.app.log.warning("Auto update check failed: %s" % message)
        if silent is not True:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Failed checking for latest version. Could not connect."))
