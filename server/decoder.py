"""
decoder.py — H.264 Annex-B NAL unit decoder via PyAV (FFmpeg bindings).
Applies server-side rotation via OpenCV when requested by the mobile client.
"""
import logging

import av
import cv2
import numpy as np

logger = logging.getLogger("sharecam.decoder")

_ROTATE_MAP = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


class H264Decoder:
    """
    Stateful H.264 decoder.

    Accepts raw Annex-B binary chunks (as received from the WebSocket) and
    returns fully decoded BGR numpy frames ready for pyvirtualcam.
    """

    def __init__(self) -> None:
        self._ctx: av.CodecContext | None = None
        self._reset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode(self, nal_data: bytes, rotation: int = 0) -> list[np.ndarray]:
        """
        Parse + decode one or more NAL units from `nal_data`.
        Returns a (possibly empty) list of BGR uint8 numpy arrays.
        """
        frames: list[np.ndarray] = []

        try:
            packets = self._ctx.parse(nal_data)
        except Exception as exc:
            logger.warning(f"NAL parse error — resetting codec context: {exc}")
            self._reset()
            return frames

        for pkt in packets:
            if pkt is None or pkt.size == 0:
                continue
            try:
                for av_frame in self._ctx.decode(pkt):
                    img: np.ndarray = av_frame.to_ndarray(format="bgr24")
                    if rotation in _ROTATE_MAP:
                        img = cv2.rotate(img, _ROTATE_MAP[rotation])
                    frames.append(img)
            except av.AVError as exc:
                # Non-fatal — keyframe might be missing; decoder will recover
                logger.debug(f"Frame decode skip: {exc}")

        return frames

    def reset(self) -> None:
        """Force a codec context reset (e.g. after stream reconfiguration)."""
        self._reset()
        logger.info("Decoder reset.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:
                pass
        self._ctx = av.CodecContext.create("h264", "r")
        # Low-latency decode flags
        self._ctx.options = {
            "flags": "low_delay",
            "flags2": "fast",
        }
