#!/bin/bash
# One-shot setup for mudra. Run as your regular user:
#     ./setup.sh
# It elevates itself (pkexec/sudo) for the system phase — packages +
# /dev/uinput access — then creates the Python venv and fetches the
# hand-pose model as your user.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# System phase (root). Invoked automatically by the user phase below.
#
# Supports zypper (openSUSE), apt (Debian/Ubuntu), dnf (Fedora) and
# pacman (Arch). On anything else, install the equivalents of: python3 + pip
# + venv, OpenCV python bindings, NumPy, python-evdev, PyQt6, the Qt6 Wayland
# platform plugin — the /dev/uinput setup below runs regardless.
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--system" ]; then
    [ "$(id -u)" -eq 0 ] || { echo "--system must run as root"; exit 1; }

    TARGET_USER="${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}"
    TARGET_USER="${TARGET_USER:-${SUDO_USER:-$(id -nu)}}"

    echo "== Installing system packages =="
    if command -v zypper >/dev/null; then
        zypper --non-interactive install --no-recommends \
            python3 python3-pip python3-opencv python3-numpy \
            python3-evdev python3-PyQt6 qt6-wayland
    elif command -v apt-get >/dev/null; then
        apt-get update
        apt-get install -y --no-install-recommends \
            python3 python3-pip python3-venv python3-opencv python3-numpy \
            python3-evdev python3-pyqt6 qt6-wayland
    elif command -v dnf >/dev/null; then
        dnf install -y \
            python3 python3-pip python3-opencv python3-numpy \
            python3-evdev python3-pyqt6 qt6-qtwayland
    elif command -v pacman >/dev/null; then
        pacman -S --needed --noconfirm \
            python python-pip python-opencv python-numpy \
            python-evdev python-pyqt6 qt6-wayland
    else
        echo "!! No supported package manager found (zypper/apt/dnf/pacman)."
        echo "   Install manually: python3 + pip + venv, OpenCV python bindings,"
        echo "   NumPy, python-evdev, PyQt6, the Qt6 Wayland platform plugin."
        echo "   Continuing with /dev/uinput setup..."
    fi

    echo "== Enabling /dev/uinput for the 'input' group =="
    modprobe uinput || true
    echo uinput > /etc/modules-load.d/uinput.conf
    cat > /etc/udev/rules.d/99-uinput.rules <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
    udevadm control --reload-rules || true
    udevadm trigger /dev/uinput 2>/dev/null || udevadm trigger || true
    getent group input >/dev/null || groupadd input
    usermod -aG input "$TARGET_USER"
    chgrp input /dev/uinput 2>/dev/null || true
    chmod 660 /dev/uinput 2>/dev/null || true

    echo "== System setup done. User '$TARGET_USER' is in group 'input'. =="
    exit 0
fi

# ---------------------------------------------------------------------------
# User phase: elevate for the system phase, then venv + model. No root here.
# ---------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    echo "Run ./setup.sh as your regular user; it elevates itself for the"
    echo "system phase."
    exit 1
fi

echo "== System setup (asks for your password) =="
if command -v pkexec >/dev/null; then
    pkexec "$DIR/setup.sh" --system
else
    sudo "$DIR/setup.sh" --system
fi

cd "$DIR"
# Override with e.g. PYTHON=python3.13 ./setup.sh
PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
    echo "== Creating venv (with --system-site-packages: sees system "
    echo "   opencv/numpy/evdev/PyQt6) =="
    "$PYTHON" -m venv --system-site-packages .venv
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
