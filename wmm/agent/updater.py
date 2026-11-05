"""Program updates from the GitHub releases of the project. A release carries the program as a zip and a SHA256SUMS
file (built by .github/workflows/release.yml); an update is installed only when the zip matches its checksum, has no
path outside its folder and really is the announced version. Data (dati) is never touched.

2.11: a copy installed with the MSI (Group Policy, Intune) is updated with the MSI of the release, so Windows Installer
keeps knowing what is installed (repair, uninstall, inventory). The MSI must match SHA256SUMS too; when it carries a
signature, the signature must be valid. Windows Installer replaces the files and the console restarts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple

import wmm
from wmm import installer

REPO = "mrbot0/WMMS"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ALLOWED_HOSTS = ("https://github.com/", "https://objects.githubusercontent.com/", "https://api.github.com/")
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_MSI_BYTES = 120 * 1024 * 1024
MSI_KEY = r"SOFTWARE\Windows Maintenance Manager"  # written by packaging/wmm.wxs
TIMEOUT = 30


class UpdateError(RuntimeError):
    """The update cannot be checked or installed; nothing was changed."""


def version_tuple(testo: str) -> Tuple[int, ...]:
    trovato = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (testo or "").strip())
    if not trovato:
        raise UpdateError(f"not a version: {testo!r}")
    return tuple(int(x) for x in trovato.groups())


def _get(url: str, limite: int, accept: str = "application/octet-stream") -> bytes:
    if not url.startswith(ALLOWED_HOSTS):
        raise UpdateError(f"refused download address: {url}")
    richiesta = urllib.request.Request(url, headers={"User-Agent": f"WindowsMaintenanceManager/{wmm.VERSION}", "Accept": accept})
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
        dati = risposta.read(limite + 1)
    if len(dati) > limite:
        raise UpdateError("the download is larger than expected")
    return dati


def parse_release(dati: dict) -> dict:
    """The fields of a GitHub release the updater needs."""
    versione = ".".join(map(str, version_tuple(str(dati.get("tag_name") or ""))))
    nome_zip = f"WindowsMaintenanceManager-{versione}.zip"
    nome_msi = f"WindowsMaintenanceManager-{versione}.msi"
    zip_url = sums_url = msi_url = None
    for asset in dati.get("assets") or []:
        nome, url = str(asset.get("name") or ""), str(asset.get("browser_download_url") or "")
        if nome == nome_zip:
            zip_url = url
        elif nome == nome_msi:
            msi_url = url
        elif nome == "SHA256SUMS.txt":
            sums_url = url
    return {"version": versione, "notes": str(dati.get("body") or "")[:4000], "published": str(dati.get("published_at") or ""),
            "page": str(dati.get("html_url") or ""), "zip_url": zip_url, "sums_url": sums_url, "zip_name": nome_zip,
            "msi_url": msi_url, "msi_name": nome_msi}


def check(attuale: str = wmm.VERSION) -> dict:
    """Is there a newer release? {available, current, latest, ...}; a project without releases is not an error."""
    try:
        dati = json.loads(_get(LATEST_URL, 1024 * 1024, "application/vnd.github+json").decode("utf-8"))
    except urllib.error.HTTPError as errore:
        if errore.code == 404:
            return {"available": False, "current": attuale, "latest": None, "reason": "The project has no release yet."}
        raise UpdateError(f"GitHub answered {errore.code}") from None
    except (OSError, ValueError) as errore:
        raise UpdateError(f"GitHub could not be reached: {errore}") from None
    rilascio = parse_release(dati)
    nuova = version_tuple(rilascio["version"]) > version_tuple(attuale)
    pronta = bool(rilascio["zip_url"] and rilascio["sums_url"])
    return dict(rilascio, available=nuova and pronta, current=attuale, latest=rilascio["version"],
                reason="" if pronta or not nuova else "The release has no program package and checksum yet.")


def expected_hash(sums: str, nome: str) -> str:
    for riga in sums.splitlines():
        parti = riga.strip().split()
        if len(parti) == 2 and parti[1].lstrip("*") == nome and re.fullmatch(r"[0-9a-fA-F]{64}", parti[0]):
            return parti[0].lower()
    raise UpdateError(f"{nome} is not listed in SHA256SUMS.txt")


def safe_extract(archivio: Path, cartella: Path) -> Path:
    """Extracts the zip, refusing any entry that would land outside the folder; returns the program root inside it."""
    cartella = cartella.resolve()
    shutil.rmtree(cartella, ignore_errors=True)
    cartella.mkdir(parents=True)
    with zipfile.ZipFile(archivio) as zf:
        for voce in zf.infolist():
            destinazione = (cartella / voce.filename).resolve()
            if cartella not in destinazione.parents and destinazione != cartella:
                raise UpdateError(f"the package contains a path outside its folder: {voce.filename}")
        zf.extractall(cartella)
    radici = [p.parent for p in cartella.rglob("wmm.py") if (p.parent / "wmm" / "__init__.py").exists()]
    if len(radici) != 1:
        raise UpdateError("the package does not contain the program")
    return radici[0]


def packaged_version(radice: Path) -> str:
    trovato = re.search(r'^VERSION = "([\d.]+)"', (radice / "wmm" / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not trovato:
        raise UpdateError("the package has no version")
    return trovato.group(1)


def msi_installed() -> bool:
    """The program was installed by the MSI (per machine, Program Files)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MSI_KEY) as k:
            return bool(winreg.QueryValueEx(k, "Installed")[0])
    except (OSError, ImportError):
        return False


