"""LAN CA so iPhone Safari treats the HUD as a secure page (microphone)."""

from __future__ import annotations

import base64
import datetime as dt
import ipaddress
import uuid
from pathlib import Path

from jarvis.config import DATA_DIR
from jarvis.lan import lan_ipv4

CERT_DIR = DATA_DIR / "certs"
CA_FILE = CERT_DIR / "ca.pem"
CA_KEY_FILE = CERT_DIR / "ca.key"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"
PROFILE_FILE = CERT_DIR / "Ilaria-CA.mobileconfig"

_DNS = ("localhost", "ilaria.local", "ilaria")


def ensure_lan_certs() -> tuple[Path, Path]:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if not _ca_ok():
        _write_ca()
    if not _server_covers_lan():
        _write_server()
    _write_mobileconfig()
    return CERT_FILE, KEY_FILE


def profile_file() -> Path:
    ensure_lan_certs()
    return PROFILE_FILE


def _ca_ok() -> bool:
    return CA_FILE.is_file() and CA_KEY_FILE.is_file() and CA_FILE.stat().st_size > 32


def _server_covers_lan() -> bool:
    if not CERT_FILE.is_file() or not KEY_FILE.is_file():
        return False
    if CERT_FILE.stat().st_size < 32:
        return False
    try:
        from cryptography import x509
    except ImportError:
        return True
    cert = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    have = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    need = {"127.0.0.1", *lan_ipv4()}
    return need.issubset(have)


def _write_ca() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ilaria")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    CA_KEY_FILE.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CA_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _write_server() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ca_key = serialization.load_pem_private_key(CA_KEY_FILE.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(CA_FILE.read_bytes())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    san: list[x509.GeneralName] = [x509.DNSName(item) for item in _DNS]
    for raw in ("127.0.0.1", "::1", *lan_ipv4()):
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(raw)))
        except ValueError:
            continue
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ilaria.local")]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _write_mobileconfig() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    ca = x509.load_pem_x509_certificate(CA_FILE.read_bytes())
    der = base64.encodebytes(ca.public_bytes(serialization.Encoding.DER)).decode("ascii")
    profile_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "app.gsuss.ilaria.profile"))
    cert_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "app.gsuss.ilaria.ca"))
    PROFILE_FILE.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadCertificateFileName</key>
      <string>Ilaria.cer</string>
      <key>PayloadContent</key>
      <data>{der}</data>
      <key>PayloadDescription</key>
      <string>Permette il microfono di Ilaria sul Wi-Fi di casa</string>
      <key>PayloadDisplayName</key>
      <string>Ilaria</string>
      <key>PayloadIdentifier</key>
      <string>app.gsuss.ilaria.ca</string>
      <key>PayloadType</key>
      <string>com.apple.security.root</string>
      <key>PayloadUUID</key>
      <string>{cert_id}</string>
      <key>PayloadVersion</key>
      <integer>1</integer>
    </dict>
  </array>
  <key>PayloadDisplayName</key>
  <string>Ilaria</string>
  <key>PayloadIdentifier</key>
  <string>app.gsuss.ilaria.profile</string>
  <key>PayloadRemovalDisallowed</key>
  <false/>
  <key>PayloadType</key>
  <string>Configuration</string>
  <key>PayloadUUID</key>
  <string>{profile_id}</string>
  <key>PayloadVersion</key>
  <integer>1</integer>
</dict>
</plist>
""",
        encoding="utf-8",
    )
