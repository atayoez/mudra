#!/bin/bash
# Launch mudra through the pinned Electron helper.  Electron owns global
# shortcuts through the Wayland GlobalShortcuts portal; Python never reads
# physical keyboard event devices.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in palm_detection_mediapipe_2023feb.onnx \
         handpose_estimation_mediapipe_2023feb.onnx; do
    [ -e "$DIR/$f" ] || { echo "Missing model $f. Run ./setup.sh first."; exit 1; }
done

ELECTRON="$DIR/node_modules/.bin/electron"
[ -x "$ELECTRON" ] || {
    echo "Pinned Electron runtime is missing. Run ./setup.sh first."
    exit 1
}

# Pass Python arguments as JSON in the environment so no user-controlled
# argument is interpolated into a shell command.
export MUDRA_PYTHON_ARGS_JSON
MUDRA_PYTHON_ARGS_JSON="$(
    python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "$@"
)"

exec "$ELECTRON" "$DIR"
