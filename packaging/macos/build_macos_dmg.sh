#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SKIP_TRANSLATIONS=0
SKIP_APP=0
SKIP_DMG=0
SKIP_SIGN=0

usage() {
    cat <<'EOF'
Usage: packaging/macos/build_macos_dmg.sh [options]

Options:
  --skip-translations   Do not compile locale/*.po files into .mo files.
  --skip-app            Reuse an existing dist/macos/FlatCAM-Plus.app.
  --no-dmg              Build only the .app bundle.
  --no-sign             Do not codesign the .app bundle.
  -h, --help            Show this help.

Environment:
  PYTHON_BIN            Python executable to use. Default: python3
  APPLE_DEVELOPER_ID    Optional Developer ID signing identity.
                        When omitted, the app is ad-hoc signed locally.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-translations)
            SKIP_TRANSLATIONS=1
            shift
            ;;
        --skip-app)
            SKIP_APP=1
            shift
            ;;
        --no-dmg)
            SKIP_DMG=1
            shift
            ;;
        --no-sign)
            SKIP_SIGN=1
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

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "[ERROR] macOS packages must be built on macOS."
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
APP_BUNDLE="$ROOT_DIR/dist/macos/$APP_NAME.app"
DMG_PATH="$ROOT_DIR/dist/installer/FlatCAMPlus-${VERSION}-macOS-$(uname -m).dmg"

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
        if command -v brew >/dev/null 2>&1; then
            GETTEXT_PREFIX="$(brew --prefix gettext 2>/dev/null || true)"
            if [[ -n "$GETTEXT_PREFIX" && -x "$GETTEXT_PREFIX/bin/msgfmt" ]]; then
                export PATH="$GETTEXT_PREFIX/bin:$PATH"
            fi
        fi
    fi

    if ! command -v msgfmt >/dev/null 2>&1; then
        echo "[WARN] msgfmt was not found; existing .mo files will be used."
        echo "       Install gettext with: brew install gettext"
        return
    fi

    echo "[INFO] Compiling translations..."
    find locale -name "strings.po" -print0 |
        while IFS= read -r -d '' po_file; do
            msgfmt "$po_file" -o "${po_file%.po}.mo"
        done
}

create_macos_icon() {
    local icon_dir="$ROOT_DIR/build/icons"
    local iconset="$icon_dir/FlatCAMPlus.iconset"
    local icns="$icon_dir/FlatCAMPlus.icns"
    local source_png="$ROOT_DIR/assets/resources/app256.png"

    if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
        return 0
    fi
    if [[ ! -f "$source_png" ]]; then
        return 0
    fi

    rm -rf "$iconset"
    mkdir -p "$iconset"

    sips -z 16 16 "$source_png" --out "$iconset/icon_16x16.png" >/dev/null
    sips -z 32 32 "$source_png" --out "$iconset/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$source_png" --out "$iconset/icon_32x32.png" >/dev/null
    sips -z 64 64 "$source_png" --out "$iconset/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$source_png" --out "$iconset/icon_128x128.png" >/dev/null
    sips -z 256 256 "$source_png" --out "$iconset/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$source_png" --out "$iconset/icon_256x256.png" >/dev/null
    sips -z 512 512 "$source_png" --out "$iconset/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$source_png" --out "$iconset/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "$source_png" --out "$iconset/icon_512x512@2x.png" >/dev/null

    if iconutil -c icns "$iconset" -o "$icns" >/dev/null 2>&1; then
        printf '%s\n' "$icns"
    fi
}

build_app() {
    ensure_pyinstaller
    check_python_modules
    compile_translations

    mkdir -p "$ROOT_DIR/dist/macos" "$ROOT_DIR/build/pyinstaller/macos"

    local icon_path
    icon_path="$(create_macos_icon || true)"

    local args=(
        -m PyInstaller flatcam.py
        --name "$APP_NAME"
        --windowed
        --clean
        --noconfirm
        --distpath "$ROOT_DIR/dist/macos"
        --workpath "$ROOT_DIR/build/pyinstaller/macos"
        --specpath "$ROOT_DIR/build/pyinstaller/macos"
        --osx-bundle-identifier "com.flatcamplus.app"
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

    if [[ -n "$icon_path" ]]; then
        args+=(--icon "$icon_path")
    fi

    echo "[INFO] Building macOS .app bundle..."
    "$PYTHON_BIN" "${args[@]}"

    if [[ ! -d "$APP_BUNDLE" ]]; then
        echo "[ERROR] Expected app bundle was not created: $APP_BUNDLE"
        exit 1
    fi
}

sign_app() {
    if [[ "$SKIP_SIGN" -eq 1 ]]; then
        echo "[INFO] Skipping codesign."
        return
    fi
    if ! command -v codesign >/dev/null 2>&1; then
        echo "[WARN] codesign was not found; leaving app unsigned."
        return
    fi

    local identity="${APPLE_DEVELOPER_ID:--}"
    local sign_args=(--force --deep)
    if [[ "$identity" != "-" ]]; then
        sign_args+=(--options runtime)
    fi
    sign_args+=(--sign "$identity" "$APP_BUNDLE")

    echo "[INFO] Signing app with identity: $identity"
    codesign "${sign_args[@]}"
}

create_dmg() {
    if [[ "$SKIP_DMG" -eq 1 ]]; then
        echo "[INFO] Skipping DMG creation."
        return
    fi
    if ! command -v hdiutil >/dev/null 2>&1; then
        echo "[ERROR] hdiutil was not found; cannot create DMG."
        exit 1
    fi

    mkdir -p "$ROOT_DIR/dist/installer"
    rm -f "$DMG_PATH"

    echo "[INFO] Creating DMG: $DMG_PATH"
    hdiutil create \
        -volname "FlatCAM Plus" \
        -srcfolder "$APP_BUNDLE" \
        -ov \
        -format UDZO \
        "$DMG_PATH"
}

if [[ "$SKIP_APP" -eq 0 ]]; then
    build_app
elif [[ ! -d "$APP_BUNDLE" ]]; then
    echo "[ERROR] --skip-app was used but app bundle does not exist: $APP_BUNDLE"
    exit 1
fi

sign_app
create_dmg

echo
echo "[OK] macOS package is ready."
echo "     App: $APP_BUNDLE"
if [[ "$SKIP_DMG" -eq 0 ]]; then
    echo "     DMG: $DMG_PATH"
fi
