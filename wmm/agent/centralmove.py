"""Back up, restore and move the central server (2.11) without enrolling the PCs again.

The backup is one file protected by a password: the database (PCs, jobs, groups, assets, catalog, rings, clients), the
server certificate and its key (so the fingerprint the PCs pinned does not change) and the port. The secrets of the PCs
are stored encrypted for this Windows user (DPAPI) and would be unreadable on another PC: in the backup they are
plain, and the whole file is encrypted with the password (PBKDF2-HMAC-SHA256, 300 000 rounds; HMAC-SHA256 keystream;
HMAC-SHA256 seal checked before anything is read). On restore they are encrypted again for the new PC.

Moving to another PC: from the old server send "Move to a new address" to the PCs (they keep the pinned fingerprint
and only change where they call), back up, restore on the new PC. A PC that misses the move can be pointed at the new
address later, or keeps calling the old one until it is switched off."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import shutil
import socket
import sqlite3
import ssl
import tempfile
import zlib
from datetime import datetime
from pathlib import Path

from . import migrations, notify, tlsutil

MAGIC = b"WMMCB1"
ROUNDS = 300_000
FORMAT = "wmm-central/1"
MIN_PASSWORD = 12


class MoveError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _keys(password: str, sale: bytes) -> tuple:
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sale, ROUNDS, dklen=64)
    return k[:32], k[32:]


def _stream(chiave: bytes, nonce: bytes, dati: bytes) -> bytes:
    fuori = bytearray(len(dati))
    for i in range(0, len(dati), 32):
        blocco = hmac.new(chiave, nonce + (i // 32).to_bytes(8, "big"), hashlib.sha256).digest()
        pezzo = dati[i:i + 32]
        n = len(pezzo)
        fuori[i:i + n] = (int.from_bytes(pezzo, "big") ^ int.from_bytes(blocco[:n], "big")).to_bytes(n, "big")
    return bytes(fuori)


def seal(password: str, dati: bytes) -> bytes:
    if len(password or "") < MIN_PASSWORD:
        raise MoveError(f"The backup password needs at least {MIN_PASSWORD} characters.")
    sale, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    k_enc, k_mac = _keys(password, sale)
    cifrato = _stream(k_enc, nonce, zlib.compress(dati, 6))
    testa = MAGIC + sale + nonce
    return testa + cifrato + hmac.new(k_mac, testa + cifrato, hashlib.sha256).digest()


def unseal(password: str, blob: bytes) -> bytes:
    if len(blob) < len(MAGIC) + 64 or not blob.startswith(MAGIC):
        raise MoveError("This is not a backup of the central server.")
    testa, cifrato, sigillo = blob[:len(MAGIC) + 32], blob[len(MAGIC) + 32:-32], blob[-32:]
    sale, nonce = testa[len(MAGIC):len(MAGIC) + 16], testa[len(MAGIC) + 16:]
    k_enc, k_mac = _keys(password or "", sale)
    if not hmac.compare_digest(hmac.new(k_mac, testa + cifrato, hashlib.sha256).digest(), sigillo):
        raise MoveError("Wrong password, or the file is damaged.", 403)
    return zlib.decompress(_stream(k_enc, nonce, cifrato))


def _copy_db(sorgente: Path, destinazione: Path) -> None:
    a, b = sqlite3.connect(sorgente, timeout=30), sqlite3.connect(destinazione)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()


def _secrets(percorso: Path, funzione) -> int:
    """Turns the stored secrets of the PCs and of the enrollment codes with funzione (decrypt or encrypt)."""
    db = sqlite3.connect(percorso)
    n = 0
    try:
        with db:
            for tabella in ("agents", "enroll"):
                for ident, segreto in db.execute(f"SELECT id, secret FROM {tabella}").fetchall():
                    db.execute(f"UPDATE {tabella} SET secret = ? WHERE id = ?", (funzione(segreto), ident))
                    n += 1
    finally:
        db.close()
    return n


def export(data_dir: Path, password: str, port: int) -> bytes:
    """The encrypted backup of the central server of this PC."""
    data_dir = Path(data_dir)
    db_path, tls = data_dir / "central.db", data_dir / "tls"
    if not db_path.exists():
        raise MoveError("This PC has no central server to back up.", 404)
    if not (tls / "server.crt").exists() or not (tls / "server.key").exists():
        raise MoveError("The certificate of the server is missing: turn the central server on once first.", 409)
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "central.db"
        _copy_db(db_path, copia)
        _secrets(copia, notify.unprotect)
        dati = {"format": FORMAT, "created": datetime.now().isoformat(timespec="seconds"), "source": socket.gethostname(), "port": int(port),
                "db": base64.b64encode(copia.read_bytes()).decode("ascii"),
                "cert": (tls / "server.crt").read_text(encoding="ascii"), "key": (tls / "server.key").read_text(encoding="ascii")}
    return seal(password, json.dumps(dati).encode("utf-8"))


def _payload(blob: bytes, password: str) -> dict:
    try:
        dati = json.loads(unseal(password, blob).decode("utf-8"))
    except MoveError:
        raise
    except (ValueError, zlib.error):
        raise MoveError("The backup is damaged.") from None
    if not isinstance(dati, dict) or dati.get("format") != FORMAT or not all(k in dati for k in ("db", "cert", "key", "port")):
        raise MoveError("Unknown backup format.")
    return dati


def _summary(dati: dict, percorso: Path) -> dict:
    db = sqlite3.connect(percorso)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MoveError("The database in the backup is damaged.")
        pcs = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        ha_clienti = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'tenants'").fetchone()
        clienti = db.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] if ha_clienti else 0
    except sqlite3.DatabaseError:
        raise MoveError("The database in the backup is damaged.") from None
    finally:
        db.close()
    return {"created": dati["created"], "source": dati["source"], "port": dati["port"], "agents": pcs, "tenants": clienti,
            "fingerprint": tlsutil.fingerprint(ssl.PEM_cert_to_DER_cert(dati["cert"]))}


def inspect(blob: bytes, password: str) -> dict:
    """What a backup contains, without restoring it."""
    dati = _payload(blob, password)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "c.db"
        p.write_bytes(base64.b64decode(dati["db"]))
        return _summary(dati, p)


def restore(data_dir: Path, blob: bytes, password: str) -> dict:
    """Replaces the central server of this PC with the backup. The database and certificate it replaces are kept in
    dati\\db-backups and dati\\tls\\previous-*. The caller stops the server before and starts it again after."""
    data_dir = Path(data_dir)
    dati = _payload(blob, password)
    db_path, tls = data_dir / "central.db", data_dir / "tls"
    with tempfile.TemporaryDirectory() as tmp:
        nuovo = Path(tmp) / "central.db"
        nuovo.write_bytes(base64.b64decode(dati["db"]))
        info = _summary(dati, nuovo)
        _secrets(nuovo, notify.protect)
        if db_path.exists():
            vecchio = sqlite3.connect(db_path)
            try:
                migrations.backup(vecchio, db_path, "central", int(vecchio.execute("PRAGMA user_version").fetchone()[0]))
            finally:
                vecchio.close()
        _copy_db(nuovo, db_path)  # the backup API writes over the live file consistently, WAL included
    tls.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    for nome in ("server.crt", "server.key"):
        if (tls / nome).exists():
            shutil.copy2(tls / nome, tls / f"previous-{marca}-{nome}")
    (tls / "server.key").write_text(dati["key"], encoding="ascii")
    (tls / "server.crt").write_text(dati["cert"], encoding="ascii")
    tlsutil._protect_folder(tls)
    return dict(info, restored=True)
