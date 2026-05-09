"""
virtualcam.py — pyvirtualcam bridge with a dedicated writer thread.

The writer thread owns the pyvirtualcam instance exclusively.
Frames are pushed via a small queue; the asyncio event loop is never blocked.
sleep_until_next_frame() is intentionally NOT called — the network/encoder
pace is the natural rate limiter, and calling it on the event loop would
stall WebSocket reception.
"""
import logging
import os
import platform
import queue
import subprocess
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger("sharecam.vcam")


def _recover_v4l2loopback(device: str, max_retries: int = 5) -> bool:
    """
    Recover a corrupted v4l2loopback device by reloading the kernel module.
    Returns True if recovery succeeded, False otherwise.
    """
    if not device or not device.startswith("/dev/video"):
        return False

    if platform.system() != "Linux":
        return False

    try:
        dev_nr = device.replace("/dev/video", "")
        logger.warning(f"Attempting to recover {device} by reloading v4l2loopback...")

        # Try to unload and reload the module
        for attempt in range(max_retries):
            try:
                # Unload the module
                logger.debug(f"[Recovery attempt {attempt + 1}/{max_retries}] Unloading v4l2loopback...")
                result = subprocess.run(
                    ["sudo", "modprobe", "-r", "v4l2loopback"],
                    capture_output=True,
                    timeout=10,
                    text=True,
                )
                if result.returncode != 0:
                    logger.debug(f"Unload output: {result.stderr}")
                
                # Wait longer to ensure clean unload
                time.sleep(2)

                # Reload the module
                logger.debug(f"[Recovery attempt {attempt + 1}/{max_retries}] Reloading v4l2loopback...")
                result = subprocess.run(
                    ["sudo", "modprobe", "v4l2loopback", f"devices=1", f"video_nr={dev_nr}", f"card_label=ShareCam"],
                    capture_output=True,
                    timeout=10,
                    text=True,
                )
                if result.returncode != 0:
                    logger.debug(f"Reload output: {result.stderr}")
                
                # Wait for device to be ready
                time.sleep(2)

                # Verify the device exists AND is accessible
                if os.path.exists(device):
                    try:
                        # Try to open and immediately close to verify it's a valid video device
                        os.stat(device)
                        logger.info(f"✓ Successfully recovered {device}")
                        return True
                    except OSError as e:
                        logger.debug(f"Device exists but not accessible: {e}")
                        continue
                else:
                    logger.debug(f"Device {device} still doesn't exist after reload")
                    continue
                    
            except subprocess.TimeoutExpired:
                logger.debug(f"[Recovery attempt {attempt + 1}/{max_retries}] Command timed out")
                time.sleep(1)
                continue
            except Exception as e:
                logger.debug(f"[Recovery attempt {attempt + 1}/{max_retries}] Exception: {e}")
                time.sleep(1)
                continue

        logger.error(f"Recovery failed after {max_retries} attempts - device may need manual recovery")
        return False
    except Exception as exc:
        logger.error(f"Recovery failed: {exc}")
        return False


