"""
mdns_service.py — Advertises ShareCam over mDNS (_sharecam._tcp.local.)
so the mobile client can find the host without manual IP entry.
"""
import logging
import socket

logger = logging.getLogger("sharecam.mdns")


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class MDNSService:
    """Thin wrapper around python-zeroconf for mDNS advertisement."""

    def __init__(self, port: int = 8443):
        self.port = port
        self._zeroconf = None
        self._info = None

    def start(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf

            local_ip = get_local_ip()
            self._zeroconf = Zeroconf()
            self._info = ServiceInfo(
                "_sharecam._tcp.local.",
                "ShareCam._sharecam._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "path": "/",
                    "version": "1.0",
                    "tls": "1",
                },
                server="sharecam.local.",
            )
            self._zeroconf.register_service(self._info)
            logger.info(f"mDNS active — sharecam.local → {local_ip}:{self.port}")
        except ImportError:
            logger.warning("zeroconf not installed — mDNS disabled. Run: pip install zeroconf")
        except Exception as exc:
            logger.warning(f"mDNS failed to start: {exc}")

    def stop(self) -> None:
        if self._zeroconf and self._info:
            try:
                self._zeroconf.unregister_service(self._info)
                self._zeroconf.close()
                logger.info("mDNS stopped.")
            except Exception:
                pass
