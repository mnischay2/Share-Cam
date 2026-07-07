#!/usr/bin/env python3
"""
run.py — ShareCam entry point.
Usage: python run.py [--device /dev/video42] [--port 8443] [--regen-cert]
"""
import argparse
import os   
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))


def check_device_health(device: str) -> None:
    """Check if the v4l2loopback device is healthy; attempt recovery if not."""
    if not device or not device.startswith("/dev/video"):
        return
    
    if sys.platform != "linux":
        return
    
    if not os.path.exists(device):
        print(f"[Device Health] {device} not found.")
        return
    
    # Try to stat the device to see if it's accessible
    try:
        os.stat(device)
        # If stat succeeds, device is likely healthy
        return
    except OSError as e:
        print(f"[Device Health] {device} is inaccessible: {e}")
        print("[Device Health] Attempting automatic recovery...")
        
        # Import the recovery function from virtualcam
        from server.virtualcam import _recover_v4l2loopback
        
        if _recover_v4l2loopback(device):
            print("[Device Health] ✓ Device recovered successfully!")
        else:
            dev_nr = device.replace("/dev/video", "")
            print(f"[Device Health] Recovery failed. Manual fix required:")
            print(f"  sudo modprobe -r v4l2loopback")
            print(f"  sudo modprobe v4l2loopback devices=1 video_nr={dev_nr} card_label='ShareCam'")
            print(f"  python run.py")


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

    # Pre-flight: check device health
    if not args.obs:
        check_device_health(args.device)

    if args.regen_cert:
        from ssl_gen import generate_cert  # type: ignore
        generate_cert(srv.CERT_PATH, srv.KEY_PATH, force=True)

    srv.main()


if __name__ == "__main__":
    main()
