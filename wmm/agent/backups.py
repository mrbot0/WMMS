"""Backups (2.13): the Backup tab of Storage.

A backup profile says what to save (folders, with exclusions), where (another disk, a NAS share), how and when:
  copy     only new and changed files are copied; nothing is ever deleted at the destination (robocopy /E)
  mirror   the destination becomes an exact copy: files deleted here are deleted there too (robocopy /MIR)
  archive  every run makes a dated zip (a version) with a manifest; the oldest beyond "keep" are removed; it can be
           encrypted with a password (PBKDF2-SHA256 key, SHAKE-256 keystream, HMAC-SHA256 seal checked before reading)
Versions can be listed, browsed, checked and restored (all files or the chosen ones) into a new folder or back to their
place. Scheduled runs (the tool "Run the backups that are due") run every profile whose daily or weekly turn has come.
The password of an encrypted profile is kept with DPAPI for the machine, so the scheduled run (as SYSTEM) can use it.

Data: dati\\backups.json (profiles), dati\\backup_history.json (the last 500 runs)."""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from . import securestore

PROFILES = "backups.json"
HISTORY = "backup_history.json"
KINDS = ("copy", "mirror", "archive")
FREQUENCIES = ("manual", "daily", "weekly")
MAGIC = b"WMMBK1"
ROUNDS = 200_000
CHUNK = 1 << 20
MAX_PROFILES = 30
MANIFEST = "wmm-manifest.json"
_LOCK = threading.Lock()
RUNNING: Dict[str, dict] = {}  # profile id -> progress of the run in progress


class BackupError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ======================================================================= storage of profiles and history

def _read(path: Path, predefinito):
    try:
        return json.loads(securestore.read_text(path))
    except (OSError, ValueError):
        return predefinito


def _write(path: Path, dati) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(path, json.dumps(dati, indent=1, ensure_ascii=False))


def _raw(data_dir: Path) -> List[dict]:
    dati = _read(Path(data_dir) / PROFILES, [])
    return [p for p in dati if isinstance(p, dict)] if isinstance(dati, list) else []


def _public(p: dict) -> dict:
    d = {k: v for k, v in p.items() if k != "password"}
    d["encrypted"] = p.get("kind") == "archive" and bool(p.get("password"))
    d["has_password"] = bool(p.get("password"))
    return d


def profiles(data_dir: Path) -> List[dict]:
    return [_public(p) for p in _raw(data_dir)]


def _get(data_dir: Path, ident: str) -> dict:
    p = next((p for p in _raw(data_dir) if p.get("id") == ident), None)
    if p is None:
        raise BackupError("Backup not found.", 404)
    return p


def _protect(testo: str) -> str:
    return base64.b64encode(securestore._dpapi(testo.encode("utf-8"), True)).decode("ascii")


def _unprotect(testo: str) -> str:
    return securestore._dpapi(base64.b64decode(testo), False).decode("utf-8")


TARGET = re.compile(r"(?:[A-Za-z]:\\|\\\\[\w.\-]+\\[\w$.\- ]+)[^<>\"|?*]{0,240}")


def _norm(a: str) -> str:
    return os.path.normcase(os.path.abspath(a)).rstrip("\\/")


def _inside(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b + os.sep)


