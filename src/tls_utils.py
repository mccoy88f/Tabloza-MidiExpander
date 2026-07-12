"""Tabloza MidiExpander — certificato TLS locale (auto-firmato, LAN)."""

from __future__ import annotations

import logging
import os
import ssl
import subprocess
from pathlib import Path

from tabloza_common import DATA_DIR, HOSTNAME, MDNS_NAME

log = logging.getLogger("tabloza.tls")

TLS_DIR = DATA_DIR / "tls"
CERT_FILE = TLS_DIR / "cert.pem"
KEY_FILE = TLS_DIR / "key.pem"
CERT_DAYS = int(os.environ.get("TABLOZA_TLS_CERT_DAYS", "3650"))


def _primary_ip() -> str | None:
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        parts = result.stdout.strip().split()
        return parts[0] if parts else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _openssl_available() -> bool:
    try:
        subprocess.run(["openssl", "version"], capture_output=True, timeout=5, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_tls_certificate(*, force: bool = False) -> tuple[Path, Path]:
    """Genera (se assente) certificato auto-firmato per tabloza-me.local e IP LAN."""
    if not force and CERT_FILE.is_file() and KEY_FILE.is_file():
        return CERT_FILE, KEY_FILE

    if not _openssl_available():
        raise RuntimeError("openssl non disponibile: impossibile generare certificato TLS")

    TLS_DIR.mkdir(parents=True, exist_ok=True)
    san_parts = [
        f"DNS:{MDNS_NAME}",
        f"DNS:{HOSTNAME}",
        "DNS:localhost",
        "IP:127.0.0.1",
    ]
    ip = _primary_ip()
    if ip:
        san_parts.append(f"IP:{ip}")
    san = ",".join(san_parts)
    subject = f"/CN={MDNS_NAME}"

    cmd = [
        "openssl", "req", "-x509", "-nodes",
        "-newkey", "rsa:2048",
        "-keyout", str(KEY_FILE),
        "-out", str(CERT_FILE),
        "-days", str(CERT_DAYS),
        "-subj", subject,
        "-addext", f"subjectAltName={san}",
    ]
    subprocess.run(cmd, check=True, timeout=60)
    os.chmod(KEY_FILE, 0o600)
    os.chmod(CERT_FILE, 0o644)
    log.info("Certificato TLS generato (%s, SAN: %s)", CERT_FILE, san)
    return CERT_FILE, KEY_FILE


def load_ssl_context() -> ssl.SSLContext:
    cert, key = ensure_tls_certificate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx


def tls_cert_paths() -> dict:
    cert, key = ensure_tls_certificate()
    return {
        "cert": str(cert),
        "key": str(key),
        "hostname": MDNS_NAME,
    }


def read_certificate_pem() -> str:
    cert, _key = ensure_tls_certificate()
    return cert.read_text(encoding="utf-8")
