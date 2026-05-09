"""
virtualcam.py — pyvirtualcam bridge with a dedicated writer thread.

The writer thread owns the pyvirtualcam instance exclusively.
Frames are pushed via a small queue; the asyncio event loop is never blocked.
sleep_until_next_frame() is intentionally NOT called — the network/encoder
pace is the natural rate limiter, and calling it on the event loop would
stall WebSocket reception.
"""
import logging
import platform
import queue
import threading

import cv2
import numpy as np

logger = logging.getLogger("sharecam.vcam")


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
            if self.device is not None:
                dev_nr = self.device.replace("/dev/video", "")
                logger.error(
                    f"Run: sudo modprobe v4l2loopback devices=1 "
                    f"video_nr={dev_nr} card_label='ShareCam' exclusive_caps=1"
                )
            else:
                logger.error("OBS VirtualCam not detected. Install OBS Studio or use a v4l2loopback device.")
            logger.warning("Continuing WITHOUT virtual camera output.")
        finally:
            self._active = False
            self._ready.set()
