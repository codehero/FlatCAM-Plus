#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SKIP_TRANSLATIONS=0
SKIP_BUILD=0
SKIP_ARCHIVE=0

usage() {
    cat <<'EOF'
Usage: packaging/linux/build_linux_portable.sh [options]

Options:
  --skip-translations   Do not compile locale/*.po files into .mo files.
  --skip-build          Reuse an existing dist/linux/FlatCAM-Plus folder.
  --no-archive          Build only the portable folder distribution.
  -h, --help            Show this help.

Environment:
  PYTHON_BIN            Python executable to use. Default: python3
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-translations)
            SKIP_TRANSLATIONS=1
            shift
            ;;
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --no-archive)
            SKIP_ARCHIVE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown option: $1"
            usage
            exit 2
            ;;
    esac
done

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[ERROR] Linux packages must be built on Linux."
    exit 1
fi

resolve_python() {
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        command -v "$PYTHON_BIN"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    if command -v python >/dev/null 2>&1; then
        command -v python
        return 0
    fi
    return 1
}

PYTHON_BIN="$(resolve_python)" || {
    echo "[ERROR] Python was not found. Install Python 3.11+ or set PYTHON_BIN."
    exit 1
}

cd "$ROOT_DIR"

VERSION="$("$PYTHON_BIN" - <<'PY'
import re
from pathlib import Path
text = Path("appVersion.py").read_text(encoding="utf-8")
match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
print(match.group(1) if match else "0.0.0")
PY
)"

APP_NAME="FlatCAM-Plus"
DIST_ROOT="$ROOT_DIR/dist/linux"
APP_DIR="$DIST_ROOT/$APP_NAME"
ARCHIVE_PATH="$ROOT_DIR/dist/installer/FlatCAMPlus-${VERSION}-linux-$(uname -m).tar.gz"

echo "[INFO] Root: $ROOT_DIR"
echo "[INFO] Python: $PYTHON_BIN"
echo "[INFO] Version: $VERSION"

ensure_pyinstaller() {
    if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
        echo "[ERROR] PyInstaller is missing in this Python environment."
        echo "        Install it with: $PYTHON_BIN -m pip install pyinstaller"
        exit 1
    fi
}

check_python_modules() {
    "$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

modules = [
    "PyQt6",
    "vispy",
    "shapely",
    "rasterio",
    "OpenGL",
    "matplotlib",
    "ortools",
]

missing = [name for name in modules if importlib.util.find_spec(name) is None]
if missing:
    print("[ERROR] Missing Python packages: " + ", ".join(missing))
    print("        Install project dependencies in the active environment first.")
    print("        Example: python -m pip install -r requirements.txt")
    sys.exit(1)
PY
}

compile_translations() {
    if [[ "$SKIP_TRANSLATIONS" -eq 1 ]]; then
        echo "[INFO] Skipping translation compilation."
        return
    fi

    if ! command -v msgfmt >/dev/null 2>&1; then
        echo "[WARN] msgfmt was not found; existing .mo files will be used."
        echo "       On Ubuntu/Debian install it with: sudo apt install gettext"
        return
    fi

    echo "[INFO] Compiling translations..."
    find locale -name "strings.po" -print0 |
        while IFS= read -r -d '' po_file; do
            msgfmt "$po_file" -o "${po_file%.po}.mo"
        done
}

write_desktop_launcher() {
    local launcher_file="$APP_DIR/run-flatcam-plus.sh"
    local desktop_file="$APP_DIR/FlatCAM-Plus.desktop"

    cat > "$launcher_file" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/FlatCAM-Plus" "$@"
EOF
    chmod +x "$launcher_file" 2>/dev/null || true

    cat > "$desktop_file" <<'EOF'
[Desktop Entry]
Name=FlatCAM Plus
Exec=sh -c "cd \"$(dirname \"$1\")\" && ./run-flatcam-plus.sh" sh %k
Type=Application
StartupNotify=true
Icon=./assets/resources/app256.png
Comment=PCB CAM and CNC workflow
Categories=Development;Engineering;
EOF
    chmod +x "$desktop_file" 2>/dev/null || true
}

build_portable() {
    ensure_pyinstaller
    check_python_modules
    compile_translations

    mkdir -p "$DIST_ROOT" "$ROOT_DIR/build/pyinstaller/linux"

    local args=(
        -m PyInstaller flatcam.py
        --name "$APP_NAME"
        --windowed
        --clean
        --noconfirm
        --distpath "$DIST_ROOT"
        --workpath "$ROOT_DIR/build/pyinstaller/linux"
        --specpath "$ROOT_DIR/build/pyinstaller/linux"
        --icon "$ROOT_DIR/assets/resources/app256.png"
        --add-data "assets:assets"
        --add-data "config:config"
        --add-data "locale:locale"
        --add-data "preprocessors:preprocessors"
        --add-data "libs:libs"
        --collect-submodules appCommon
        --collect-submodules appEditors
        --collect-submodules appGUI
        --collect-submodules appHandlers
        --collect-submodules appObjects
        --collect-submodules appParsers
        --collect-submodules appPlugins
        --collect-submodules tclCommands
        --collect-all PyQt6
        --collect-all vispy
        --collect-all shapely
        --collect-all rasterio
        --collect-all OpenGL
        --collect-all matplotlib
        --collect-all ortools
        --exclude-module PyQt5
        --exclude-module PySide2
        --exclude-module PySide6
        --exclude-module matplotlib.tests
        --exclude-module vispy.testing
        --exclude-module OpenGL.Tk
    )

    echo "[INFO] Building Linux portable folder..."
    "$PYTHON_BIN" "${args[@]}"

    if [[ ! -d "$APP_DIR" ]]; then
        echo "[ERROR] Expected portable folder was not created: $APP_DIR"
        exit 1
    fi

    write_desktop_launcher
}

create_archive() {
    if [[ "$SKIP_ARCHIVE" -eq 1 ]]; then
        echo "[INFO] Skipping archive creation."
        return
    fi
    if ! command -v tar >/dev/null 2>&1; then
        echo "[ERROR] tar was not found; cannot create portable archive."
        exit 1
    fi

    mkdir -p "$ROOT_DIR/dist/installer"
    rm -f "$ARCHIVE_PATH"

    echo "[INFO] Creating archive: $ARCHIVE_PATH"
    tar -C "$DIST_ROOT" -czf "$ARCHIVE_PATH" "$APP_NAME"
}

if [[ "$SKIP_BUILD" -eq 0 ]]; then
    build_portable
elif [[ ! -d "$APP_DIR" ]]; then
    echo "[ERROR] --skip-build was used but portable folder does not exist: $APP_DIR"
    exit 1
fi

create_archive

echo
echo "[OK] Linux portable package is ready."
echo "     Folder: $APP_DIR"
if [[ "$SKIP_ARCHIVE" -eq 0 ]]; then
    echo "     Archive: $ARCHIVE_PATH"
fi
