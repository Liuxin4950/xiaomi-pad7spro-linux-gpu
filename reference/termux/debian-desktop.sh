#!/data/data/com.termux/files/usr/bin/bash
# All normal desktop entries use the current GPU release.
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "$SCRIPT_DIR/mali-work/desktop-zink.sh" "$@"
