"""The Python that scheduled actions run with.

Tasks run as SYSTEM, so the interpreter must live where standard users cannot change it. A per-user
Python (the Microsoft Store alias in AppData\\Local\\Microsoft\\WindowsApps, or a "just for me"
install in AppData) does not qualify. This module finds a Python installed for all users, installs
one when none exists (winget, or the signed python.org installer), and records it in `python.path`
next to the program so that every start of the console uses it."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Optional

PYTHON_FILE = "python.path"
MIN_VERSION = (3, 9)
WINGET_ID = "Python.Python.3.12"
INSTALLER_VERSION = "3.12.10"
INSTALLER_URL = f"https://www.python.org/ftp/python/{INSTALLER_VERSION}/python-{INSTALLER_VERSION}-amd64.exe"
INSTALLER_SIGNER = "Python Software Foundation"
INSTALLER_ARGS = ("/quiet", "InstallAllUsers=1", "PrependPath=0", "Include_test=0", "Include_launcher=0", "Shortcuts=0")
PER_USER_MARKERS = ("\\appdata\\", "\\windowsapps\\")
HANDOVER_ENV = "WMM_PYTHON_HANDOVER"

Log = Callable[[str], None]


def _version_key(path: str) -> tuple:
    numeri = re.findall(r"Python(\d)(\d+)", path, re.IGNORECASE)
    return tuple(int(n) for n in numeri[-1]) if numeri else (0, 0)


def per_user(path: str) -> bool:
    """A Python under the user profile or the Store alias folder is never protected."""
    return any(marker in os.path.normcase(path) for marker in PER_USER_MARKERS)


def registry_pythons() -> List[str]:
    """Pythons registered for all users (HKLM\\SOFTWARE\\Python\\PythonCore, 64- and 32-bit views)."""
    import winreg
    trovati = []
    for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            radice = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\PythonCore", 0, winreg.KEY_READ | vista)
        except OSError:
            continue
        with radice:
            i = 0
            while True:
                try:
                    versione = winreg.EnumKey(radice, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(radice, versione + r"\InstallPath") as chiave:
                        try:
                            eseguibile = winreg.QueryValueEx(chiave, "ExecutablePath")[0]
                        except OSError:
                            eseguibile = os.path.join(winreg.QueryValueEx(chiave, "")[0], "python.exe")
                    trovati.append(eseguibile)
                except OSError:
                    continue
    return trovati


def candidates(environ: Mapping[str, str] = os.environ, extra: Iterable[str] = ()) -> List[str]:
    """Machine-wide Pythons, newest first. Per-user installs are left out."""
    cartelle = [environ.get("ProgramFiles", r"C:\Program Files"), environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    elenco = list(extra)
    for cartella in cartelle:
        elenco += glob.glob(os.path.join(cartella, "Python3*", "python.exe"))
    try:
        elenco += registry_pythons()
    except Exception:  # registry unreadable: the folders above are enough
        pass
    visti, risultato = set(), []
    for percorso in elenco:
        chiave = os.path.normcase(os.path.abspath(percorso))
        if chiave in visti or per_user(percorso) or not os.path.isfile(percorso):
            continue
        visti.add(chiave)
        risultato.append(os.path.abspath(percorso))
    return sorted(risultato, key=_version_key, reverse=True)


def version_ok(python: str) -> bool:
    try:
        risultato = subprocess.run([python, "-c", "import sys; print(sys.version_info[:2] >= %r)" % (MIN_VERSION,)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return risultato.stdout.strip() == b"True"


def find_protected(unprotected: Callable[[List[str]], List[str]], environ: Mapping[str, str] = os.environ) -> Optional[str]:
    """The newest machine-wide Python (3.9+) that standard users cannot change, if any."""
    from .agent.scheduler import python_paths
    for python in candidates(environ):
        if version_ok(python) and not unprotected(python_paths(python)):
            return python
    return None


def _run(comando: List[str], log: Log, timeout: int) -> int:
    log("> " + subprocess.list2cmdline(comando))
    try:
        processo = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as errore:
        log(f"  {errore}")
        return -1
    for riga in processo.stdout.decode("utf-8", "replace").splitlines():
        riga = riga.strip().strip("\x08|/-\\ ")
        if riga:
            log("  " + riga)
    return processo.returncode


def install_with_winget(log: Log) -> bool:
    winget = shutil.which("winget")
    if not winget:
        log("winget is not available on this PC.")
        return False
    codice = _run([winget, "install", "--id", WINGET_ID, "--exact", "--scope", "machine", "--silent",
                   "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"], log, 1800)
    return codice == 0


def signature_ok(path: str, log: Log) -> bool:
    """The python.org installer must carry a valid Authenticode signature of the Python Software Foundation."""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath '" + path.replace("'", "''") + "'; "
              "\"$($s.Status)|$($s.SignerCertificate.Subject)\"")
    try:
        uscita = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    stato, _, firmatario = uscita.stdout.decode("utf-8", "replace").strip().partition("|")
    log(f"  Signature: {stato} ({firmatario})")
    return stato == "Valid" and INSTALLER_SIGNER in firmatario


def install_from_python_org(log: Log, environ: Mapping[str, str] = os.environ) -> bool:
    cartella = tempfile.mkdtemp(prefix="wmm-python-")
    file = os.path.join(cartella, os.path.basename(INSTALLER_URL))
    try:
        log(f"Downloading {INSTALLER_URL}")
        try:
            with urllib.request.urlopen(INSTALLER_URL, timeout=120) as risposta, open(file, "wb") as uscita:
                shutil.copyfileobj(risposta, uscita)
        except OSError as errore:
            log(f"  Download failed: {errore}")
            return False
        if not signature_ok(file, log):
            log("  The installer signature is not valid: it is not run.")
            return False
        destinazione = os.path.join(environ.get("ProgramFiles", r"C:\Program Files"), "Python312")
        return _run([file, *INSTALLER_ARGS, f"TargetDir={destinazione}"], log, 1800) == 0
    finally:
        shutil.rmtree(cartella, ignore_errors=True)


def ensure_protected_python(unprotected: Callable[[List[str]], List[str]], log: Log,
                            installers: Iterable[Callable[[Log], bool]] = (install_with_winget, install_from_python_org)) -> Optional[str]:
    """Finds a protected Python or installs one; None when every way failed."""
    python = find_protected(unprotected)
    if python:
        log(f"Python installed for all users found: {python}")
        return python
    log("No Python installed for all users: installing one.")
    for installa in installers:
        if installa(log):
            python = find_protected(unprotected)
            if python:
                log(f"Python ready: {python}")
                return python
        log("This way did not give a protected Python; trying the next one.")
    return None


def configured(root: Path) -> Optional[str]:
    """The Python recorded next to the program, if it still exists."""
    try:
        percorso = (Path(root) / PYTHON_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return percorso if percorso and os.path.isfile(percorso) and not per_user(percorso) else None


def record(root: Path, python: str) -> None:
    (Path(root) / PYTHON_FILE).write_text(python + "\n", encoding="utf-8")


def same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
