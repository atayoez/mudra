#!/bin/bash
# System setup for mudra: install packages + grant /dev/uinput access.
# Run with root via pkexec (no TTY needed) or sudo:
#     pkexec ./setup.sh
#
# Package names below are for openSUSE (zypper). On other distros install the
# equivalents: python3 + venv, opencv (python bindings), numpy, python-evdev,
# PyQt6, the Qt6 Wayland platform plugin.
set -euo pipefail

TARGET_USER="${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}"
TARGET_USER="${TARGET_USER:-${SUDO_USER:-$(id -nu)}}"

echo "== Installing system packages =="
zypper --non-interactive install --no-recommends \
    python313 python313-pip python313-opencv python313-numpy \
    python313-evdev python313-PyQt6 qt6-wayland

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

echo "== Done. User '$TARGET_USER' is in group 'input'. Next: ./install.sh =="