def _protected_roots(data_dir: Optional[Path]) -> List[str]:
    """Folders a backup never reads from, writes to or restores into: Windows, the programs, ProgramData and this app."""
    radici = [os.environ.get(v) for v in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")]
    radici += [str(Path(__file__).resolve().parents[2])]
    if data_dir is not None:
        radici.append(str(data_dir))
    return [r for r in radici if r]


def protected(percorso: str, data_dir: Optional[Path]) -> bool:
    """True for a protected folder, one inside it, or a drive root that contains one (C:\\ holds Windows)."""
    try:
        reale = os.path.realpath(percorso)
    except (OSError, ValueError):
        return True
    for r in _protected_roots(data_dir):
        try:
            radice = os.path.realpath(r)
        except (OSError, ValueError):
            continue
        if _inside(reale, radice) or (_inside(radice, reale) and len(_norm(reale)) <= 3):
            return True
    return False


def clean(dati: dict, vecchio: Optional[dict] = None, data_dir: Optional[Path] = None) -> dict:
    """Checks a profile sent by the console; the password is kept from the old profile unless replaced or cleared.

    Windows, the programs, ProgramData and the data of this app are never saved nor written to (they hold the accounts
    and the protected secrets of the agent, which runs with more rights than the person using the console)."""
    if not isinstance(dati, dict):
        raise BackupError("A backup profile.")
    nome = str(dati.get("name", "")).strip()
    if not 1 <= len(nome) <= 60:
        raise BackupError("Name: 1-60 characters.")
    sorgenti = dati.get("sources")
    if not isinstance(sorgenti, list) or not 1 <= len(sorgenti) <= 20 or not all(isinstance(s, str) and s.strip() for s in sorgenti):
        raise BackupError("Choose from 1 to 20 folders to save.")
    sorgenti = [s.strip() for s in sorgenti]
    sorgenti = [s if re.fullmatch(r"[A-Za-z]:\\?", s) else s.rstrip("\\/") for s in sorgenti]
    for s in sorgenti:
        if not os.path.isabs(s) or not os.path.isdir(s):
            raise BackupError(f"This folder does not exist: {s}")
    target = str(dati.get("target", "")).strip()
    if not TARGET.fullmatch(target):
        raise BackupError("The destination is a folder on another disk (E:\\Backup) or on a NAS (\\\\nas\\share).")
    for s in sorgenti:
        if _inside(target, s) or _inside(s, target):
            raise BackupError("The destination cannot be inside a saved folder, nor the other way round.")
    for percorso in sorgenti + [target]:
        if protected(percorso, data_dir):
            raise BackupError(f"Windows, the programs and the data of this app cannot be saved nor used as destination: {percorso}")
    esclusi = dati.get("exclude") or []
    if isinstance(esclusi, str):
        esclusi = [e for e in esclusi.splitlines() if e.strip()]
    if not isinstance(esclusi, list) or len(esclusi) > 50 or any(not isinstance(e, str) or not re.fullmatch(r"[^\\/:<>\"|]{1,100}", e.strip()) for e in esclusi):
        raise BackupError("Exclusions: names or patterns such as *.tmp or node_modules, one per line.")
    tipo = dati.get("kind", "copy")
    if tipo not in KINDS:
        raise BackupError("Kind: copy, mirror or archive.")
    freq = dati.get("frequency", "manual")
    if freq not in FREQUENCIES:
        raise BackupError("Frequency: manual, daily or weekly.")
    tieni = dati.get("keep", 10)
    if isinstance(tieni, bool) or not isinstance(tieni, int) or not 1 <= tieni <= 365:
        raise BackupError("Versions to keep: from 1 to 365.")
    p = {"id": (vecchio or {}).get("id") or "b" + secrets.token_hex(5), "name": nome, "sources": sorgenti, "exclude": [e.strip() for e in esclusi],
         "target": target, "kind": tipo, "keep": tieni, "frequency": freq, "enabled": bool(dati.get("enabled", True)),
         "created": (vecchio or {}).get("created") or now(), "updated": now()}
    password = dati.get("password")
    if isinstance(password, str) and password:
        if len(password) < 8:
            raise BackupError("The password of the archives needs at least 8 characters.")
        p["password"] = _protect(password)
    elif not dati.get("clear_password") and (vecchio or {}).get("password"):
        p["password"] = (vecchio or {})["password"]
    return p


def save(data_dir: Path, dati: dict, ident: Optional[str] = None) -> dict:
    with _LOCK:
        elenco = _raw(data_dir)
        if ident:
            vecchio = next((p for p in elenco if p.get("id") == ident), None)
            if vecchio is None:
                raise BackupError("Backup not found.", 404)
            nuovo = clean(dati, vecchio, data_dir)
            elenco = [nuovo if p.get("id") == ident else p for p in elenco]
        else:
            if len(elenco) >= MAX_PROFILES:
                raise BackupError(f"Up to {MAX_PROFILES} backups.")
            nuovo = clean(dati, data_dir=data_dir)
            elenco.append(nuovo)
        _write(Path(data_dir) / PROFILES, elenco)
    return _public(nuovo)


def delete(data_dir: Path, ident: str) -> None:
    """Removes the profile only: the backups already made stay at the destination."""
    with _LOCK:
        elenco = _raw(data_dir)
        if not any(p.get("id") == ident for p in elenco):
            raise BackupError("Backup not found.", 404)
        if ident in RUNNING:
            raise BackupError("This backup is running: wait for it to finish.", 409)
        _write(Path(data_dir) / PROFILES, [p for p in elenco if p.get("id") != ident])


def history(data_dir: Path, ident: Optional[str] = None, limite: int = 100) -> List[dict]:
    dati = _read(Path(data_dir) / HISTORY, [])
    voci = [h for h in dati if isinstance(h, dict) and (not ident or h.get("profile") == ident)] if isinstance(dati, list) else []
    return list(reversed(voci))[:limite]


def _record(data_dir: Path, voce: dict) -> None:
    with _LOCK:
        dati = _read(Path(data_dir) / HISTORY, [])
        voci = [h for h in dati if isinstance(h, dict)] if isinstance(dati, list) else []
        _write(Path(data_dir) / HISTORY, (voci + [voce])[-500:])


# ======================================================================= files to save

def folder(p: dict) -> Path:
    """Where a profile writes: <destination>\\<this PC>\\<name of the profile>."""
    sicuro = re.sub(r"[^\w\- ]", "_", p["name"]).strip() or p["id"]
    return Path(p["target"]) / re.sub(r"[^\w\-]", "_", socket.gethostname()) / sicuro


def _labels(sorgenti: List[str]) -> List[str]:
    """A folder name for every source inside the backup (Documents, Documents-2…)."""
    usati: Dict[str, int] = {}
    fuori = []
    for s in sorgenti:
        base = re.sub(r"[^\w\- .]", "_", Path(s).name or s.replace(":", "").strip("\\/")) or "folder"
        usati[base] = usati.get(base, 0) + 1
        fuori.append(base if usati[base] == 1 else f"{base}-{usati[base]}")
    return fuori


def _excluded(nome: str, esclusi: List[str]) -> bool:
    return any(fnmatch.fnmatch(nome.lower(), e.lower()) for e in esclusi)


def iter_files(sorgenti: List[str], esclusi: List[str]) -> Iterator[Tuple[str, str]]:
    """(absolute path, path inside the backup) of every file to save, without excluded names and links."""
    for etichetta, radice in zip(_labels(sorgenti), sorgenti):
        for cartella, dirs, files in os.walk(radice):
            dirs[:] = [d for d in dirs if not _excluded(d, esclusi) and not os.path.islink(os.path.join(cartella, d))]
            for f in files:
                if _excluded(f, esclusi):
                    continue
                pieno = os.path.join(cartella, f)
                if os.path.islink(pieno):
                    continue
                rel = os.path.relpath(pieno, radice).replace("\\", "/")
                yield pieno, f"{etichetta}/{rel}"


def estimate(data_dir: Path, ident: str, limite_secondi: float = 15.0) -> dict:
    """How much the profile saves and how much room the destination has."""
    p = _get(data_dir, ident)
    fine = time.monotonic() + limite_secondi
    n, tot, troncato = 0, 0, False
    for pieno, _ in iter_files(p["sources"], p.get("exclude") or []):
        try:
            tot += os.path.getsize(pieno)
        except OSError:
            continue
        n += 1
        if time.monotonic() > fine:
            troncato = True
            break
    try:
        libero: Optional[int] = shutil.disk_usage(p["target"]).free
    except OSError:
        libero = None
    return {"files": n, "bytes": tot, "truncated": troncato, "target_free": libero, "target_ok": libero is not None,
            "fits": None if libero is None else tot < libero}


# ======================================================================= encrypted archives (streamed)

def _keys(password: str, sale: bytes) -> Tuple[bytes, bytes]:
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sale, ROUNDS, dklen=64)
    return k[:32], k[32:]


