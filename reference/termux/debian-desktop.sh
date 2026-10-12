#!/data/data/com.termux/files/usr/bin/bash
# All normal desktop entries use the current GPU release.
set -Eeuo pipefail
exec /data/data/com.termux/files/usr/bin/bash /data/data/com.termux/files/home/mali-work/desktop-zink.sh "$@"
