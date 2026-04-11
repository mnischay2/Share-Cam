# CamShare

Share any device's camera over your local network. The receiving device mounts it as a **virtual webcam driver** — usable by OBS, Zoom, Meet, any app.

```
[Host Device]              [Utiliser Device]
  webcam                      /dev/video0 (CamShare)
    │                               ▲
    │   WebRTC (LAN, <100ms)        │
    └──────────────────────────────►│
                              ffmpeg pipe
                           (v4l2loopback)
```

---

## Quick Start

### 1. Install dependencies
```bash
npm install
```

### 2. Setup virtual camera (utiliser device only — Linux)
```bash
chmod +x setup.sh
./setup.sh
```
This installs `v4l2loopback` + `ffmpeg` and creates `/dev/video0` labelled **CamShare**.

### 3. Start the server
```bash
npm start
```

Open `http://localhost:3000` on **both** devices (or use your machine's LAN IP for the second device).

---

## Usage

### Host Device
1. Go to `http://<server-ip>:3000` → **HOST**
2. Select your camera from the dropdown
3. Choose quality and room name
4. Click **Start Hosting**

### Utiliser Device
1. Go to `http://<server-ip>:3000` → **UTILISER**
2. Select the room (or enter the room ID)
3. Click **Connect** — the live feed appears
4. Click **Start Virtual Camera** to pipe it to `/dev/video0`
5. Open any app (OBS, Zoom, etc.) and select **CamShare** as your webcam

---

## How it Works

| Layer | Technology |
|-------|-----------|
| Signaling | Socket.IO |
| Video transport | WebRTC (P2P over LAN) |
| Frame capture | Canvas `getImageData` → RGBA→BGR24 |
| Virtual driver | `ffmpeg` rawvideo → `v4l2loopback` |
| Virtual device | `/dev/video0` (label: CamShare) |

The utiliser's browser captures frames from the WebRTC stream via `<canvas>`, converts pixel data from RGBA to raw BGR24, and emits it over a Socket.IO event. The Node.js server pipes the frames to `ffmpeg`, which writes them to the v4l2loopback device.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | Server port |
| `VCAM_DEVICE` | `/dev/video0` | Virtual camera device path |
| `VCAM_WIDTH` | `1280` | Frame width for ffmpeg |
| `VCAM_HEIGHT` | `720` | Frame height for ffmpeg |

Example:
```bash
PORT=8080 VCAM_DEVICE=/dev/video2 VCAM_WIDTH=1920 VCAM_HEIGHT=1080 npm start
```

---

## Platform Notes

### Linux ✅
Full support. Run `./setup.sh` for one-time setup.

### macOS ⚠️
WebRTC streaming works. For virtual camera, use **OBS + Virtual Camera**:
1. Add a Browser Source in OBS pointing to the utiliser page
2. Start OBS Virtual Camera

### Windows ⚠️
WebRTC streaming works. For virtual camera, use **OBS Virtual Camera** or **UnityCapture**.

---

## Multiple Utilisers

Multiple devices can connect to the same room simultaneously. Each gets an independent WebRTC connection from the host. Each utiliser can independently start/stop their own virtual camera.

---

## Troubleshooting

**Virtual camera not showing in apps:**
```bash
# Check the device exists
ls /dev/video*

# Check v4l2loopback loaded
lsmod | grep v4l2loopback

# Check ffmpeg is in PATH
which ffmpeg
```

**WebRTC connection fails:**
- Ensure both devices are on the same LAN
- Some corporate networks block WebRTC — try disabling VPN

**Permission denied on /dev/video0:**
```bash
sudo usermod -aG video $USER
# Then log out and back in
```
