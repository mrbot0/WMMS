"""System Restore around manual changes: a restore point before an uninstall, a Store app removal or a deleted
registry key, the list of points, and the way back (the System Restore wizard of Windows)."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from typing import List, Optional

import wmm  # noqa: F401

from . import tools

# A point this recent already protects the next change: no new one (each takes a minute and some disk space).
REUSE_MINUTES = 60

SCRIPT_POINTS = r"""
@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue | ForEach-Object {
  [ordered]@{ seq = [int]$_.SequenceNumber; description = "$($_.Description)"; created = $_.ConvertToDateTime($_.CreationTime).ToString('s') } }) |
  ConvertTo-Json -Compress
"""


class RestoreError(RuntimeError):
    """No restore point could be made: the change must not go ahead without the user agreeing."""


def _powershell(script: str, timeout: int = 120, valori: Optional[dict] = None) -> subprocess.CompletedProcess:
    """`valori` reach the script as environment variables ($env:NAME): text from outside (a program name) never
    becomes part of the script, so no quote in it can end a string and run a command."""
    ambiente = dict(os.environ, **valori) if valori else None
    return subprocess.run(tools.powershell_command(script), capture_output=True, text=True, timeout=timeout, env=ambiente)


def parse_points(testo: str) -> List[dict]:
    try:
        dati = json.loads(testo or "[]")
    except ValueError:
        return []
    voci = dati if isinstance(dati, list) else [dati] if isinstance(dati, dict) else []
    punti = [{"seq": int(v.get("seq") or 0), "description": str(v.get("description") or ""), "created": str(v.get("created") or "")}
             for v in voci if isinstance(v, dict) and v.get("seq")]
    return sorted(punti, key=lambda p: p["created"], reverse=True)


def points() -> List[dict]:
    """Restore points of this PC, newest first (reading them needs administrator rights)."""
    return parse_points(_powershell(SCRIPT_POINTS).stdout)


def recent(elenco: List[dict], adesso: Optional[datetime] = None, minuti: int = REUSE_MINUTES) -> Optional[dict]:
    adesso = adesso or datetime.now()
    for punto in elenco:
        try:
            if adesso - datetime.fromisoformat(punto["created"]) <= timedelta(minutes=minuti):
                return punto
        except ValueError:
            continue
    return None


def before(elenco: List[dict], quando: str) -> Optional[dict]:
    """The newest point created before a change started: the one that undoes it."""
    for punto in elenco:
        if punto["created"] and punto["created"] <= quando[:19]:
            return punto
    return None


def ensure_point(motivo: str) -> dict:
    """A restore point made in the last hour, or a new one. RestoreError when Windows makes none."""
    gia = recent(points())
    if gia:
        return dict(gia, new=False)
    descrizione = ("WMM: " + motivo)[:60]
    # Windows skips a point when one is less than 24 hours old: the limit is lifted for this one call.
    script = (
        "$k = 'HKLM:\\" + tools.SYSTEM_RESTORE_KEY + "'; $n = '" + tools.RESTORE_FREQUENCY + "'\n"
        "$old = (Get-ItemProperty -Path $k -Name $n -ErrorAction SilentlyContinue).$n\n"
        "New-ItemProperty -Path $k -Name $n -Value 0 -PropertyType DWord -Force | Out-Null\n"
        "try { Enable-ComputerRestore -Drive \"$env:SystemDrive\\\" -ErrorAction SilentlyContinue\n"
        "  Checkpoint-Computer -Description $env:WMM_RESTORE_DESCRIPTION -RestorePointType MODIFY_SETTINGS -ErrorAction Stop }\n"
        "finally { if ($null -eq $old) { Remove-ItemProperty -Path $k -Name $n -ErrorAction SilentlyContinue }\n"
        "  else { Set-ItemProperty -Path $k -Name $n -Value $old } }\n"
    )
    try:
        risultato = _powershell(script, timeout=600, valori={"WMM_RESTORE_DESCRIPTION": descrizione})
    except subprocess.TimeoutExpired:
        raise RestoreError("Windows took more than ten minutes to create the restore point.") from None
    nuovo = recent(points(), minuti=5)
    if not nuovo:
        dettaglio = (risultato.stderr or "").strip().splitlines()
        raise RestoreError("Windows did not create a restore point" + (f": {dettaglio[-1][:200]}" if dettaglio else "") +
                           ". Turn on System Restore for the system drive (Security page) or continue without it.")
    return dict(nuovo, new=True)


def open_wizard() -> None:
    """System Restore of Windows: the user picks the point and Windows restarts to apply it."""
    subprocess.Popen(["rstrui.exe"])
