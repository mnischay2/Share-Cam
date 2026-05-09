"""
main.py — ShareCam Host Engine

Responsibilities:
  • HTTPS server (TLS 1.3 self-signed) — serves the mobile SPA
  • WSS /stream endpoint — receives H.264 NAL units from the phone
  • Decodes frames via PyAV and writes to pyvirtualcam virtual device
  • Prints QR code to terminal for zero-config pairing
  • Advertises sharecam.local via mDNS
"""
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

# Project-local imports
sys.path.insert(0, str(Path(__file__).parent))
from decoder import H264Decoder
from mdns_service import MDNSService
from ssl_gen import generate_cert, get_local_ip
from virtualcam import VirtualCam

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PORT = 8443
CLIENT_HTML = Path(__file__).parent.parent / "client" / "index.html"
CERT_PATH = str(Path(__file__).parent.parent / "cert.pem")
KEY_PATH = str(Path(__file__).parent.parent / "key.pem")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sharecam")

# ---------------------------------------------------------------------------
# Shared state (single active stream)
# ---------------------------------------------------------------------------
decoder = H264Decoder()
vcam = VirtualCam()

stream_cfg: dict = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "rotation": 0,
}
stats: dict = {
    "frames_decoded": 0,
    "bytes_received": 0,
    "connected": False,
    "client_ip": None,
}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="ShareCam", docs_url=None, redoc_url=None)


@app.get("/")
async def serve_client():
    """Serve the mobile SPA."""
    if CLIENT_HTML.exists():
        return FileResponse(CLIENT_HTML, media_type="text/html")
    return JSONResponse({"error": "client/index.html not found"}, status_code=404)


@app.get("/status")
async def get_status():
    return JSONResponse({**stats, **stream_cfg})


@app.websocket("/stream")
async def stream_endpoint(ws: WebSocket):
    """
    Binary WebSocket endpoint.
    Text frames: JSON control messages (config, ping)
    Binary frames: raw H.264 Annex-B NAL units
    """
    global stream_cfg

    await ws.accept()
    client = f"{ws.client.host}:{ws.client.port}"
    logger.info(f"📱 Client connected: {client}")
    stats["connected"] = True
    stats["client_ip"] = ws.client.host

    # Request an immediate keyframe once connected
    try:
        await ws.send_text(json.dumps({"type": "request_keyframe"}))
    except Exception:
        pass

    try:
        while True:
            message = await ws.receive()

            # ── Control / config message ────────────────────────────────
            if "text" in message:
                try:
                    msg = json.loads(message["text"])
                    msg_type = msg.get("type")

                    if msg_type == "config":
                        new_w = int(msg.get("width", 1920))
                        new_h = int(msg.get("height", 1080))
                        new_fps = int(msg.get("fps", 30))
                        new_rot = int(msg.get("rotation", 0))

                        dims_changed = (
                            new_w != stream_cfg["width"]
                            or new_h != stream_cfg["height"]
                            or new_fps != stream_cfg["fps"]
                        )
                        stream_cfg.update(
                            width=new_w, height=new_h, fps=new_fps, rotation=new_rot
                        )

                        if dims_changed:
                            logger.info(
                                f"Stream config updated → "
                                f"{new_w}×{new_h}@{new_fps}fps  rot={new_rot}°"
                            )
                        #    vcam.reconfigure(new_w, new_h, new_fps)
                            decoder.reset()

                    elif msg_type == "ping":
                        await ws.send_text(json.dumps({"type": "pong"}))

                except (json.JSONDecodeError, ValueError) as exc:
                    logger.debug(f"Bad text message: {exc}")

            # ── H.264 NAL units (binary) ────────────────────────────────
            elif "bytes" in message:
                nal_data: bytes = message["bytes"]
                stats["bytes_received"] += len(nal_data)

                try:
                    # Run synchronous PyAV decode in a thread so the
                    # event loop stays free to receive the next WS frame.
                    rot = stream_cfg["rotation"]
                    loop = asyncio.get_event_loop()
                    frames = await loop.run_in_executor(
                        None, lambda: decoder.decode(nal_data, rot)
                    )
                    for frame in frames:
                        vcam.send(frame)   # non-blocking queue put
                        stats["frames_decoded"] += 1
                except Exception as exc:
                    logger.debug(f"Frame processing error (non-fatal): {exc}")

    except WebSocketDisconnect:
        logger.info(f"📵 Client disconnected: {client}")
    except Exception as exc:
        logger.error(f"WebSocket error ({client}): {exc}")
    finally:
        stats["connected"] = False
        stats["client_ip"] = None


# ---------------------------------------------------------------------------
# Terminal QR code
# ---------------------------------------------------------------------------
def print_qr(url: str) -> None:
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)

        divider = "─" * 54
        print(f"\n  {divider}")
        print("  │  📷  S H A R E C A M  —  Scan to Connect  │")
        print(f"  {divider}")
        qr.print_ascii(invert=True)
        print(f"\n  URL : {url}")
        print(
            "  ⚠️   Tap 'Advanced → Proceed' when Chrome warns about the certificate."
        )
        print(f"  {divider}\n")
    except ImportError:
        print(f"\n[QR] Install qrcode for QR display → pip install qrcode")
        print(f"[QR] URL: {url}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    local_ip = get_local_ip()

    # 1. SSL
    cert, key = generate_cert(CERT_PATH, KEY_PATH)

    # 2. Virtual camera
    vcam.open()

    # 3. mDNS
    mdns = MDNSService(port=PORT)
    mdns.start()

    # 4. QR
    url = f"https://{local_ip}:{PORT}"
    print_qr(url)

    # 5. Graceful shutdown
    def _shutdown(*_):
        logger.info("Shutting down ShareCam…")
        mdns.stop()
        vcam.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 6. Uvicorn
    logger.info(f"ShareCam host engine running → {url}")
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT,
        ssl_certfile=cert,
        ssl_keyfile=key,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
