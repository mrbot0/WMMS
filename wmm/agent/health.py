"""Health check and dependency verification, run when the console starts and on demand.

Every check returns {id, name, status: ok|warning|error, detail, critical}. A critical
error stops the start-up: without it the console cannot work at all."""
from __future__ import annotations

import ctypes
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import wmm

WINDOWS_TOOLS = ("sc", "schtasks", "dism", "sfc", "chkdsk", "fsutil", "defrag", "powercfg", "ipconfig", "netsh",
                 "icacls", "winmgmt", "taskkill")
WEB = Path(wmm.__file__).resolve().parent / "web"
MIN_FREE_BYTES = 200 * 1024 ** 2


def _check(ident: str, name: str, status: str, detail: str, critical: bool = False) -> dict:
    return {"id": ident, "name": name, "status": status, "detail": detail, "critical": critical and status == "error"}


def check_python(version: Sequence[int] = tuple(sys.version_info[:3])) -> dict:
    testo = ".".join(str(v) for v in version[:3])
    if tuple(version[:2]) < (3, 9):
        return _check("python", "Python", "error", f"Python {testo} found; 3.9 or newer is required.", True)
    return _check("python", "Python", "ok", f"Python {testo} ({sys.executable})")


def check_powershell() -> dict:
    percorso = shutil.which("powershell")
    if not percorso:
        return _check("powershell", "Windows PowerShell", "error", "powershell.exe was not found: data collection cannot work.", True)
    try:
        uscita = subprocess.run([percorso, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=30)
        versione = uscita.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired) as errore:
        return _check("powershell", "Windows PowerShell", "error", f"PowerShell does not start: {errore}", True)
    if uscita.returncode != 0 or not versione:
        return _check("powershell", "Windows PowerShell", "error", "PowerShell returned an error (execution may be blocked by policy).", True)
    return _check("powershell", "Windows PowerShell", "ok", f"Version {versione}")


def check_commands(which: Callable[[str], Optional[str]] = shutil.which) -> dict:
    mancanti = [nome for nome in WINDOWS_TOOLS if not which(nome)]
    if mancanti:
        return _check("tools", "Windows tools", "warning", "Missing: " + ", ".join(mancanti) + ". The actions that use them will fail.")
    return _check("tools", "Windows tools", "ok", f"{len(WINDOWS_TOOLS)} tools available (DISM, SFC, CHKDSK, schtasks, netsh…)")


def check_counters() -> dict:
    try:
        ctypes.WinDLL("pdh.dll")
    except OSError as errore:
        return _check("counters", "Performance counters", "warning", f"pdh.dll not available ({errore}): the live monitor is disabled.")
    return _check("counters", "Performance counters", "ok", "Live monitor available")


def check_data_dir(path: Path) -> dict:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix="wmm-health-", delete=True) as prova:
            prova.write(b"ok")
        libero = shutil.disk_usage(path).free
    except OSError as errore:
        return _check("data", "Data folder", "error", f"{path} is not writable: {errore}", True)
    if libero < MIN_FREE_BYTES:
        return _check("data", "Data folder", "warning", f"Only {libero // 1024 ** 2} MB free on the data drive.")
    return _check("data", "Data folder", "ok", f"{path} is writable")


def check_database(path: Path) -> dict:
    if not Path(path).exists():
        return _check("database", "History database", "ok", "Not created yet: it is created at first use.")
    try:
        db = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=10)
        try:
            esito = db.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            db.close()
    except sqlite3.Error as errore:
        return _check("database", "History database", "error", f"{path} cannot be read: {errore}. Move it away to start with a new history.")
    if esito != "ok":
        return _check("database", "History database", "error", f"Integrity check failed: {esito}")
    return _check("database", "History database", "ok", f"Integrity check passed ({Path(path).stat().st_size // 1024} KB)")


def check_port(port: int) -> dict:
    prova = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        prova.bind(("127.0.0.1", port))
    except OSError:
        return _check("port", "Console port", "error", f"Port {port} is already in use (another console may be open). Use --port to choose another.", True)
    finally:
        prova.close()
    return _check("port", "Console port", "ok", f"127.0.0.1:{port} is free")


def check_web_assets() -> dict:
    mancanti = [p for p in ("index.html", "css/app.css", "js/app.js", "js/api.js", "js/charts.js", "js/ui.js", "js/components.js") if not (WEB / p).is_file()]
    if mancanti:
        return _check("web", "Console files", "error", "Missing: " + ", ".join(mancanti) + ". Copy the whole program folder again.", True)
    return _check("web", "Console files", "ok", f"{sum(1 for _ in WEB.rglob('*.js'))} scripts and the stylesheet are present")


def check_admin(admin: bool) -> dict:
    if admin:
        return _check("admin", "Administrator rights", "ok", "Actions and schedules are available")
    return _check("admin", "Administrator rights", "warning", "Running without administrator rights: the console is read-only.")


def check_installation(python: str, script: str) -> List[dict]:
    from . import scheduler
    programma = scheduler.unprotected_paths(scheduler.program_paths(script))
    interprete = scheduler.unprotected_paths(scheduler.python_paths(python))
    return [
        _check("install", "Protected installation", "warning" if programma else "ok",
               ("Program folder writable by standard users: schedules are disabled. Start from start_wmm.bat to install it in Program Files."
                if programma else "Program folder can only be changed by administrators")),
        _check("python_protected", "Python for all users", "warning" if interprete else "ok",
               (f"{python} can be changed by standard users: schedules are disabled. "
                "Use Settings > This agent > Fix automatically (it installs Python for all users when needed)."
                if interprete else "Python can only be changed by administrators")),
    ]


def run_checks(data_dir: Path, port: Optional[int], admin: bool, python: str, script: str) -> List[dict]:
    voci = [check_python(), check_powershell(), check_commands(), check_counters(), check_web_assets(),
            check_data_dir(data_dir), check_database(Path(data_dir) / "wmm.db")]
    if port is not None:
        voci.append(check_port(port))
    voci.append(check_admin(admin))
    try:
        voci += check_installation(python, script)
    except Exception as errore:  # an ACL read problem must not stop the console
        voci.append(_check("install", "Protected installation", "warning", f"Could not be verified: {errore}"))
    return voci


def summary(checks: List[dict]) -> Dict[str, object]:
    conteggio = {stato: sum(1 for c in checks if c["status"] == stato) for stato in ("ok", "warning", "error")}
    conteggio["blocking"] = any(c.get("critical") for c in checks)
    return conteggio


def print_report(checks: List[dict]) -> None:
    simboli = {"ok": " OK ", "warning": "WARN", "error": "FAIL"}
    print("Health check:")
    for voce in checks:
        print(f"  [{simboli[voce['status']]}] {voce['name']:<26} {voce['detail']}")
