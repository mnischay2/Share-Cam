#!/usr/bin/env python3
"""
run.py — ShareCam entry point.
Usage: python run.py [--device /dev/video42] [--port 8443] [--regen-cert]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))


def main():
    parser = argparse.ArgumentParser(description="ShareCam Host Engine")
    parser.add_argument("--device", default="/dev/video42", help="v4l2loopback device path. Ignored when --obs is set.")
    parser.add_argument("--obs", action="store_true", help="Use OBS VirtualCam (auto-discover device)")
    parser.add_argument("--port", type=int, default=8443, help="HTTPS/WSS port (default: 8443)")
    parser.add_argument("--regen-cert", action="store_true", help="Force regenerate SSL certificate")
    args = parser.parse_args()

    import server.main as srv  # type: ignore

    srv.PORT = args.port
    srv.vcam.device = None if args.obs else args.device

    if args.regen_cert:
        from ssl_gen import generate_cert  # type: ignore
        generate_cert(srv.CERT_PATH, srv.KEY_PATH, force=True)

    srv.main()


if __name__ == "__main__":
    main()
