#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/packaging/linux/build_linux_portable.sh"

echo
echo "========================================================="
echo " FlatCAM Plus | Linux Portable Builder"
echo "========================================================="
echo

if [[ ! -f "$BUILD_SCRIPT" ]]; then
    echo "[ERROR] Build script not found: $BUILD_SCRIPT"
    exit 1
fi

chmod +x "$BUILD_SCRIPT" 2>/dev/null || true
exec "$BUILD_SCRIPT" "$@"