def signature_status(percorso: Path, runner=subprocess.run) -> str:
    """Valid, NotSigned or the reason it is not valid (Authenticode, read by Windows)."""
    comando = ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"(Get-AuthenticodeSignature -LiteralPath '{percorso}').Status.ToString()"]
    try:
        r = runner(comando, capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return f"unknown ({e})"
    return (r.stdout or "").strip() or "unknown"


def install_msi(rilascio: dict, data_dir: Path, runner=subprocess.run, launcher=subprocess.Popen) -> Dict[str, object]:
    """Downloads and checks the MSI, then hands it to Windows Installer (silent, no restart of the PC)."""
    if not rilascio.get("msi_url") or not rilascio.get("sums_url"):
        raise UpdateError("the release has no MSI package and checksum")
    cartella = Path(data_dir) / "updates"
    cartella.mkdir(parents=True, exist_ok=True)
    pacchetto = _get(rilascio["msi_url"], MAX_MSI_BYTES)
    atteso = expected_hash(_get(rilascio["sums_url"], 64 * 1024).decode("utf-8", "replace"), rilascio["msi_name"])
    trovato = hashlib.sha256(pacchetto).hexdigest()
    if trovato != atteso:
        raise UpdateError("the downloaded MSI does not match its checksum: nothing was installed")
    msi = cartella / rilascio["msi_name"]
    msi.write_bytes(pacchetto)
    firma = signature_status(msi, runner)
    if firma not in ("Valid", "NotSigned"):
        raise UpdateError(f"the signature of the MSI is not valid ({firma}): nothing was installed")
    registro = cartella / f"msi-{rilascio['version']}.log"
    launcher(["msiexec", "/i", str(msi), "/qn", "/norestart", "/l*v", str(registro)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"installed": rilascio["version"], "sha256": trovato, "method": "msi", "signature": firma, "log": str(registro)}


def install(rilascio: dict, data_dir: Path, target: Optional[Path] = None) -> Dict[str, object]:
    """Downloads, checks and installs a release over the running copy (`target`, the program folder)."""
    if target is None and msi_installed() and rilascio.get("msi_url"):
        return install_msi(rilascio, data_dir)
    if not rilascio.get("zip_url") or not rilascio.get("sums_url"):
        raise UpdateError("the release has no program package and checksum")
    cartella = Path(data_dir) / "updates"
    cartella.mkdir(parents=True, exist_ok=True)
    pacchetto = _get(rilascio["zip_url"], MAX_ZIP_BYTES)
    atteso = expected_hash(_get(rilascio["sums_url"], 64 * 1024).decode("utf-8", "replace"), rilascio["zip_name"])
    trovato = hashlib.sha256(pacchetto).hexdigest()
    if trovato != atteso:
        raise UpdateError("the downloaded package does not match its checksum: nothing was installed")
    archivio = cartella / rilascio["zip_name"]
    archivio.write_bytes(pacchetto)
    radice = safe_extract(archivio, cartella / rilascio["version"])
    if packaged_version(radice) != rilascio["version"]:
        raise UpdateError("the package is not the announced version: nothing was installed")
    destinazione = Path(target or wmm.ROOT)
    esito = installer.copy_program(radice, destinazione)
    # The protected copy in Program Files keeps its admin-only permissions after the files are replaced.
    if destinazione.resolve() == installer.default_target(os.environ).resolve():
        esito["hardened"] = installer.harden(destinazione)
    return dict(esito, installed=rilascio["version"], sha256=trovato)
