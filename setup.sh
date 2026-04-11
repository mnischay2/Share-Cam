#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  CamShare · Virtual Camera Setup Script
#  Installs v4l2loopback & FFmpeg.
#  Run once on the UTILISER machine.
# ─────────────────────────────────────────────────────────────────

set -e

GREEN='\033[0;32m'
AMBER='\033[0;33m'
RED='\033[0;31m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "${GREEN}  ██████╗ █████╗ ███╗   ███╗███████╗██╗  ██╗ █████╗ ██████╗ ███████╗${RESET}"
echo -e "${GREEN} ██╔════╝██╔══██╗████╗ ████║██╔════╝██║  ██║██╔══██╗██╔══██╗██╔════╝${RESET}"
echo -e "${GREEN} ██║     ███████║██╔████╔██║███████╗███████║███████║██████╔╝█████╗  ${RESET}"
echo -e "${GREEN} ██║     ██╔══██║██║╚██╔╝██║╚════██║██╔══██║██╔══██║██╔══██╗██╔══╝  ${RESET}"
echo -e "${GREEN} ╚██████╗██║  ██║██║ ╚═╝ ██║███████║██║  ██║██║  ██║██║  ██║███████╗${RESET}"
echo -e "${GREEN}  ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝${RESET}"
echo ""
echo -e "${DIM}  Virtual Camera Setup · Utiliser Mode${RESET}"
echo ""

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
  OS="mac"
  echo -e "${AMBER}⚠  macOS detected.${RESET}"
  echo "   CamShare's virtual camera uses v4l2loopback which is Linux-only."
  echo "   On macOS, use OBS with Virtual Camera, or install obs-mac-virtualcam."
  echo "   https://obsproject.com"
  echo ""
  echo "   The server will still run and stream to OBS or any WebRTC-compatible player."
  exit 0
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
  echo -e "${AMBER}⚠  Windows detected.${RESET}"
  echo "   Use OBS Virtual Camera or UnityCapture on Windows."
  echo "   https://obsproject.com"
  exit 0
fi

echo -e "${GREEN}✓ Linux detected${RESET}"
echo ""

# Check for root or sudo
if [ "$EUID" -ne 0 ]; then
  SUDO="sudo"
  echo -e "${AMBER}→ Will use sudo for privileged commands${RESET}"
else
  SUDO=""
fi

# Detect package manager
if command -v apt-get &>/dev/null; then
  PKG="apt"
elif command -v dnf &>/dev/null; then
  PKG="dnf"
elif command -v pacman &>/dev/null; then
  PKG="pacman"
else
  echo -e "${RED}✗ Unsupported package manager. Install manually:${RESET}"
  echo "  - v4l2loopback-dkms"
  echo "  - ffmpeg"
  exit 1
fi

echo "─── Installing dependencies ──────────────────────────────────"

# Install v4l2loopback
if ! modinfo v4l2loopback &>/dev/null; then
  echo -e "${AMBER}→ Installing v4l2loopback...${RESET}"
  if [ "$PKG" = "apt" ]; then
    $SUDO apt-get install -y v4l2loopback-dkms v4l2loopback-utils
  elif [ "$PKG" = "dnf" ]; then
    $SUDO dnf install -y v4l2loopback
  elif [ "$PKG" = "pacman" ]; then
    $SUDO pacman -Sy --noconfirm v4l2loopback-dkms
  fi
else
  echo -e "${GREEN}✓ v4l2loopback already installed${RESET}"
fi

# Install FFmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo -e "${AMBER}→ Installing FFmpeg...${RESET}"
  if [ "$PKG" = "apt" ]; then
    $SUDO apt-get install -y ffmpeg
  elif [ "$PKG" = "dnf" ]; then
    $SUDO dnf install -y ffmpeg
  elif [ "$PKG" = "pacman" ]; then
    $SUDO pacman -Sy --noconfirm ffmpeg
  fi
  echo -e "${GREEN}✓ FFmpeg installed${RESET}"
else
  echo -e "${GREEN}✓ FFmpeg already installed${RESET}"
fi

echo ""
echo "─── Loading v4l2loopback kernel module ───────────────────────"

# Unload existing instance if loaded without correct params
if lsmod | grep -q v4l2loopback; then
  echo -e "${AMBER}→ Reloading module with CamShare params...${RESET}"
  $SUDO modprobe -r v4l2loopback 2>/dev/null || true
fi

# Load with CamShare settings
DEVICE=${VCAM_DEVICE_NR:-42}
$SUDO modprobe v4l2loopback \
  devices=1 \
  video_nr=$DEVICE \
  card_label="CamShare" \
  exclusive_caps=1

if [ $? -eq 0 ]; then
  sleep 1
  $SUDO chmod 666 /dev/video${DEVICE}
  echo -e "${GREEN}✓ v4l2loopback loaded → /dev/video${DEVICE} (label: CamShare)${RESET}"
else
  echo -e "${RED}✗ Failed to load v4l2loopback${RESET}"
  exit 1
fi

echo ""
echo "─────────────────────────────────────────────────────────────"
echo -e "${GREEN}  ✦ Setup complete!${RESET}"
echo ""
echo "  Virtual camera system:  FFmpeg + v4l2loopback"
echo "  Device path:            /dev/video${DEVICE}"
echo "  Label:                  CamShare"
echo ""
echo "  Next steps:"
echo "  1. Run:  npm start"
echo "  2. Open: http://localhost:3000"
echo "  3. On this device (utiliser) click 'Start Virtual Camera'"
echo "  4. Open OBS, Zoom, Meet — select 'CamShare' as webcam"
echo ""
