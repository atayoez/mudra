#!/bin/bash
# Launch mudra. Uses `sg input` so 'input' group membership applies immediately
# (no relogin needed) for /dev/uinput access.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in palm_detection_mediapipe_2023feb.onnx \
         handpose_estimation_mediapipe_2023feb.onnx; do
    [ -e "$DIR/$f" ] || { echo "Missing model $f. Run ./setup.sh first."; exit 1; }
done

if id -nG | grep -qw input; then
    exec python3 "$DIR/mudra.py" "$@"
else
    exec sg input -c "python3 '$DIR/mudra.py' $*"
fi
