#!/usr/bin/env bash
# install.sh — ShareCam Linux setup
# Run once as a normal user (will sudo when needed).
# Tested on: Ubuntu 22.04 / 24.04

set -euo pipefail

VENV_DIR=".venv"
V4L2_DEVICE_NR=2

echo ""
echo "══════════════════════════════════════════"
echo "  ShareCam — Linux Setup"
echo "══════════════════════════════════════════"

# ── 1. System deps ────────────────────────────────────────────────────────
echo "[1/5] Installing system packages…"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    v4l2loopback-dkms v4l-utils \
    ffmpeg \
    libopencv-dev

# ── 2. Load v4l2loopback ──────────────────────────────────────────────────
echo "[2/5] Loading v4l2loopback kernel module…"
sudo modprobe v4l2loopback \
    devices=1 \
    video_nr=${V4L2_DEVICE_NR} \
    card_label="ShareCam" \
    exclusive_caps=1 \
    || echo "  ⚠  v4l2loopback already loaded or failed — check: lsmod | grep v4l2"

# Make it persistent across reboots
MODPROBE_CONF="/etc/modprobe.d/sharecam.conf"
if [ ! -f "$MODPROBE_CONF" ]; then
    echo "options v4l2loopback devices=1 video_nr=${V4L2_DEVICE_NR} card_label=ShareCam exclusive_caps=1" \
        | sudo tee "$MODPROBE_CONF" > /dev/null
    echo "  v4l2loopback module options saved to $MODPROBE_CONF"
fi

MODULES_CONF="/etc/modules-load.d/sharecam.conf"
if [ ! -f "$MODULES_CONF" ]; then
    echo "v4l2loopback" | sudo tee "$MODULES_CONF" > /dev/null
fi

# ── 3. Python virtualenv ──────────────────────────────────────────────────
echo "[3/5] Creating Python virtualenv…"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[4/5] Installing Python dependencies…"
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 4. Verify virtual device ──────────────────────────────────────────────
echo "[5/5] Checking virtual device…"
if v4l2-ctl --list-devices 2>/dev/null | grep -q "ShareCam\|video${V4L2_DEVICE_NR}"; then
    echo "  ✓ Virtual camera device: /dev/video${V4L2_DEVICE_NR}"
else
    echo "  ⚠  /dev/video${V4L2_DEVICE_NR} not found — you may need to reboot or re-run:"
    echo "     sudo modprobe v4l2loopback devices=1 video_nr=${V4L2_DEVICE_NR} card_label=ShareCam exclusive_caps=1"
fi

echo ""
echo "══════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  To start ShareCam:"
echo "    source .venv/bin/activate"
echo "    python run.py"
echo ""
echo "  Custom device / port:"
echo "    python run.py --device /dev/video2 --port 8443"
echo "══════════════════════════════════════════"
echo ""
