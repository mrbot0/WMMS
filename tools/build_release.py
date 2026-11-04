"""Builds what a GitHub release needs for the in-app updater: the program zip, SHA256SUMS.txt and the release notes
taken from CHANGELOG.md. Used by .github/workflows/release.yml; it can also be run by hand to check a release:

    python tools/build_release.py [output folder]
"""
from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("wmm.py", "ottimizza_pc.py", "start_wmm.bat", "README.md", "CHANGELOG.md")
FOLDER = "WindowsMaintenanceManager"


def version() -> str:
    trovato = re.search(r'^VERSION = "([\d.]+)"', (ROOT / "wmm" / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not trovato:
        raise SystemExit("VERSION not found in wmm/__init__.py")
    return trovato.group(1)


def notes(versione: str) -> str:
    testo = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    trovato = re.search(r"^## " + re.escape(versione) + r"\b[^\n]*\n(.*?)(?=^## |\Z)", testo, re.S | re.M)
    return trovato.group(1).strip() if trovato else "See CHANGELOG.md"


def build(uscita: Path) -> Path:
    versione = version()
    uscita.mkdir(parents=True, exist_ok=True)
    archivio = uscita / f"{FOLDER}-{versione}.zip"
    with zipfile.ZipFile(archivio, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome in FILES:
            zf.write(ROOT / nome, f"{FOLDER}/{nome}")
        for percorso in sorted((ROOT / "wmm").rglob("*")):
            if percorso.is_file() and "__pycache__" not in percorso.parts and percorso.suffix != ".pyc":
                zf.write(percorso, f"{FOLDER}/{percorso.relative_to(ROOT).as_posix()}")
    impronta = hashlib.sha256(archivio.read_bytes()).hexdigest()
    (uscita / "SHA256SUMS.txt").write_text(f"{impronta}  {archivio.name}\n", encoding="ascii")
    (uscita / "notes.md").write_text(notes(versione) + "\n", encoding="utf-8")
    return archivio


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "release"))
