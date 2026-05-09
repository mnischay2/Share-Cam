# ShareCam

Turn your smartphone into a high-fidelity virtual webcam over your local network.
**No cloud. No drivers to install on the phone. Sub-150ms latency.**

```
Phone  ──(H.264/WSS)──►  Host PC  ──►  /dev/videoX  ──►  Zoom / Meet / OBS
```

---

## Architecture

| Layer | Tech |
|---|---|
| Discovery | mDNS (`sharecam.local`) + QR code |
| Transport | Secure WebSocket (WSS / TLS 1.3) |
| Codec | H.264 Annex-B via WebCodecs API |
| Decode | PyAV (FFmpeg bindings) |
| Output | pyvirtualcam → v4l2loopback (Linux) / OBS VirtualCam (Windows) |

---

## Quick Start

### Linux (Ubuntu 22.04 / 24.04)

```bash
git clone <repo> sharecam && cd sharecam

# One-time setup (installs v4l2loopback, creates venv)
chmod +x install.sh && ./install.sh

# Run
source .venv/bin/activate
python run.py
```

### Windows

```bat
install_windows.bat
.venv\Scripts\activate.bat
python run.py
```

---

## Connecting Your Phone

1. Host PC and phone must be on the **same Wi-Fi network**.
2. Run `python run.py` — a QR code prints to the terminal.
3. Open the phone camera and scan the QR code.
4. Chrome will warn about the self-signed certificate → tap **Advanced → Proceed**.
5. Tap **Connect & Stream**.

---

## CLI Options

```
python run.py --device /dev/video2   # v4l2 device (Linux, default: /dev/video2)
              --port   8443          # HTTPS port (default: 8443)
              --regen-cert           # Force new TLS certificate
```

---

## Performance Targets

| Metric | Target |
|---|---|
| Latency | < 150ms (ideal 80ms) |
| Resolution | Up to 1080p |
| Frame Rate | Up to 60fps |
| Bitrate | 5–10 Mbps adaptive |
| Color Space | yuv420p → BGR |

---

## Troubleshooting

### "Insecure Connection" warning on phone
Expected. The certificate is self-signed.
- **Chrome/Android:** Advanced → Proceed to site
- **Safari/iOS:** Settings → General → VPN & Device Management → Trust certificate

### Virtual camera not found (Linux)
```bash
# Load manually
sudo modprobe v4l2loopback devices=1 video_nr=2 card_label="ShareCam" exclusive_caps=1

# Verify
v4l2-ctl --list-devices
```

### No camera permission on phone
The mobile SPA must be served over **HTTPS** — which ShareCam does by default.
If loading the URL manually, ensure you're using `https://`, not `http://`.

### WebCodecs not available
Requires Chrome 94+ or Edge 94+. Firefox does not support WebCodecs (as of 2025).
On iOS, WebCodecs requires Safari 17.4+.

### High latency
- Switch to 720p if on a 2.4GHz network.
- Ensure the phone and PC are on the **same access point** (not different SSIDs on a mesh).
- Check the **Send Buffer** bar in the app — if it's red, reduce resolution/fps.

---

## File Structure

```
sharecam/
├── server/
│   ├── main.py          # FastAPI HTTPS server + WebSocket endpoint
│   ├── ssl_gen.py       # Self-signed TLS 1.3 cert generator
│   ├── mdns_service.py  # mDNS advertisement (sharecam.local)
│   ├── decoder.py       # H.264 → NumPy BGR via PyAV
│   └── virtualcam.py    # pyvirtualcam bridge (Linux + Windows)
├── client/
│   └── index.html       # Mobile SPA (WebCodecs encoder + WebSocket)
├── run.py               # Entry point
├── requirements.txt
├── install.sh           # Linux one-shot setup
└── install_windows.bat
```

---

## License
MIT
