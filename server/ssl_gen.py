"""
ssl_gen.py — Self-signed TLS 1.3 certificate generator for ShareCam.
Embeds the host's LAN IP into the SAN so mobile browsers accept it.
"""
import datetime
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def get_local_ip() -> str:
    """Reliably detect the LAN IP (works behind CGNAT / Jio)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def generate_cert(
    cert_path: str = "cert.pem",
    key_path: str = "key.pem",
    force: bool = False,
) -> tuple[str, str]:
    """
    Generate a self-signed certificate valid for 365 days.
    Skips generation if both files already exist (unless force=True).
    Returns (cert_path, key_path).
    """
    if not force and os.path.exists(cert_path) and os.path.exists(key_path):
        print(f"[SSL] Reusing existing certificate: {cert_path}")
        return cert_path, key_path

    local_ip = get_local_ip()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "ShareCam"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ShareCam Local"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("sharecam.local"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address(local_ip)),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )

    print(f"[SSL] Generated TLS 1.3 certificate — IP SAN: {local_ip}")
    return cert_path, key_path
