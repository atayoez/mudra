#!/bin/bash
# Launch mudra. Uses `sg input` so 'input' group membership applies immediately
# (no relogin needed) for /dev/uinput access.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPY="$DIR/.venv/bin/python"

[ -x "$VPY" ] || { echo "No venv found. Run ./install.sh first."; exit 1; }
[ -e "$DIR/hand_yolo11n_pose.pt" ] || { echo "No model. Run ./install.sh."; exit 1; }

if id -nG | grep -qw input; then
    exec "$VPY" "$DIR/mudra.py" "$@"
else
    exec sg input -c "'$VPY' '$DIR/mudra.py' $*"
fi