def _xor(chiave: bytes, nonce: bytes, indice: int, dati: bytes) -> bytes:
    flusso = hashlib.shake_256(chiave + nonce + indice.to_bytes(8, "big")).digest(len(dati))
    return (int.from_bytes(dati, "big") ^ int.from_bytes(flusso, "big")).to_bytes(len(dati), "big")


def encrypt_file(sorgente: Path, destinazione: Path, password: str) -> None:
    sale, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    k_enc, k_mac = _keys(password, sale)
    testa = MAGIC + sale + nonce
    sigillo = hmac.new(k_mac, testa, hashlib.sha256)
    with open(sorgente, "rb") as src, open(destinazione, "wb") as dst:
        dst.write(testa)
        i = 0
        for pezzo in iter(lambda: src.read(CHUNK), b""):
            c = _xor(k_enc, nonce, i, pezzo)
            sigillo.update(c)
            dst.write(c)
            i += 1
        dst.write(sigillo.digest())


def decrypt_file(sorgente: Path, destinazione: Path, password: str) -> None:
    """Checks the seal over the whole file first, then decrypts: a wrong password or a changed byte writes nothing."""
    dim = os.path.getsize(sorgente)
    with open(sorgente, "rb") as src:
        testa = src.read(len(MAGIC) + 32)
        if not testa.startswith(MAGIC) or dim < len(testa) + 32:
            raise BackupError("This is not an encrypted backup of this app.")
        sale, nonce = testa[len(MAGIC):len(MAGIC) + 16], testa[len(MAGIC) + 16:]
        k_enc, k_mac = _keys(password, sale)
        sigillo = hmac.new(k_mac, testa, hashlib.sha256)
        resto = dim - len(testa) - 32
        letti = 0
        while letti < resto:
            pezzo = src.read(min(CHUNK, resto - letti))
            sigillo.update(pezzo)
            letti += len(pezzo)
        if not hmac.compare_digest(sigillo.digest(), src.read(32)):
            raise BackupError("Wrong password, or the archive is damaged.", 403)
        src.seek(len(testa))
        with open(destinazione, "wb") as dst:
            letti, i = 0, 0
            while letti < resto:
                pezzo = src.read(min(CHUNK, resto - letti))
                dst.write(_xor(k_enc, nonce, i, pezzo))
                letti += len(pezzo)
                i += 1


