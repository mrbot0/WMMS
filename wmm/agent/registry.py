"""Registry browser and editor (winreg, stdlib only).

Every change is preceded by a .reg backup of the key it touches (restorable from the console), and the
keys Windows cannot boot or sign in without refuse deletion."""
from __future__ import annotations

import os
import re
import subprocess
import time
import winreg
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOTS: Dict[str, Tuple[str, int]] = {
    "HKEY_LOCAL_MACHINE": ("HKLM", winreg.HKEY_LOCAL_MACHINE), "HKLM": ("HKLM", winreg.HKEY_LOCAL_MACHINE),
    "HKEY_CURRENT_USER": ("HKCU", winreg.HKEY_CURRENT_USER), "HKCU": ("HKCU", winreg.HKEY_CURRENT_USER),
    "HKEY_CLASSES_ROOT": ("HKCR", winreg.HKEY_CLASSES_ROOT), "HKCR": ("HKCR", winreg.HKEY_CLASSES_ROOT),
    "HKEY_USERS": ("HKU", winreg.HKEY_USERS), "HKU": ("HKU", winreg.HKEY_USERS),
    "HKEY_CURRENT_CONFIG": ("HKCC", winreg.HKEY_CURRENT_CONFIG), "HKCC": ("HKCC", winreg.HKEY_CURRENT_CONFIG),
}
ROOT_NAMES = {"HKLM": "HKEY_LOCAL_MACHINE", "HKCU": "HKEY_CURRENT_USER", "HKCR": "HKEY_CLASSES_ROOT", "HKU": "HKEY_USERS",
              "HKCC": "HKEY_CURRENT_CONFIG"}
TYPES = {winreg.REG_SZ: "REG_SZ", winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ", winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
         winreg.REG_DWORD: "REG_DWORD", winreg.REG_QWORD: "REG_QWORD", winreg.REG_BINARY: "REG_BINARY", winreg.REG_NONE: "REG_NONE"}
TYPE_CODES = {v: k for k, v in TYPES.items()}
VIEW = winreg.KEY_WOW64_64KEY
MAX_SUBKEYS = 5000
MAX_VALUES = 2000
MAX_BINARY = 64 * 1024
# These keys cannot be deleted (their values can still be edited, with a backup).
PROTECTED_KEYS = frozenset(k.lower() for k in (
    r"HKLM\SYSTEM", r"HKLM\SYSTEM\CurrentControlSet", r"HKLM\SYSTEM\Setup", r"HKLM\SOFTWARE", r"HKLM\SOFTWARE\Microsoft",
    r"HKLM\SOFTWARE\Microsoft\Windows", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion", r"HKLM\SOFTWARE\Microsoft\Windows NT",
    r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion", r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
    r"HKLM\SOFTWARE\Policies", r"HKLM\SOFTWARE\Classes", r"HKLM\SOFTWARE\WOW6432Node", r"HKCU\Software", r"HKCU\Software\Microsoft",
    r"HKCU\Software\Microsoft\Windows", r"HKCU\Software\Microsoft\Windows\CurrentVersion", r"HKCU\Software\Classes",
    r"HKCU\Control Panel", r"HKCU\Environment",
))
# Nothing below these can be deleted: drivers, boot configuration, accounts and hardware.
PROTECTED_TREES = tuple(k.lower() + "\\" for k in (
    r"HKLM\SYSTEM\CurrentControlSet\Control", r"HKLM\SYSTEM\CurrentControlSet\Services", r"HKLM\SYSTEM\CurrentControlSet\Enum",
    r"HKLM\SYSTEM\ControlSet001", r"HKLM\SYSTEM\ControlSet002", r"HKLM\SYSTEM\Select", r"HKLM\SAM", r"HKLM\SECURITY",
    r"HKLM\BCD00000000", r"HKLM\HARDWARE",
))
BACKUP_NAME = re.compile(r"^\d{8}-\d{6}-\d{3}-[\w.-]{1,80}\.reg$")


class RegistryError(ValueError):
    """Bad path, protected key or refused change."""


def parse_path(path: str) -> Tuple[str, int, str]:
    """'HKLM\\SOFTWARE\\x' (or the long root name, or with 'Computer\\') -> ('HKLM', handle, 'SOFTWARE\\x')."""
    testo = (path or "").strip().strip("\\").replace("/", "\\")
    if testo.lower().startswith("computer\\"):
        testo = testo[len("computer\\"):]
    radice, _, sotto = testo.partition("\\")
    if radice.upper() not in ROOTS:
        raise RegistryError("The path must start with HKLM, HKCU, HKCR, HKU or HKCC.")
    if "\\\\" in sotto or len(sotto) > 1024:
        raise RegistryError("Invalid key path.")
    breve, handle = ROOTS[radice.upper()]
    return breve, handle, sotto


