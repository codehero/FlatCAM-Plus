#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/packaging/macos/build_macos_dmg.sh"

echo
echo "========================================================="
echo " FlatCAM Plus | macOS DMG Builder"
echo "========================================================="
echo

if [[ ! -f "$BUILD_SCRIPT" ]]; then
    echo "[ERROR] Build script not found: $BUILD_SCRIPT"
    read -r -p "Press Enter to close..." _ || true
    exit 1
fi

chmod +x "$BUILD_SCRIPT" 2>/dev/null || true

set +e
"$BUILD_SCRIPT" "$@"
EXIT_CODE=$?
set -e

echo
if [[ "$EXIT_CODE" -eq 0 ]]; then
    echo "[OK] macOS build finished."
else
    echo "[ERROR] macOS build failed with exit code $EXIT_CODE."
fi

if [[ -t 0 ]]; then
    read -r -p "Press Enter to close..." _ || true
fi

exit "$EXIT_CODE"
