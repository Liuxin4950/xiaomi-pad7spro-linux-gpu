#!/data/data/com.termux/files/usr/bin/bash
# Termux Widget: shared current GPU desktop entry, safe to reuse a live session.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$SCRIPT_DIR/mali-work/desktop-zink.sh" "$@"
