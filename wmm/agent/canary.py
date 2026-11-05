"""Ransomware protection (2.10). Two layers:

- Controlled Folder Access of Microsoft Defender (on, audit only, off), with the list of protected folders and the
  programs blocked recently (events 1123/1124 of the Defender log).
- Decoy files: documents with ordinary names placed in Documents, Desktop and Pictures (hidden), with their SHA-256.
  A ransomware encrypts everything it finds; when a decoy changes or disappears, the scheduled check sends the alert
  "ransomware_canary" at once, with the programs that were running. Nobody has a reason to touch them."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from ottimizza_pc import Esito, Stato

from . import notify, securestore
from .crashes import as_list, run_json
from .tools import powershell_command

DECOYS = (("Documents", "Contratti 2026 - riepilogo.docx"), ("Documents", "Fatture fornitori.xlsx"), ("Desktop", "Password vecchie.txt"),
          ("Pictures", "Scansione documento identita.jpg"))


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "canary.json"


def _content(nome: str) -> bytes:
    """Plausible bytes for the extension (a ransomware may skip files that look empty), random so each PC differs."""
    corpo = secrets.token_bytes(4096 + secrets.randbelow(4096))
    if nome.endswith((".docx", ".xlsx")):
        return b"PK\x03\x04" + corpo
    if nome.endswith(".jpg"):
        return b"\xff\xd8\xff\xe0" + corpo
    return ("Elenco aggiornato\r\n" + secrets.token_hex(64) + "\r\n").encode() * 8


def folders() -> List[Path]:
    casa = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return [casa / cartella for cartella, _ in DECOYS]


def place(data_dir: Path, base: Optional[Path] = None) -> List[dict]:
    """Puts the decoys (hidden) and records their fingerprints."""
    casa = Path(base) if base else Path(os.environ.get("USERPROFILE", str(Path.home())))
    voci = []
    for cartella, nome in DECOYS:
        destino = casa / cartella
        if not destino.is_dir():
            continue
        p = destino / nome
        dati = _content(nome)
        if p.exists():  # a hidden file cannot be overwritten: unhide and delete the old decoy first
            subprocess.run(["attrib", "-h", str(p)], capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            p.unlink(missing_ok=True)
        p.write_bytes(dati)
        try:
            subprocess.run(["attrib", "+h", str(p)], capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
        voci.append({"path": str(p), "sha256": hashlib.sha256(dati).hexdigest(), "placed": datetime.now().isoformat(timespec="seconds")})
    securestore.write_text(_path(data_dir), json.dumps({"decoys": voci}, indent=1))
    return voci


def state(data_dir: Path) -> dict:
    try:
        dati = json.loads(securestore.read_text(_path(data_dir)))
    except (OSError, ValueError):
        dati = {}
    return {"decoys": dati.get("decoys", []), "last_check": dati.get("last_check"), "tripped": dati.get("tripped", [])}


def check(data_dir: Path) -> dict:
    """Which decoys changed or disappeared since they were placed."""
    s = state(data_dir)
    toccati = []
    for v in s["decoys"]:
        p = Path(v["path"])
        try:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            toccati.append(dict(v, change="missing"))
            continue
        if h != v["sha256"]:
            toccati.append(dict(v, change="modified"))
    s.update(last_check=datetime.now().isoformat(timespec="seconds"), tripped=toccati)
    securestore.write_text(_path(data_dir), json.dumps({"decoys": s["decoys"], "last_check": s["last_check"], "tripped": toccati}, indent=1))
    return s


def remove(data_dir: Path) -> int:
    n = 0
    for v in state(data_dir)["decoys"]:
        try:
            subprocess.run(["attrib", "-h", v["path"]], capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            Path(v["path"]).unlink()
            n += 1
        except (OSError, subprocess.SubprocessError):
            pass
    securestore.write_text(_path(data_dir), json.dumps({"decoys": []}))
    return n


CFA_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$p = Get-MpPreference
$ev = @(Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-Windows Defender/Operational'; Id = 1123, 1124 } -MaxEvents 30 |
  ForEach-Object { $d = @{}; foreach ($x in ([xml]$_.ToXml()).Event.EventData.Data) { $d[$x.Name] = "$($x.'#text')" }
    [ordered]@{ at = $_.TimeCreated.ToString('s'); blocked = ($_.Id -eq 1123); program = $d['Process Name']; path = $d['Path'] } })
[ordered]@{ mode = "$($p.EnableControlledFolderAccess)"; folders = @($p.ControlledFolderAccessProtectedFolders); allowed = @($p.ControlledFolderAccessAllowedApplications);
  events = $ev } | ConvertTo-Json -Depth 4 -Compress
"""
MODES = {"0": "off", "1": "on", "2": "audit", "3": "off", "4": "audit"}


def cfa_state(runner: Optional[Callable[[], str]] = None) -> dict:
    d = run_json(CFA_SCRIPT, runner)
    return {"mode": MODES.get(str(d.get("mode", "")), "unknown"), "folders": [str(x) for x in as_list(d.get("folders")) if x],
            "allowed": [str(x) for x in as_list(d.get("allowed")) if x],
            "events": [e for e in as_list(d.get("events")) if isinstance(e, dict)][:30]}


def cfa_set(mode: str) -> None:
    valori = {"on": "Enabled", "audit": "AuditMode", "off": "Disabled"}
    if mode not in valori:
        raise ValueError("Mode: on, audit or off.")
    finito = subprocess.run(powershell_command(f"Set-MpPreference -EnableControlledFolderAccess {valori[mode]}"), capture_output=True, text=True,
                            timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if finito.returncode != 0:
        raise OSError((finito.stderr or finito.stdout).strip()[-300:] or "Defender refused the change")


def canary_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    s = state(cartella)
    if not s["decoys"]:
        ctx.scrivi("No decoy files yet: place them from Security › Ransomware protection.")
        return Esito(Stato.AVVISO, "no decoys placed")
    s = check(cartella)
    if not s["tripped"]:
        ctx.scrivi(f"{len(s['decoys'])} decoy files intact.")
        return Esito(Stato.OK, "decoys intact")
    for v in s["tripped"]:
        ctx.scrivi(f"  {v['change'].upper()}  {v['path']}")
    try:
        processi = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        nomi = sorted({r.split('","')[0].strip('"') for r in processi.splitlines() if r})[:80]
    except (OSError, subprocess.SubprocessError):
        nomi = []
    testo = ("Decoy files were changed or deleted: this is how ransomware behaves.\n" + "\n".join(f"- {v['change']}: {v['path']}" for v in s["tripped"]) +
             "\n\nDisconnect the PC from the network now and check it.\nRunning programs: " + ", ".join(nomi))
    notify.safe_event(cartella, "ransomware_canary", testo, gruppo=hashlib.sha1(testo[:200].encode()).hexdigest()[:12])
    return Esito(Stato.ERRORE, f"{len(s['tripped'])} decoy files touched")
