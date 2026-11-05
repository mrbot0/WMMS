"""Data at rest encrypted with DPAPI, machine scope (2.10, Settings › Security › Encrypt the data files). The JSON files
with what the app learns about this PC and its network (devices, Wi-Fi and Bluetooth, connection log, suspicious
programs and changes, configuration copies, trends, alerts, paired PCs and phones, integrations) are written
encrypted, readable only on this PC, by the console and by the scheduled runs (SYSTEM). Reading is transparent:
encrypted and plain files are both read, so turning the option on or off never loses data. The two SQLite databases
(history; users and audit) are not encrypted: protect the disk with BitLocker for those."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path
from typing import Iterable, List

MAGIC = b"WMMENC1\n"
FILES = ("network_scan.json", "wifi_scan.json", "wifi_history.json", "bluetooth_scan.json", "connection_history.json", "drift.json",
         "suspicious.json", "health_history.json", "notify_log.json", "fleet.json", "phone.json", "integrations.json", "upnp.json",
         "incidents.json", "goodconfig_last.json")
_CACHE: dict = {"t": 0.0, "on": False}


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dati: bytes, proteggi: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(dati, len(dati))
    ingresso = _Blob(len(dati), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    uscita = _Blob()
    flags = 0x4 | 0x1  # CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN
    if proteggi:
        ok = crypt32.CryptProtectData(ctypes.byref(ingresso), "WMM data", None, None, None, flags, ctypes.byref(uscita))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(ingresso), None, None, None, None, flags, ctypes.byref(uscita))
    if not ok:
        raise OSError("DPAPI could not " + ("encrypt" if proteggi else "decrypt") + " the data")
    try:
        return ctypes.string_at(uscita.pbData, uscita.cbData)
    finally:
        kernel32.LocalFree(uscita.pbData)


def enabled() -> bool:
    """The setting of this PC, read again at most every 30 seconds."""
    if time.time() - _CACHE["t"] > 30:
        try:
            from . import appsettings
            from .watch import DATA_DIR
            _CACHE["on"] = bool(appsettings.load(DATA_DIR).get("encrypt_data"))
        except Exception:  # noqa: BLE001 - when in doubt, plain files as before
            _CACHE["on"] = False
        _CACHE["t"] = time.time()
    return _CACHE["on"]


def set_cached(valore: bool) -> None:
    _CACHE.update(t=time.time(), on=bool(valore))


def decode(dati: bytes, encoding: str = "utf-8") -> str:
    if dati.startswith(MAGIC):
        return _dpapi(dati[len(MAGIC):], False).decode(encoding)
    return dati.decode(encoding)


def read_text(path, encoding: str = "utf-8") -> str:
    """Like Path.read_text, for files that may be encrypted."""
    return decode(Path(path).read_bytes(), encoding)


def write_text(path, testo: str, encoding: str = "utf-8", encrypt=None) -> int:
    """Like Path.write_text; encrypted when the setting is on (or encrypt=True)."""
    dati = testo.encode(encoding)
    if encrypt if encrypt is not None else (enabled() and Path(path).name in FILES):
        dati = MAGIC + _dpapi(dati, True)
    Path(path).write_bytes(dati)
    return len(testo)


def convert(data_dir: Path, cifra: bool, nomi: Iterable[str] = FILES) -> List[str]:
    """Encrypts (or decrypts) the existing data files at once when the setting changes."""
    fatti = []
    for nome in nomi:
        p = Path(data_dir) / nome
        if not p.exists():
            continue
        grezzo = p.read_bytes()
        if grezzo.startswith(MAGIC) == cifra:
            continue
        testo = decode(grezzo)
        write_text(p, testo, encrypt=cifra)
        fatti.append(nome)
    set_cached(cifra)
    return fatti
