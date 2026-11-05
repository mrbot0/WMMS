"""Windows Update rings (2.10). A ring sets how many days quality and feature updates wait after their release, the
Windows version to stay on, a pause, and the active hours (no restarts then). It is applied with the Windows Update
for Business policies (HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate), recorded for the undo of History,
and the compliance report says which updates are pending and how old the last one is."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Callable, Dict, Optional

from .crashes import as_list, run_json

KEY = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"


def clean_ring(dati: dict) -> dict:
    nome = str(dati.get("name", "")).strip()
    if not 1 <= len(nome) <= 40:
        raise ValueError("Ring name: 1 to 40 characters.")
    q, f = dati.get("quality_days", 0), dati.get("feature_days", 0)
    for v, massimo, testo in ((q, 30, "Quality updates: 0 to 30 days."), (f, 365, "Feature updates: 0 to 365 days.")):
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= massimo:
            raise ValueError(testo)
    versione = str(dati.get("target_version", "")).strip().upper()
    if versione and not re.fullmatch(r"\d{2}H\d", versione):
        raise ValueError("The Windows version looks like 24H2 (empty: always the latest).")
    pausa = str(dati.get("paused_until", "")).strip()
    if pausa and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pausa):
        raise ValueError("Pause until a date (YYYY-MM-DD), at most 35 days ahead.")
    if pausa and (date.fromisoformat(pausa) - date.today()).days > 35:
        raise ValueError("Windows pauses updates for at most 35 days.")
    ore = str(dati.get("active_hours", "8-18"))
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", ore)
    if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 23) or (int(m.group(2)) - int(m.group(1))) % 24 > 18:
        raise ValueError("Active hours like 8-18 (at most 18 hours).")
    return {"name": nome, "quality_days": q, "feature_days": f, "target_version": versione, "paused_until": pausa, "active_hours": ore}


def values(anello: dict) -> dict:
    """The registry values (name -> (type, value)) of a ring."""
    inizio, fine = (int(x) for x in anello.get("active_hours", "8-18").split("-"))
    v: Dict[str, tuple] = {"DeferQualityUpdates": ("dword", 1 if anello.get("quality_days") else 0), "DeferQualityUpdatesPeriodInDays": ("dword", int(anello.get("quality_days") or 0)),
         "DeferFeatureUpdates": ("dword", 1 if anello.get("feature_days") else 0), "DeferFeatureUpdatesPeriodInDays": ("dword", int(anello.get("feature_days") or 0)),
         "SetActiveHours": ("dword", 1), "ActiveHoursStart": ("dword", inizio), "ActiveHoursEnd": ("dword", fine)}
    if anello.get("target_version"):
        v.update(TargetReleaseVersion=("dword", 1), TargetReleaseVersionInfo=("string", anello["target_version"]), ProductVersion=("string", "Windows 11"))
    else:
        v.update(TargetReleaseVersion=("dword", 0))
    if anello.get("paused_until"):
        v.update(PauseQualityUpdatesStartTime=("string", date.today().isoformat()), PauseQualityUpdatesEndTime=("string", anello["paused_until"]),
                 PauseFeatureUpdatesStartTime=("string", date.today().isoformat()), PauseFeatureUpdatesEndTime=("string", anello["paused_until"]))
    return v


def apply_ring(anello: dict, preview: bool = False, writer=None) -> dict:
    """Writes the policies through the registry helpers of the tools (recorded for the undo when a run is open)."""
    from . import tools
    scritti = []
    for nome, (tipo, valore) in values(anello).items():
        if not preview:
            (writer or (tools.write_dword if tipo == "dword" else tools.write_string))("HKLM", KEY, nome, valore)
        scritti.append(f"{nome} = {valore}")
    return {"ring": anello.get("name"), "values": scritti, "preview": preview}


REPORT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0")
$pending = @($r.Updates | ForEach-Object { [ordered]@{ title = $_.Title; kb = (@($_.KBArticleIDs) -join ','); severity = "$($_.MsrcSeverity)";
  released = $_.LastDeploymentChangeTime.ToString('s') } })
$h = $s.CreateUpdateSearcher(); $n = $h.GetTotalHistoryCount()
$last = @($h.QueryHistory(0, [math]::Min($n, 50)) | Where-Object { $_.ResultCode -eq 2 } | Select-Object -First 1)
$p = Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
[ordered]@{ pending = $pending; last_installed = if ($last) { $last[0].Date.ToString('s') } else { '' }; last_title = if ($last) { $last[0].Title } else { '' };
  quality_days = $p.DeferQualityUpdatesPeriodInDays; feature_days = $p.DeferFeatureUpdatesPeriodInDays; target = "$($p.TargetReleaseVersionInfo)" } |
  ConvertTo-Json -Depth 4 -Compress
"""


def compliance_report(ctx):
    from ottimizza_pc import Esito, Stato
    c = compliance()
    for u in c["pending"][:30]:
        ctx.scrivi(f"  {u.get('severity') or '-':<10} KB{u.get('kb') or '?':<10} {u.get('title')}")
    ctx.scrivi(f"Last update installed: {c['last_installed'] or 'unknown'} ({c['days_since_last'] if c['days_since_last'] is not None else '?'} days ago)")
    if not c["compliant"]:
        return Esito(Stato.AVVISO, f"{len(c['pending'])} pending, {c['critical']} critical or important")
    return Esito(Stato.OK, f"{len(c['pending'])} pending, none critical")


def compliance(runner: Optional[Callable[[], str]] = None, now: Optional[datetime] = None) -> dict:
    d = run_json(REPORT, runner, timeout=300)
    adesso = now or datetime.now()
    in_attesa = [x for x in as_list(d.get("pending")) if isinstance(x, dict)]
    critici = [x for x in in_attesa if str(x.get("severity", "")).lower() in ("critical", "important")]
    ultimo = str(d.get("last_installed") or "")
    giorni = (adesso - datetime.fromisoformat(ultimo[:19])).days if ultimo else None
    return {"pending": in_attesa[:100], "critical": len(critici), "last_installed": ultimo or None, "last_title": d.get("last_title") or "",
            "days_since_last": giorni, "policy": {"quality_days": d.get("quality_days"), "feature_days": d.get("feature_days"), "target": d.get("target") or ""},
            "compliant": not critici and (giorni is None or giorni <= 45)}