def full(breve: str, sotto: str) -> str:
    return breve + ("\\" + sotto if sotto else "")


def _filetime(valore: int) -> Optional[str]:
    if not valore:
        return None
    return (datetime(1601, 1, 1) + timedelta(microseconds=valore // 10)).isoformat(timespec="seconds") + "Z"


def render(tipo: int, dati) -> Tuple[str, object]:
    """(text shown in the list, value the edit form starts from)."""
    if tipo in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        return str(dati), str(dati)
    if tipo == winreg.REG_MULTI_SZ:
        elenco = list(dati or [])
        return " · ".join(elenco), elenco
    if tipo in (winreg.REG_DWORD, winreg.REG_QWORD):
        numero = int(dati or 0)
        return f"0x{numero:0{8 if tipo == winreg.REG_DWORD else 16}x} ({numero})", numero
    if isinstance(dati, (bytes, bytearray)):
        esadecimale = bytes(dati[:MAX_BINARY]).hex(" ")
        return (esadecimale[:300] + (" …" if len(esadecimale) > 300 else "")), esadecimale
    return ("" if dati is None else str(dati)), ("" if dati is None else str(dati))


def is_protected(percorso: str) -> bool:
    """True for hive roots, first-level keys, the listed keys and everything under the protected trees."""
    breve, _, sotto = parse_path(percorso)
    testo = full(breve, sotto).lower()
    return not sotto or "\\" not in sotto or testo in PROTECTED_KEYS or (testo + "\\").startswith(PROTECTED_TREES)


def list_key(path: str) -> dict:
    if not (path or "").strip():
        return {"path": "", "subkeys": [{"name": n, "path": n} for n in ROOT_NAMES], "values": [], "roots": True}
    breve, handle, sotto = parse_path(path)
    try:
        chiave = winreg.OpenKey(handle, sotto, 0, winreg.KEY_READ | VIEW)
    except FileNotFoundError:
        raise RegistryError("The key does not exist.") from None
    except PermissionError:
        raise RegistryError("Windows denies reading this key (it belongs to the system).") from None
    with chiave:
        n_sotto, n_valori, scrittura = winreg.QueryInfoKey(chiave)
        sottochiavi = []
        for i in range(min(n_sotto, MAX_SUBKEYS)):
            try:
                sottochiavi.append(winreg.EnumKey(chiave, i))
            except OSError:
                break
        valori = []
        for i in range(min(n_valori, MAX_VALUES)):
            try:
                nome, dati, tipo = winreg.EnumValue(chiave, i)
            except OSError:
                break
            testo, modifica = render(tipo, dati)
            valori.append({"name": nome, "type": TYPES.get(tipo, f"REG_{tipo}"), "display": testo, "data": modifica,
                           "editable": tipo in TYPES and tipo != winreg.REG_NONE and
                           (not isinstance(dati, (bytes, bytearray)) or len(dati) <= MAX_BINARY)})
    percorso = full(breve, sotto)
    return {"path": percorso, "long_path": full(ROOT_NAMES[breve], sotto),
            "subkeys": [{"name": n, "path": percorso + "\\" + n} for n in sorted(sottochiavi, key=str.lower)],
            "values": sorted(valori, key=lambda v: (v["name"] != "", v["name"].lower())),
            "counts": {"subkeys": n_sotto, "values": n_valori}, "truncated": n_sotto > MAX_SUBKEYS or n_valori > MAX_VALUES,
            "modified": _filetime(scrittura), "protected": is_protected(percorso)}


def convert(tipo: str, dati) -> Tuple[int, object]:
    if tipo not in TYPE_CODES or tipo == "REG_NONE":
        raise RegistryError("Unsupported value type.")
    codice = TYPE_CODES[tipo]
    if codice in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        return codice, str(dati if dati is not None else "")
    if codice == winreg.REG_MULTI_SZ:
        elenco = dati if isinstance(dati, list) else str(dati or "").split("\n")
        return codice, [str(x).rstrip("\r") for x in elenco]
    if codice in (winreg.REG_DWORD, winreg.REG_QWORD):
        bit = 32 if codice == winreg.REG_DWORD else 64
        try:
            numero = int(str(dati).strip(), 0) if isinstance(dati, str) else int(dati)
        except (TypeError, ValueError):
            raise RegistryError(f"{tipo} needs a number (decimal, or hexadecimal starting with 0x).") from None
        if not 0 <= numero < (1 << bit):
            raise RegistryError(f"{tipo} must be between 0 and {(1 << bit) - 1}.")
        return codice, numero
    esadecimale = re.sub(r"[\s,]", "", str(dati or ""))
    if len(esadecimale) > MAX_BINARY * 2:
        raise RegistryError("Binary data is too large.")
    try:
        return codice, bytes.fromhex(esadecimale)
    except ValueError:
        raise RegistryError("REG_BINARY needs hexadecimal bytes, e.g. 01 a0 ff.") from None


def check_name(nome, what: str) -> str:
    if not isinstance(nome, str) or len(nome) > 255 or any(ord(c) < 32 for c in nome) or (what == "key" and "\\" in nome):
        raise RegistryError(f"Invalid {what} name.")
    if what == "key" and not nome.strip():
        raise RegistryError("The key name cannot be empty.")
    return nome


class RegistryEditor:
    def __init__(self, backup_dir: Path):
        self.backup_dir = Path(backup_dir)

    def _reg(self, *argomenti: str) -> subprocess.CompletedProcess:
        return subprocess.run(["reg", *argomenti], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)

    # ---------- backups ----------

    def backup(self, percorso: str, motivo: str) -> str:
        """Exports the key to a .reg file before it changes; no backup, no change."""
        breve, _, sotto = parse_path(percorso)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        nome = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:19] + "-" + re.sub(r"[^\w.-]", "_", motivo)[:60] + ".reg"
        risultato = self._reg("export", full(ROOT_NAMES[breve], sotto), str(self.backup_dir / nome), "/y")
        if risultato.returncode != 0:
            raise RegistryError("The backup of the key failed, so nothing was changed: " + risultato.stdout.decode("oem", "replace").strip())
        return nome

    def backups(self) -> List[dict]:
        if not self.backup_dir.is_dir():
            return []
        elenco = []
        for file in sorted(self.backup_dir.glob("*.reg"), reverse=True)[:200]:
            try:
                with open(file, "r", encoding="utf-16") as testo:
                    chiave = next((r.strip()[1:-1] for r in testo if r.startswith("[")), "")
            except (OSError, UnicodeError):
                chiave = ""
            info = file.stat()
            elenco.append({"name": file.name, "key": chiave, "bytes": info.st_size,
                           "created": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds")})
        return elenco

    def backup_file(self, nome: str) -> Path:
        if not BACKUP_NAME.match(nome or ""):
            raise RegistryError("Unknown backup.")
        file = self.backup_dir / nome
        if not file.is_file():
            raise RegistryError("Unknown backup.")
        return file

    def restore(self, nome: str) -> str:
        file = self.backup_file(nome)
        risultato = self._reg("import", str(file))
        if risultato.returncode != 0:
            raise RegistryError("Windows refused the import: " + risultato.stdout.decode("oem", "replace").strip())
        return file.name

    # ---------- changes ----------

    def set_value(self, percorso: str, nome: str, tipo: str, dati) -> dict:
        breve, handle, sotto = parse_path(percorso)
        if not sotto:
            raise RegistryError("Values cannot be written at the root of a hive.")
        check_name(nome, "value")
        codice, valore = convert(tipo, dati)
        copia = self.backup(percorso, f"value-{nome or 'default'}")
        with winreg.OpenKey(handle, sotto, 0, winreg.KEY_SET_VALUE | VIEW) as chiave:
            winreg.SetValueEx(chiave, nome, 0, codice, valore)
        return {"backup": copia}

    def delete_value(self, percorso: str, nome: str) -> dict:
        breve, handle, sotto = parse_path(percorso)
        check_name(nome, "value")
        copia = self.backup(percorso, f"delete-value-{nome or 'default'}")
        with winreg.OpenKey(handle, sotto, 0, winreg.KEY_SET_VALUE | VIEW) as chiave:
            winreg.DeleteValue(chiave, nome)
        return {"backup": copia}

    def rename_value(self, percorso: str, vecchio: str, nuovo: str) -> dict:
        breve, handle, sotto = parse_path(percorso)
        check_name(vecchio, "value")
        check_name(nuovo, "value")
        with winreg.OpenKey(handle, sotto, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE | VIEW) as chiave:
            try:
                winreg.QueryValueEx(chiave, nuovo)
            except FileNotFoundError:
                pass
            else:
                raise RegistryError("A value with that name already exists.")
            dati, tipo = winreg.QueryValueEx(chiave, vecchio)
            copia = self.backup(percorso, f"rename-value-{vecchio or 'default'}")
            winreg.SetValueEx(chiave, nuovo, 0, tipo, dati)
            winreg.DeleteValue(chiave, vecchio)
        return {"backup": copia}

    def create_key(self, percorso: str, nome: str) -> dict:
        breve, handle, sotto = parse_path(percorso)
        check_name(nome, "key")
        if not sotto:
            raise RegistryError("Keys cannot be created at the root of a hive here.")
        nuova = sotto + "\\" + nome
        winreg.CloseKey(winreg.CreateKeyEx(handle, nuova, 0, winreg.KEY_WRITE | VIEW))
        return {"path": full(breve, nuova)}

    def delete_key(self, percorso: str) -> dict:
        breve, handle, sotto = parse_path(percorso)
        if is_protected(percorso):
            raise RegistryError(f"{full(breve, sotto)} is essential to Windows and cannot be deleted.")
        copia = self.backup(percorso, "delete-key-" + sotto.rsplit("\\", 1)[-1])
        _delete_tree(handle, sotto)
        return {"backup": copia}

    # ---------- search and export ----------

    def search(self, percorso: str, testo: str, limit: int = 200, seconds: float = 8.0) -> dict:
        """Breadth-first search of key names, value names and text data under a key, with a time budget."""
        if not testo or len(testo) < 2:
            raise RegistryError("Search for at least two characters.")
        breve, handle, sotto = parse_path(percorso)
        cercato, fine = testo.lower(), time.monotonic() + seconds
        coda, trovati, visitate = [sotto], [], 0
        while coda and len(trovati) < limit and time.monotonic() < fine:
            corrente = coda.pop(0)
            try:
                chiave = winreg.OpenKey(handle, corrente, 0, winreg.KEY_READ | VIEW)
            except OSError:
                continue
            visitate += 1
            with chiave:
                n_sotto, n_valori, _ = winreg.QueryInfoKey(chiave)
                for i in range(min(n_valori, MAX_VALUES)):
                    try:
                        nome, dati, tipo = winreg.EnumValue(chiave, i)
                    except OSError:
                        break
                    testo_dati = render(tipo, dati)[0] if tipo in (winreg.REG_SZ, winreg.REG_EXPAND_SZ, winreg.REG_MULTI_SZ) else ""
                    if cercato in nome.lower() or cercato in testo_dati.lower():
                        trovati.append({"kind": "value", "path": full(breve, corrente), "name": nome, "type": TYPES.get(tipo, ""),
                                        "display": testo_dati[:200]})
                for i in range(min(n_sotto, MAX_SUBKEYS)):
                    try:
                        figlio = winreg.EnumKey(chiave, i)
                    except OSError:
                        break
                    percorso_figlio = (corrente + "\\" if corrente else "") + figlio
                    if cercato in figlio.lower():
                        trovati.append({"kind": "key", "path": full(breve, percorso_figlio), "name": figlio})
                    coda.append(percorso_figlio)
        return {"results": trovati[:limit], "keys_searched": visitate, "complete": not coda,
                "stopped": "limit" if len(trovati) >= limit else "time" if coda else ""}

    def export(self, percorso: str) -> bytes:
        breve, _, sotto = parse_path(percorso)
        cartella = self.backup_dir.parent / "tmp"
        cartella.mkdir(parents=True, exist_ok=True)
        file = cartella / f"export-{os.getpid()}-{time.time_ns()}.reg"
        try:
            risultato = self._reg("export", full(ROOT_NAMES[breve], sotto), str(file), "/y")
            if risultato.returncode != 0:
                raise RegistryError("Export failed: " + risultato.stdout.decode("oem", "replace").strip())
            return file.read_bytes()
        finally:
            try:
                file.unlink()
            except OSError:
                pass


def _delete_tree(handle: int, sotto: str) -> None:
    with winreg.OpenKey(handle, sotto, 0, winreg.KEY_READ | winreg.KEY_WRITE | VIEW) as chiave:
        while True:
            try:
                figlio = winreg.EnumKey(chiave, 0)
            except OSError:
                break
            _delete_tree(handle, sotto + "\\" + figlio)
    winreg.DeleteKeyEx(handle, sotto, VIEW, 0)
