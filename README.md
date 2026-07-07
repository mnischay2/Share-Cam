# ShareCam

Turn your smartphone into a high-fidelity virtual webcam over your local network.
**No cloud. No drivers to install on the phone. Sub-150ms latency.**

```
Phone  ──(H.264/WSS)──►  Host PC  ──►  /dev/videoX  ──►  Zoom / Meet / OBS
```

---

## Key Features

- 🔒 **Zero Cloud, 100% Local**: Secure WebSocket (WSS/TLS 1.3) connection ensures your stream stays private within your local network (LAN).
- ⚡ **Sub-150ms Latency**: Employs browser WebCodecs API (`VideoEncoder`) for hardware-accelerated H.264 encoding on the phone, and PyAV on the host for ultra-low latency.
- 📱 **Zero App Installs**: Run straight from your mobile browser (Chrome on Android, Safari on iOS). Pairing is as simple as scanning the printed terminal QR code or navigating to `https://sharecam.local:8443`.
- 🩺 **Auto-Recovery & Health Check**: The [run.py](file:///home/nischay/home/github/share-Cam/run.py) script automatically performs a pre-flight health check on Linux, reloading the `v4l2loopback` kernel module if it is missing or corrupted.
- 🖼️ **Aspect Ratio Padding**: Automatic letterboxing/pillarboxing in [virtualcam.py](file:///home/nischay/home/github/share-Cam/server/virtualcam.py) maintains your camera's proportional aspect ratio, preventing any stretching or distortion.
- 🔄 **Dynamic Orientation Matching**: Automatically detects phone rotation/resize events, updates the Python backend config on the fly, and restarts the streaming pipeline seamlessly.
- 📉 **Smart Congestion Control**: Real-time buffer monitoring drops lagging non-keyframes automatically if Wi-Fi throughput dips, keeping latency consistently low.
- 🍏 **iOS Safari Fallback**: Detects Web API limitations and falls back to an `ImageCapture` frame-grab loop when `MediaStreamTrackProcessor` is unavailable (e.g., Safari/non-secure context).

---

## Architecture

| Layer | Tech | Description |
|---|---|---|
| **Discovery** | mDNS + QR Code | Advertises `sharecam.local` via [mdns_service.py](file:///home/nischay/home/github/share-Cam/server/mdns_service.py) |
| **Transport** | Secure WebSocket | Fast full-duplex binary control & stream channels using FastAPI + Uvicorn |
| **Certificates** | Self-signed TLS 1.3 | Generated on the fly with SAN IPs by [ssl_gen.py](file:///home/nischay/home/github/share-Cam/server/ssl_gen.py) |
| **Encoding** | H.264 Annex-B | Hardware-accelerated client-side encoding via WebCodecs API in [index.html](file:///home/nischay/home/github/share-Cam/client/index.html) |
| **Decoding** | FFmpeg / PyAV | Highly optimized CPU H.264 decoding in [decoder.py](file:///home/nischay/home/github/share-Cam/server/decoder.py) |
| **Output** | `pyvirtualcam` | Writes raw frames to OS virtual loopback device (V4L2 on Linux, OBS on Windows) |

---

## How It Works

ShareCam captures, encodes, transmits, decodes, and outputs video frames in real time over local networks using custom pipelines:

1. **Capture & Process (Mobile)**: The mobile browser captures camera frames using `getUserMedia`. On supported platforms (e.g. Chrome/Android), it utilizes the zero-copy `MediaStreamTrackProcessor` API to read frames directly. On others (e.g. iOS/Safari), it falls back to a precise timer interval polling frames via `ImageCapture.grabFrame()`.
2. **Hardware Acceleration (Mobile)**: Frames are encoded to raw H.264 Annex-B format using the native WebCodecs `VideoEncoder` API. It uses a low-overhead Baseline profile (`avc1.42002a`) to eliminate CPU-intensive encoding features, ensuring high performance.
3. **Low-Latency Transport**: Raw H.264 NAL units are streamed over a local secure WebSocket (`wss://`) hosted by FastAPI/Uvicorn. If the network buffers build up, a client-side congestion control routine drops non-keyframes to keep delay under 150ms.
4. **Fast Decoding (Host)**: The host python engine schedules decoding tasks off the main ASGI loop via an executor. [decoder.py](file:///home/nischay/home/github/share-Cam/server/decoder.py) uses PyAV (FFmpeg bindings) to deserialize packets and decode them into raw BGR numpy arrays with `low_delay` and `fast` flags.
5. **Frame Alignment (Host)**: Server-side rotation is applied dynamically using OpenCV. If the frame's aspect ratio differs from the virtual camera layout (such as when rotating the phone), [virtualcam.py](file:///home/nischay/home/github/share-Cam/server/virtualcam.py) pads the frames with black borders (letterbox/pillarbox) to prevent stretching.
6. **Kernel-Level Output (Host)**: BGR frames are fed into a dedicated writer thread that pushes them to `pyvirtualcam`. Under Linux, this pipes to `v4l2loopback` loaded with `exclusive_caps=1` so external video applications recognize it as a real USB webcam. Under Windows, it feeds OBS VirtualCam.

---

## Quick Start

### Linux (Ubuntu 22.04 / 24.04)

1. Clone the repository and navigate into it:
   ```bash
   git clone https://github.com/mnischay2/share-Cam.git sharecam && cd sharecam
   ```
2. Run the one-time installation script (installs system tools, builds `v4l2loopback` module, and configures the python virtual environment):
   ```bash
   chmod +x install.sh && ./install.sh
   ```
3. Activate the virtual environment and start the engine:
   ```bash
   source .venv/bin/activate
   python run.py
   ```

### Windows

1. Run the setup script (requires Python 3.11+ and [OBS Studio](https://obsproject.com/) with its VirtualCam active):
   ```bat
   install_windows.bat
   ```
2. Activate and start:
   ```bat
   .venv\Scripts\activate.bat
   python run.py --obs
   ```

---

## Connecting Your Phone

1. Ensure the Host PC and phone are connected to the **same local Wi-Fi network**.
2. Run `python run.py` — a pairing QR code will be generated and printed to your terminal.
3. Open your phone's camera and scan the QR code.
4. Because the TLS connection uses a dynamically generated local self-signed certificate:
   - **On Android/Chrome**: Tap **Advanced** → **Proceed** to bypass the certificate warnings.
   - **On iOS/Safari**: Trust the self-signed certificate via Settings if prompted, or allow the connection.
5. Tap **Connect & Stream** inside the web page.

---

## CLI Options

Configure the engine using command-line arguments in [run.py](file:///home/nischay/home/github/share-Cam/run.py):

| Flag | Type | Default | Description |
|---|---|---|---|
| `--device` | string | `/dev/video42` | Path to the Linux `v4l2loopback` device. |
| `--obs` | flag | `False` | Use OBS VirtualCam (ignores `--device` and auto-discovers on Windows/Linux). |
| `--port` | integer | `8443` | Port for the HTTPS/WSS server. |
| `--regen-cert`| flag | `False` | Force regenerate the self-signed SSL/TLS certificate. |

Examples:
```bash
# Stream to a specific loopback node
python run.py --device /dev/video2

# Auto-discover OBS VirtualCam
python run.py --obs

# Force regeneration of self-signed SSL certificates
python run.py --regen-cert --port 9000
```

---

## Performance Targets

| Metric | Target |
|---|---|
| **Latency** | < 150ms (average 80ms) |
| **Resolution** | Up to 1080p (depends on network and camera capabilities) |
| **Frame Rate** | Up to 60fps |
| **Bitrate** | Adaptive 2.5–10 Mbps |
| **Color Space** | yuv420p → BGR |

---

## Troubleshooting

### "Insecure Connection" warning on phone
This is completely expected because the host server uses a dynamically generated, self-signed certificate targeting local LAN IP addresses.
- **Android/Chrome:** Click **Advanced** → **Proceed to `<IP>` (unsafe)**.
- **iOS/Safari:** If Safari refuses to load, try Chrome or navigate to the settings to allow untrusted certificates.

### Virtual camera not found (Linux)
If `/dev/video42` is not detected, `run.py` attempts auto-recovery. If it fails, you can reload the module manually:
```bash
# Reload kernel module manually
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 video_nr=42 card_label="ShareCam" exclusive_caps=1

# Verify the node is created
v4l2-ctl --list-devices
```

### No camera permission on phone
Mobile browsers only allow camera access under **HTTPS** origins. ShareCam enforces HTTPS by default. If typing the URL manually, ensure you use `https://` and not `http://`.

### WebCodecs not available
WebCodecs requires Chrome 94+ (Android) or Safari 17.4+ (iOS). If your browser does not support it (e.g. Firefox), the page will display a warning.

### High latency / Stuttering
- Switch the resolution chip in the browser from **1080p** to **720p** (especially on congested 2.4GHz Wi-Fi).
- Ensure your phone and host PC are on the same Wi-Fi band/SSID (avoid connection loops across mesh node hops).
- Watch the **Send Buffer** bar in the app — if it turns red, it means the network cannot keep up; reduce resolution or frame rate.

---

## File Structure

```
sharecam/
├── server/
│   ├── main.py          # FastAPI HTTPS server + WebSocket endpoint ([main.py](file:///home/nischay/home/github/share-Cam/server/main.py))
│   ├── ssl_gen.py       # Self-signed TLS 1.3 cert generator ([ssl_gen.py](file:///home/nischay/home/github/share-Cam/server/ssl_gen.py))
│   ├── mdns_service.py  # mDNS advertisement (sharecam.local) ([mdns_service.py](file:///home/nischay/home/github/share-Cam/server/mdns_service.py))
│   ├── decoder.py       # H.264 → NumPy BGR via PyAV ([decoder.py](file:///home/nischay/home/github/share-Cam/server/decoder.py))
│   └── virtualcam.py    # pyvirtualcam bridge & aspect ratio padder ([virtualcam.py](file:///home/nischay/home/github/share-Cam/server/virtualcam.py))
├── client/
│   └── index.html       # Mobile SPA (WebCodecs encoder + WebSocket) ([index.html](file:///home/nischay/home/github/share-Cam/client/index.html))
├── run.py               # Main entry point ([run.py](file:///home/nischay/home/github/share-Cam/run.py))
├── requirements.txt     # Python dependencies ([requirements.txt](file:///home/nischay/home/github/share-Cam/requirements.txt))
├── install.sh           # Linux setup script ([install.sh](file:///home/nischay/home/github/share-Cam/install.sh))
└── install_windows.bat  # Windows setup script ([install_windows.bat](file:///home/nischay/home/github/share-Cam/install_windows.bat))
```

---

## License

MIT