# ======================================================================= running a backup

ROBOCOPY_LINE = re.compile(r"^\s*(Files|Bytes|File|Byte)\s*:\s*(.+)$", re.I)


def parse_robocopy(testo: str) -> dict:
    """The summary of robocopy (with /BYTES): Total, Copied, Skipped, Mismatch, FAILED, Extras for files and bytes."""
    fuori = {"files_copied": 0, "files_failed": 0, "bytes_copied": 0, "files_total": 0}
    for riga in testo.splitlines():
        m = ROBOCOPY_LINE.match(riga)
        if not m:
            continue
        valori = [int(x) for x in re.findall(r"\d+", m.group(2))]
        if len(valori) < 5:
            continue
        if m.group(1).lower().startswith("file"):
            fuori["files_total"] += valori[0]
            fuori["files_copied"] += valori[1]
            fuori["files_failed"] += valori[4]
        else:
            fuori["bytes_copied"] += valori[1]
    return fuori


def _robocopy(p: dict, preview: bool, runner) -> dict:
    base = folder(p)
    tot: dict = {"files": 0, "bytes": 0, "errors": []}
    for etichetta, sorgente in zip(_labels(p["sources"]), p["sources"]):
        cmd = ["robocopy", sorgente, str(base / etichetta), "/MIR" if p["kind"] == "mirror" else "/E", "/XJ", "/R:1", "/W:1", "/MT:8", "/NP",
               "/NDL", "/NFL", "/BYTES"]
        if p.get("exclude"):
            cmd += ["/XF", *p["exclude"], "/XD", *p["exclude"]]
        if preview:
            cmd.append("/L")  # list only: nothing is copied or deleted
        try:
            r = runner(cmd, capture_output=True, text=True, timeout=6 * 3600, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            tot["errors"].append(f"{sorgente}: {e}")
            continue
        s = parse_robocopy(r.stdout or "")
        tot["files"] += s["files_copied"]
        tot["bytes"] += s["bytes_copied"]
        if r.returncode >= 8 or s["files_failed"]:
            tot["errors"].append(f"{sorgente}: {s['files_failed']} files could not be copied (robocopy {r.returncode})")
    return tot


def _archive(p: dict, preview: bool, progress: Optional[Callable[[int, int], None]]) -> dict:
    base = folder(p)
    nome = datetime.now().strftime("%Y%m%d-%H%M%S")
    password = _unprotect(p["password"]) if p.get("password") else ""
    elenco = list(iter_files(p["sources"], p.get("exclude") or []))
    if preview:
        dim = 0
        for f, _ in elenco:
            try:
                dim += os.path.getsize(f)
            except OSError:
                pass
        return {"files": len(elenco), "bytes": dim, "errors": [], "version": None}
    base.mkdir(parents=True, exist_ok=True)
    parziale = base / (nome + ".part")
    manifest, errori, scritti, byte = [], [], 0, 0
    try:
        with zipfile.ZipFile(parziale, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            for i, (pieno, rel) in enumerate(elenco):
                try:
                    st = os.stat(pieno)
                    z.write(pieno, rel)
                    manifest.append({"path": rel, "size": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
                    scritti += 1
                    byte += st.st_size
                except OSError as e:  # open in another program, no permission
                    errori.append(f"{pieno}: {e.strerror or e}")
                if progress and i % 25 == 0:
                    progress(i, len(elenco))
            z.writestr(MANIFEST, json.dumps({"profile": p["name"], "created": now(), "pc": socket.gethostname(), "sources": p["sources"],
                                             "files": manifest}, ensure_ascii=False))
        if password:
            finale = base / (nome + ".wmmbak")
            encrypt_file(parziale, finale, password)
            parziale.unlink()
        else:
            finale = base / (nome + ".zip")
            parziale.replace(finale)
    finally:
        if parziale.exists():
            try:
                parziale.unlink()
            except OSError:
                pass
    _retain(p)
    return {"files": scritti, "bytes": byte, "errors": errori, "version": finale.name}


def _retain(p: dict) -> List[str]:
    """Removes the oldest versions beyond the number to keep."""
    tolte = []
    for v in versions(p)[p["keep"]:]:
        try:
            (folder(p) / v["name"]).unlink()
            tolte.append(v["name"])
        except OSError:
            pass
    return tolte


def run(data_dir: Path, ident: str, preview: bool = False, runner=subprocess.run) -> dict:
    """Runs one backup now; one at a time per profile. The result goes into the history (not for a preview)."""
    p = _get(data_dir, ident)
    with _LOCK:
        if ident in RUNNING:
            raise BackupError("This backup is already running.", 409)
        RUNNING[ident] = {"started": now(), "done": 0, "total": 0}
    inizio = now()
    try:
        if not preview:
            try:
                folder(p).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if not preview and not folder(p).is_dir():
            esito: dict = {"files": 0, "bytes": 0, "errors": [f"{p['target']} is not reachable: connect the disk or the NAS."], "version": None}
        else:
            def avanza(fatti: int, totale: int) -> None:
                RUNNING[ident].update(done=fatti, total=totale)
            try:
                esito = _archive(p, preview, avanza) if p["kind"] == "archive" else dict(_robocopy(p, preview, runner), version=None)
            except Exception as e:  # noqa: BLE001 - recorded as a failed run
                esito = {"files": 0, "bytes": 0, "errors": [str(e)[:300]], "version": None}
    finally:
        RUNNING.pop(ident, None)
    voce = {"profile": ident, "name": p["name"], "kind": p["kind"], "started": inizio, "finished": now(), "ok": not esito["errors"],
            "files": esito["files"], "bytes": esito["bytes"], "errors": esito["errors"][:20], "version": esito.get("version"), "preview": preview}
    if not preview:
        _record(data_dir, voce)
    return voce


def run_async(data_dir: Path, ident: str, preview: bool = False) -> dict:
    p = _get(data_dir, ident)
    if ident in RUNNING:
        raise BackupError("This backup is already running.", 409)

    def lavora() -> None:
        try:
            run(data_dir, ident, preview)
        except BackupError:
            pass
    threading.Thread(target=lavora, name="wmm-backup-" + ident, daemon=True).start()
    return {"started": True, "profile": ident, "name": p["name"], "preview": preview}


def due(data_dir: Path, adesso: Optional[datetime] = None) -> List[dict]:
    """Profiles whose daily or weekly turn has come (since their last successful run)."""
    adesso = adesso or datetime.now()
    ultimi: Dict[str, str] = {}
    for h in history(data_dir, limite=500):
        if h.get("ok") and h.get("profile") not in ultimi:
            ultimi[h["profile"]] = h["finished"]
    fuori = []
    for p in _raw(data_dir):
        if not p.get("enabled") or p.get("frequency") not in ("daily", "weekly"):
            continue
        passo = timedelta(hours=20) if p["frequency"] == "daily" else timedelta(days=6, hours=12)
        ultimo = ultimi.get(p["id"])
        try:
            if ultimo is None or adesso - datetime.fromisoformat(ultimo) >= passo:
                fuori.append(p)
        except ValueError:
            fuori.append(p)
    return fuori


def run_due(ctx, data_dir: Optional[Path] = None):
    """The tool: runs the backups that are due (schedule it every hour or when the PC is idle)."""
    from ottimizza_pc import Esito, Stato
    from .watch import DATA_DIR
    cartella = Path(data_dir or DATA_DIR)
    da_fare = due(cartella)
    if not da_fare:
        return Esito(Stato.OK, "No backup is due.")
    falliti = []
    for p in da_fare:
        ctx.scrivi(f"Backup {p['name']}…")
        try:
            r = run(cartella, p["id"], preview=ctx.anteprima)
        except BackupError as e:
            ctx.scrivi(f"  {e}")
            continue
        ctx.scrivi(f"  {r['files']} files, {r['bytes'] // 1048576} MB" + (f", {len(r['errors'])} problems" if r["errors"] else ""))
        if not r["ok"]:
            falliti.append(p["name"])
    fatti = len(da_fare) - len(falliti)
    return Esito(Stato.AVVISO if falliti else Stato.OK, f"{fatti} backups done" + (f", failed: {', '.join(falliti)}" if falliti else ""))


# ======================================================================= versions, browse, restore, verify

VERSION = re.compile(r"\d{8}-\d{6}\.(zip|wmmbak)")


def versions(p: dict) -> List[dict]:
    base = folder(p)
    if p.get("kind") != "archive" or not base.is_dir():
        return []
    fuori: List[dict] = []
    for f in base.iterdir():
        if f.is_file() and VERSION.fullmatch(f.name):
            fuori.append({"name": f.name, "size": f.stat().st_size, "created": datetime.strptime(f.stem, "%Y%m%d-%H%M%S").isoformat(timespec="seconds"),
                          "encrypted": f.suffix.lower() == ".wmmbak"})
    fuori.sort(key=lambda v: v["name"], reverse=True)
    return fuori


def list_versions(data_dir: Path, ident: str) -> List[dict]:
    return versions(_get(data_dir, ident))


def delete_version(data_dir: Path, ident: str, nome: str) -> None:
    (_version_path(_get(data_dir, ident), nome)).unlink()


def _version_path(p: dict, nome: str) -> Path:
    if not VERSION.fullmatch(nome or ""):
        raise BackupError("Unknown version.", 404)
    percorso = folder(p) / nome
    if not percorso.is_file():
        raise BackupError("This version is not at the destination anymore.", 404)
    return percorso


class _Opened:
    """The zip of a version, decrypted into a temporary file when it is encrypted."""

    def __init__(self, p: dict, nome: str, password: Optional[str]):
        self.path = _version_path(p, nome)
        self.temp: Optional[str] = None
        if self.path.suffix.lower() == ".wmmbak":
            chiave = password or (_unprotect(p["password"]) if p.get("password") else "")
            if not chiave:
                raise BackupError("This version is encrypted: type its password.", 403)
            fd, self.temp = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            try:
                decrypt_file(self.path, Path(self.temp), chiave)
            except BaseException:
                os.unlink(self.temp)
                raise

    def __enter__(self) -> zipfile.ZipFile:
        try:
            self.zip = zipfile.ZipFile(self.temp or self.path)
        except zipfile.BadZipFile:
            self._clean()
            raise BackupError("The archive is damaged.")
        return self.zip

    def _clean(self) -> None:
        if self.temp:
            try:
                os.unlink(self.temp)
            except OSError:
                pass

    def __exit__(self, *a) -> None:
        self.zip.close()
        self._clean()


def files(data_dir: Path, ident: str, nome: str, password: Optional[str] = None, limite: int = 20000) -> dict:
    p = _get(data_dir, ident)
    if p["kind"] != "archive":
        raise BackupError("Only archive backups have versions to browse.")
    with _Opened(p, nome, password) as z:
        try:
            m = json.loads(z.read(MANIFEST))
            elenco = m.get("files") or []
        except (KeyError, ValueError):
            elenco = [{"path": i.filename, "size": i.file_size, "mtime": None} for i in z.infolist() if not i.is_dir()]
    return {"version": nome, "files": elenco[:limite], "count": len(elenco), "bytes": sum(f.get("size") or 0 for f in elenco)}


def _safe_target(dest: Path, rel: str) -> Path:
    obiettivo = (dest / rel).resolve()
    if not _inside(str(obiettivo), str(dest.resolve())):
        raise BackupError("A file of the archive points outside the restore folder.")
    return obiettivo


def original_place(sorgenti: List[str], rel: str, consentite: Optional[set] = None) -> Optional[Path]:
    """Where a file of the archive came from: its source folder (as written in the archive) and its path inside it."""
    etichetta, _, resto = rel.partition("/")
    for e, s in zip(_labels(sorgenti), sorgenti):
        if e == etichetta and resto and (consentite is None or _norm(s) in consentite):
            radice = Path(s)
            obiettivo = (radice / resto).resolve()
            return obiettivo if _inside(str(obiettivo), str(radice.resolve())) else None
    return None


def restore(data_dir: Path, ident: str, nome: Optional[str] = None, dest: Optional[str] = None, scelti: Optional[List[str]] = None,
            password: Optional[str] = None, sovrascrivi: bool = False, preview: bool = False, runner=subprocess.run) -> dict:
    """Restores a version (all files or the chosen ones) into a folder, or back to their original place (dest None).

    An existing file is kept unless sovrascrivi is true."""
    p = _get(data_dir, ident)
    if dest is not None:
        dest = str(dest).strip()
        if not TARGET.fullmatch(dest) or not os.path.isabs(dest):
            raise BackupError("The restore folder is a full path, such as D:\\Restored.")
        if _inside(dest, str(folder(p))):
            raise BackupError("Restore into another folder, not inside the backup itself.")
        if protected(dest, Path(data_dir)):
            raise BackupError(f"Windows, the programs and the data of this app cannot be saved nor used as destination: {dest}")
    ripristinati, saltati, errori = 0, 0, []
    if p["kind"] != "archive":
        if scelti:
            raise BackupError("Choosing files works with archive backups; copy and mirror backups are plain folders you can open.")
        base = folder(p)
        for etichetta, sorgente in zip(_labels(p["sources"]), p["sources"]):
            arrivo = Path(dest) / etichetta if dest else Path(sorgente)
            cmd = ["robocopy", str(base / etichetta), str(arrivo), "/E", "/XJ", "/R:1", "/W:1", "/NP", "/NDL", "/NFL", "/BYTES"]
            if not sovrascrivi:
                cmd += ["/XC", "/XN", "/XO"]  # keep every file already there
            if preview:
                cmd.append("/L")
            try:
                r = runner(cmd, capture_output=True, text=True, timeout=6 * 3600, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError) as e:
                errori.append(f"{sorgente}: {e}")
                continue
            s = parse_robocopy(r.stdout or "")
            ripristinati += s["files_copied"]
            if r.returncode >= 8:
                errori.append(f"{sorgente}: robocopy {r.returncode}")
        return {"restored": ripristinati, "skipped": 0, "errors": errori, "dest": dest or "original place", "preview": preview}
    voluti = set(scelti or [])
    with _Opened(p, nome or "", password) as z:
        try:
            origine = json.loads(z.read(MANIFEST)).get("sources")
        except (KeyError, ValueError):
            origine = None
        if not isinstance(origine, list) or not all(isinstance(s, str) for s in origine):
            origine = []  # no manifest: the files can only go into a new folder
        # An archive at the destination can be replaced by anyone who can write there: back in place only into folders
        # this profile saves now, never where the archive alone says.
        consentite = {_norm(s) for s in p["sources"]}
        for info in z.infolist():
            if info.is_dir() or info.filename == MANIFEST or (voluti and info.filename not in voluti):
                continue
            obiettivo = _safe_target(Path(dest), info.filename) if dest else original_place(origine, info.filename, consentite)
            if obiettivo is None or (not dest and protected(str(obiettivo), Path(data_dir))):
                saltati += 1
                continue
            if obiettivo.exists() and not sovrascrivi:
                saltati += 1
                continue
            if preview:
                ripristinati += 1
                continue
            try:
                obiettivo.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(obiettivo, "wb") as out:
                    shutil.copyfileobj(src, out, CHUNK)
                ripristinati += 1
            except OSError as e:
                errori.append(f"{info.filename}: {e.strerror or e}")
    return {"restored": ripristinati, "skipped": saltati, "errors": errori[:20], "dest": dest or "original place", "preview": preview}


def verify(data_dir: Path, ident: str, nome: Optional[str] = None, password: Optional[str] = None) -> dict:
    """Archive: every file is read back and its CRC checked, and the manifest matches. Copy and mirror: the files of
    the sources are found at the destination with the same size."""
    p = _get(data_dir, ident)
    if p["kind"] == "archive":
        elenco = versions(p)
        if not elenco:
            return {"ok": False, "files": 0, "detail": "No version to check yet."}
        nome = nome or elenco[0]["name"]
        with _Opened(p, nome, password) as z:
            rotto = z.testzip()
            try:
                attesi = len(json.loads(z.read(MANIFEST)).get("files") or [])
            except (KeyError, ValueError):
                attesi = -1
            presenti = sum(1 for i in z.infolist() if not i.is_dir() and i.filename != MANIFEST)
        ok = rotto is None and attesi in (-1, presenti)
        dettaglio = f"{presenti} files read back without errors." if ok else (f"Damaged file: {rotto}" if rotto else f"{attesi} files expected, {presenti} found.")
        return {"ok": ok, "version": nome, "files": presenti, "detail": dettaglio}
    base = folder(p)
    mancanti, diversi, controllati = [], 0, 0
    for pieno, rel in iter_files(p["sources"], p.get("exclude") or []):
        controllati += 1
        copia = base / rel.replace("/", os.sep)
        try:
            if not copia.exists():
                mancanti.append(rel)
            elif copia.stat().st_size != os.path.getsize(pieno):
                diversi += 1
        except OSError:
            continue
        if controllati >= 20000:
            break
    ok = not mancanti and not diversi
    return {"ok": ok, "files": controllati, "missing": mancanti[:50], "different": diversi,
            "detail": f"{controllati} files found at the destination." if ok else f"{len(mancanti)} files missing and {diversi} different: run the backup again."}


def summary(data_dir: Path) -> dict:
    """The Backup tab: profiles with their last run, versions and whether they are running."""
    storia = history(data_dir, limite=500)
    fuori = []
    for p in _raw(data_dir):
        ultimo = next((h for h in storia if h.get("profile") == p["id"]), None)
        ultimo_ok = next((h for h in storia if h.get("profile") == p["id"] and h.get("ok")), None)
        try:
            vv = versions(p)
        except OSError:
            vv = []
        fuori.append(dict(_public(p), last=ultimo, last_ok=ultimo_ok, versions=len(vv), versions_bytes=sum(v["size"] for v in vv),
                          running=RUNNING.get(p["id"]), folder=str(folder(p))))
    falliti = sum(1 for x in fuori if x["last"] and not x["last"]["ok"])
    return {"profiles": fuori, "history": storia[:50], "due": [p["id"] for p in due(data_dir)], "failed": falliti,
            "running": len(RUNNING)}
