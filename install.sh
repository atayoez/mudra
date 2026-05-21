#!/bin/bash
# Create the Python venv and fetch the hand-pose model. No root needed.
# Run after ./setup.sh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d .venv ]; then
    echo "== Creating venv (with --system-site-packages: sees system "
    echo "   opencv/numpy/evdev/PyQt6) =="
    python3.13 -m venv --system-site-packages .venv
fi

./.venv/bin/python -m pip install --upgrade pip
echo "== Installing PyTorch + Ultralytics =="
# On a CUDA platform `pip install torch` pulls the GPU build automatically;
# on others it installs the CPU build. mudra uses the GPU if one is available.
./.venv/bin/pip install torch torchvision ultralytics

MODEL="$DIR/hand_yolo11n_pose.pt"
if [ ! -e "$MODEL" ]; then
    echo "== Downloading hand-pose model (~6 MB) =="
    curl -fL --retry 3 -o "$MODEL" \
        "https://raw.githubusercontent.com/chrismuntean/YOLO11n-pose-hands/main/runs/pose/train/weights/best.pt"
fi

echo "== Done. Launch with ./run.sh =="
