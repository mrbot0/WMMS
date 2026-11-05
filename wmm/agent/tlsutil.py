"""HTTPS on the local network (2.10): a self-signed certificate made here in pure Python (RSA 2048, SHA-256, X.509 v3
with the names and addresses of this PC), so the phone console, the PC sharing and the central server can answer over
TLS without extra packages. Clients pin its SHA-256 fingerprint the first time (trust on first use), shown in the
console so it can be compared by eye. The private key stays in dati\\tls, readable only by administrators."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import secrets
import socket
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# ---------- RSA ----------

_SMALL = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


def _probable_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    for p in _SMALL:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _probable_prime(n):
            return n


def rsa_key(bits: int = 2048) -> dict:
    e = 65537
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        d = pow(e, -1, phi)
        return {"n": n, "e": e, "d": d, "p": p, "q": q, "dp": d % (p - 1), "dq": d % (q - 1), "qi": pow(q, -1, p)}


# ---------- DER ----------

def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _len(len(body)) + body


def _int(v: int) -> bytes:
    b = v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big")
    return _tlv(0x02, b)


def _seq(*parti: bytes) -> bytes:
    return _tlv(0x30, b"".join(parti))


def _oid(testo: str) -> bytes:
    n = [int(x) for x in testo.split(".")]
    corpo = bytes([40 * n[0] + n[1]])
    for v in n[2:]:
        parti = [v & 0x7F]
        v >>= 7
        while v:
            parti.append(0x80 | (v & 0x7F))
            v >>= 7
        corpo += bytes(reversed(parti))
    return _tlv(0x06, corpo)


def _utf8(t: str) -> bytes:
    return _tlv(0x0C, t.encode("utf-8"))


def _time(t: datetime) -> bytes:
    return _tlv(0x18, t.strftime("%Y%m%d%H%M%SZ").encode()) if t.year >= 2050 else _tlv(0x17, t.strftime("%y%m%d%H%M%SZ").encode())


SHA256_RSA = _seq(_oid("1.2.840.113549.1.1.11"), b"\x05\x00")


def _name(cn: str, org: str) -> bytes:
    return _seq(_tlv(0x31, _seq(_oid("2.5.4.10"), _utf8(org))), _tlv(0x31, _seq(_oid("2.5.4.3"), _utf8(cn))))


def _sign(key: dict, dati: bytes) -> bytes:
    digest_info = _seq(_seq(_oid("2.16.840.1.101.3.4.2.1"), b"\x05\x00"), _tlv(0x04, hashlib.sha256(dati).digest()))
    k = (key["n"].bit_length() + 7) // 8
    blocco = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
    m = int.from_bytes(blocco, "big")
    # CRT: m^d mod n
    m1, m2 = pow(m, key["dp"], key["p"]), pow(m, key["dq"], key["q"])
    h = (key["qi"] * (m1 - m2)) % key["p"]
    return (m2 + h * key["q"]).to_bytes(k, "big")


def certificate(key: dict, nomi: List[str], ips: List[str], cn: str, giorni: int = 825) -> bytes:
    adesso = datetime.now(timezone.utc).replace(microsecond=0)
    chiave_pub = _seq(_seq(_oid("1.2.840.113549.1.1.1"), b"\x05\x00"), _tlv(0x03, b"\x00" + _seq(_int(key["n"]), _int(key["e"]))))
    san = b"".join(_tlv(0x82, n.encode("ascii")) for n in nomi) + b"".join(_tlv(0x87, ipaddress.ip_address(i).packed) for i in ips)
    estensioni = _tlv(0xA3, _seq(
        _seq(_oid("2.5.29.17"), _tlv(0x04, _seq(san))),
        _seq(_oid("2.5.29.19"), _tlv(0x01, b"\xff"), _tlv(0x04, _seq())),  # basicConstraints: not a CA
        _seq(_oid("2.5.29.37"), _tlv(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1")))),  # serverAuth
    ))
    tbs = _seq(_tlv(0xA0, _int(2)), _int(secrets.randbits(120) | 1), SHA256_RSA, _name(cn, "Windows Maintenance Manager"),
               _seq(_time(adesso - timedelta(days=1)), _time(adesso + timedelta(days=giorni))), _name(cn, "Windows Maintenance Manager"),
               chiave_pub, estensioni)
    return _seq(tbs, SHA256_RSA, _tlv(0x03, b"\x00" + _sign(key, tbs)))


def private_key_der(key: dict) -> bytes:
    return _seq(_int(0), *[_int(key[k]) for k in ("n", "e", "d", "p", "q", "dp", "dq", "qi")])


def pem(tipo: str, der: bytes) -> str:
    b = base64.b64encode(der).decode()
    return f"-----BEGIN {tipo}-----\n" + "\n".join(b[i:i + 64] for i in range(0, len(b), 64)) + f"\n-----END {tipo}-----\n"


def fingerprint(der: bytes) -> str:
    return ":".join(f"{x:02X}" for x in hashlib.sha256(der).digest())


# ---------- the certificate of this PC ----------

def local_names() -> Tuple[List[str], List[str]]:
    nome = socket.gethostname()
    nomi = sorted({nome, nome.lower(), "localhost"})
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(nome, None, socket.AF_INET):
            ips.add(str(info[4][0]))
    except OSError:
        pass
    return nomi, sorted(ips)


def ensure(data_dir: Path) -> dict:
    """The certificate of this PC (made once, a few seconds), as files for ssl and its fingerprint."""
    cartella = Path(data_dir) / "tls"
    cert, chiave = cartella / "server.crt", cartella / "server.key"
    if not (cert.exists() and chiave.exists()):
        cartella.mkdir(parents=True, exist_ok=True)
        key = rsa_key()
        nomi, ips = local_names()
        der = certificate(key, nomi, ips, socket.gethostname())
        chiave.write_text(pem("RSA PRIVATE KEY", private_key_der(key)), encoding="ascii")
        cert.write_text(pem("CERTIFICATE", der), encoding="ascii")
        _protect_folder(cartella)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    return {"cert": str(cert), "key": str(chiave), "fingerprint": fingerprint(der)}


def _protect_folder(cartella: Path) -> None:
    import os
    import subprocess
    utente = "\\".join(x for x in (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")) if x)
    try:  # administrators, SYSTEM and the account that runs the console
        subprocess.run(["icacls", str(cartella), "/inheritance:r", "/grant:r", "*S-1-5-32-544:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"] + ([f"{utente}:(OI)(CI)F"] if utente else []),
                       capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def server_context(data_dir: Path) -> ssl.SSLContext:
    info = ensure(data_dir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(info["cert"], info["key"])
    return ctx


def wrap(server, data_dir: Path):
    """Turns a running-to-be HTTPServer into an HTTPS one."""
    server.socket = server_context(data_dir).wrap_socket(server.socket, server_side=True)
    return server


def pinned_context(fingerprint_atteso: Optional[str]) -> ssl.SSLContext:
    """A client context that accepts only the certificate with this fingerprint (checked after the handshake)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # the fingerprint below replaces the CA check of a self-signed certificate
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def peer_fingerprint(sock) -> str:
    return fingerprint(sock.getpeercert(binary_form=True))


class PinError(OSError):
    """The server shows another certificate than the one pinned: maybe another machine on the network."""


def pinned_connection(host: str, porta: int, fingerprint_atteso: str, timeout: float = 10):
    """A TLS socket to a server of this app, accepted only when its certificate has the pinned fingerprint."""
    grezzo = socket.create_connection((host, porta), timeout=timeout)
    try:
        sicuro = pinned_context(fingerprint_atteso).wrap_socket(grezzo, server_hostname=host)
    except Exception:
        grezzo.close()
        raise
    trovato = peer_fingerprint(sicuro)
    if fingerprint_atteso and trovato != fingerprint_atteso:
        sicuro.close()
        raise PinError(f"the certificate changed (expected {fingerprint_atteso[:23]}…, found {trovato[:23]}…)")
    return sicuro, trovato
