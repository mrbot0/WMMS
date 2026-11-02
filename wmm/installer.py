"""Protected installation: scheduled actions run as SYSTEM, so the code they load
must live where standard users cannot change it (e.g. C:\\Program Files)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Mapping

PROGRAM_FILES = ("wmm.py", "ottimizza_pc.py", "start_wmm.bat")
PACKAGE = "wmm"
DATA = "dati"
DATA_SKIP = (".lock", ".tmp")
ADMINISTRATORS_SID = "*S-1-5-32-544"


def default_target(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("ProgramFiles") or r"C:\Program Files") / "WindowsMaintenanceManager"


def copy_program(source: Path, target: Path) -> Dict[str, object]:
    """Copies the program into `target`. Existing data in the target is never overwritten."""
    sorgente, destinazione = Path(source).resolve(), Path(target).resolve()
    if destinazione == sorgente or sorgente in destinazione.parents:
        raise ValueError("Choose an installation folder outside the current program folder.")
    destinazione.mkdir(parents=True, exist_ok=True)
    for nome in PROGRAM_FILES:
        shutil.copy2(sorgente / nome, destinazione / nome)
    # The package is replaced as a whole so that removed modules do not linger.
    shutil.rmtree(destinazione / PACKAGE, ignore_errors=True)
    shutil.copytree(sorgente / PACKAGE, destinazione / PACKAGE, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    dati_copiati = False
    if not (destinazione / DATA / "wmm.db").exists() and (sorgente / DATA).is_dir():
        (destinazione / DATA).mkdir(exist_ok=True)
        for file in (sorgente / DATA).iterdir():
            if file.is_file() and not file.name.endswith(DATA_SKIP):
                shutil.copy2(file, destinazione / DATA / file.name)
        dati_copiati = True
    return {"target": str(destinazione), "data_copied": dati_copiati}


def harden(target: Path) -> bool:
    """Gives ownership to Administrators and restores the inherited (admin-only write) ACL."""
    esiti = [
        subprocess.run(["icacls", str(target), "/setowner", ADMINISTRATORS_SID, "/T", "/C", "/Q"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).returncode,
        subprocess.run(["icacls", str(target), "/reset", "/T", "/C", "/Q"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).returncode,
    ]
    return all(codice == 0 for codice in esiti)