class VirtualCam:
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        device: str = "/dev/video2",
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.device = device
        self._os = platform.system()
        self._queue: queue.Queue = queue.Queue(maxsize=6)
        self._thread = None
        self._running = False
        self._ready = threading.Event()
        self._active = False

    def open(self) -> None:
        if self._running:
            return
        self._running = True
        self._ready.clear()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True, name="vcam-writer")
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def send(self, frame: np.ndarray) -> None:
        if not self._active:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self._queue.put_nowait(frame.copy())
        except queue.Full:
            pass

    def reconfigure(self, width: int, height: int, fps: int) -> None:
        logger.info(f"VirtualCam reconfigure → {width}x{height}@{fps}fps")
        self.close()
        self.width = width
        self.height = height
        self.fps = fps
        self.open()

    def close(self) -> None:
        self._running = False
        self._active = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("VirtualCam closed.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def _writer_loop(self) -> None:
        try:
            import pyvirtualcam 
        except ImportError:
            logger.error("pyvirtualcam not installed.")
            self._ready.set()
            return

        kwargs = dict(
            width=self.width,
            height=self.height,
            fps=self.fps,
            fmt=pyvirtualcam.PixelFormat.BGR,
            print_fps=False,
        )
        # device=None → pyvirtualcam auto-discovers (picks OBS VirtualCam
        # or the first available v4l2loopback device on Linux)
        if self._os == "Linux" and self.device is not None:
            kwargs["device"] = self.device

        try:
            with pyvirtualcam.Camera(**kwargs) as cam:
                logger.info(f"VirtualCam open → {cam.device}  ({self.width}x{self.height}@{self.fps}fps)")
                print(f"[VirtualCam] ✓  Streaming to: {cam.device}")
                self._active = True
                self._ready.set()

                while self._running:
                    try:
                        frame = self._queue.get(timeout=0.05)
                    except queue.Empty:
                        continue

                    if frame is None:
                        break

                    h, w = frame.shape[:2]
                    if w != self.width or h != self.height:
                        frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

                    try:
                        cam.send(frame)
                        # NO sleep_until_next_frame() — it blocks this thread
                        # and backs up the queue while the event loop waits.
                    except Exception as exc:
                        logger.debug(f"cam.send: {exc}")

        except Exception as exc:
            logger.error(f"VirtualCam open failed: {exc}")
            recovered = False
            
            if self.device is not None:
                # Try to recover the corrupted device
                if "not a video output device" in str(exc) or "No such device" in str(exc):
                    logger.info("Device appears corrupted, attempting automatic recovery...")
                    if _recover_v4l2loopback(self.device):
                        logger.info("✓ Device recovered. Retrying open...")
                        recovered = True
                        
                        # Retry loop after successful recovery
                        retry_count = 0
                        max_retries = 5
                        while retry_count < max_retries and self._running:
                            try:
                                time.sleep(2)  # Wait between retries
                                with pyvirtualcam.Camera(**kwargs) as cam:
                                    logger.info(f"VirtualCam open → {cam.device}  ({self.width}x{self.height}@{self.fps}fps)")
                                    print(f"[VirtualCam] ✓  Streaming to: {cam.device}")
                                    self._active = True
                                    self._ready.set()

                                    while self._running:
                                        try:
                                            frame = self._queue.get(timeout=0.05)
                                        except queue.Empty:
                                            continue

                                        if frame is None:
                                            break

                                        h, w = frame.shape[:2]
                                        if w != self.width or h != self.height:
                                            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

                                        try:
                                            cam.send(frame)
                                        except Exception as e:
                                            logger.debug(f"cam.send: {e}")
                                    # Successfully ran the loop, exit retry
                                    break
                            except Exception as retry_exc:
                                retry_count += 1
                                logger.warning(f"Retry {retry_count}/{max_retries} failed: {retry_exc}")
                                if retry_count < max_retries:
                                    logger.info("Retrying in 2s...")
                                continue
                        
                        if retry_count >= max_retries:
                            logger.error(f"Failed to reopen after {max_retries} retries")
                    else:
                        dev_nr = self.device.replace("/dev/video", "")
                        logger.error(
                            f"Auto-recovery failed. Manual recovery:\n"
                            f"  sudo modprobe -r v4l2loopback\n"
                            f"  sudo modprobe v4l2loopback devices=1 video_nr={dev_nr} card_label='ShareCam'\n"
                            f"  python run.py"
                        )
                
                if not recovered:
                    dev_nr = self.device.replace("/dev/video", "")
                    logger.error(
                        f"Run: sudo modprobe v4l2loopback devices=1 "
                        f"video_nr={dev_nr} card_label='ShareCam'"
                    )
            else:
                logger.error("OBS VirtualCam not detected. Install OBS Studio or use a v4l2loopback device.")
            
            logger.warning("Continuing WITHOUT virtual camera output.")
        finally:
            self._active = False
            self._ready.set()
