"""Alerts on suspicious changes. Adware and malware need a way to start again and to hide: a Run key, a scheduled task,
a service, a browser extension, a proxy, a line in the hosts file, an antivirus exclusion or a new administrator. This
takes a snapshot of those places (read-only), compares it with the previous one and reports what appeared, disappeared
or changed, with an e-mail or Telegram alert. The first snapshot is the baseline; each change is reported once."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from ottimizza_pc import Esito, Stato

from . import securestore
from . import notify
from .tools import powershell_command

CATEGORIES = {
    "run_keys": "Programs that start with Windows (Run keys)", "startup_folders": "Startup folders", "services": "Services",
    "tasks": "Scheduled tasks (not Microsoft)", "hosts": "Hosts file", "proxy": "Proxy settings", "defender_exclusions": "Antivirus exclusions",
    "extensions": "Browser extensions", "admins": "Local administrators",
}

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{}
$run = @{}
foreach ($k in 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
               'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
               'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce') {
  $p = Get-ItemProperty $k
  if ($p) { foreach ($v in $p.PSObject.Properties) { if ($v.Name -notlike 'PS*') { $run["$k\$($v.Name)"] = "$($v.Value)" } } }
}
$out.run_keys = $run
$sf = @{}
foreach ($d in [Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup')) {
  Get-ChildItem $d -File | ForEach-Object { $sf[$_.FullName] = "$($_.Length)" }
}
$out.startup_folders = $sf
$sv = @{}
Get-CimInstance Win32_Service | ForEach-Object { $sv[$_.Name] = "$($_.StartMode) | $($_.PathName)" }
$out.services = $sv
$tk = @{}
Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  $tk["$($_.TaskPath)$($_.TaskName)"] = (@($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)".Trim() }) -join ' ; ')
}
$out.tasks = $tk
$h = @{}
Get-Content (Join-Path $env:SystemRoot 'System32\drivers\etc\hosts') | Where-Object { $_ -match '^\s*[^#\s]' } | ForEach-Object { $h[($_ -replace '\s+', ' ').Trim()] = 'line' }
$out.hosts = $h
$is = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$out.proxy = @{ 'ProxyEnable' = "$($is.ProxyEnable)"; 'ProxyServer' = "$($is.ProxyServer)"; 'AutoConfigURL' = "$($is.AutoConfigURL)" }
$ex = @{}
$m = Get-MpPreference
if ($m) {
  foreach ($x in @($m.ExclusionPath)) { if ($x -and $x -notmatch 'N/A') { $ex["path: $x"] = 'excluded' } }
  foreach ($x in @($m.ExclusionProcess)) { if ($x -and $x -notmatch 'N/A') { $ex["process: $x"] = 'excluded' } }
  foreach ($x in @($m.ExclusionExtension)) { if ($x -and $x -notmatch 'N/A') { $ex["extension: $x"] = 'excluded' } }
}
$out.defender_exclusions = $ex
$be = @{}
foreach ($b in @(@('Chrome', "$env:LOCALAPPDATA\Google\Chrome\User Data"), @('Edge', "$env:LOCALAPPDATA\Microsoft\Edge\User Data"),
                 @('Brave', "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"))) {
  Get-ChildItem $b[1] -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'Extensions') } | ForEach-Object {
    $prof = $_.Name
    Get-ChildItem (Join-Path $_.FullName 'Extensions') -Directory | ForEach-Object { $be["$($b[0]) $prof $($_.Name)"] = 'installed' }
  }
}
Get-ChildItem "$env:APPDATA\Mozilla\Firefox\Profiles\*\extensions" -File | ForEach-Object { $be["Firefox $($_.Name)"] = 'installed' }
$out.extensions = $be
$ad = @{}
$g = Get-LocalGroup -SID 'S-1-5-32-544'
if ($g) { Get-LocalGroupMember -Group $g | ForEach-Object { $ad["$($_.Name)"] = "$($_.PrincipalSource)" } }
$out.admins = $ad
$out | ConvertTo-Json -Depth 4 -Compress
"""


def snapshot(runner: Optional[Callable[[], str]] = None) -> Dict[str, Dict[str, str]]:
    if runner is None:
        finito = subprocess.run(powershell_command(SCRIPT), capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        testo = finito.stdout
    else:
        testo = runner()
    righe = (testo or "").strip().splitlines()
    try:
        dati = json.loads(righe[-1]) if righe else {}
    except ValueError:
        dati = {}
    risultato = {}
    for categoria in CATEGORIES:
        voci = dati.get(categoria) if isinstance(dati, dict) else None
        risultato[categoria] = {str(k)[:300]: str(v)[:500] for k, v in voci.items()} if isinstance(voci, dict) else {}
    return risultato


def compare(prima: Dict[str, Dict[str, str]], dopo: Dict[str, Dict[str, str]]) -> dict:
    """What appeared, disappeared or changed in each category. An empty read (for example antivirus exclusions without
    administrator rights) is a read that failed, not "everything was removed", so that category is not compared."""
    differenze = {"added": [], "removed": [], "changed": []}
    for categoria in CATEGORIES:
        a, b = prima.get(categoria), dopo.get(categoria)
        if a is None or b is None or (not b and a):
            continue
        for chiave in sorted(set(b) - set(a)):
            differenze["added"].append({"category": categoria, "item": chiave, "detail": b[chiave]})
        for chiave in sorted(set(a) - set(b)):
            differenze["removed"].append({"category": categoria, "item": chiave, "detail": a[chiave]})
        for chiave in sorted(set(a) & set(b)):
            if a[chiave] != b[chiave]:
                differenze["changed"].append({"category": categoria, "item": chiave, "before": a[chiave], "detail": b[chiave]})
    return differenze


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "drift.json"


def last(data_dir: Path) -> dict:
    try:
        dati = json.loads(securestore.read_text(_path(data_dir)))
    except (OSError, ValueError):
        dati = {}
    return {"checked": dati.get("checked"), "baseline_from": dati.get("baseline_from"), "last": dati.get("last"),
            "history": dati.get("history", [])[-30:], "counts": {c: len(v) for c, v in (dati.get("baseline") or {}).items()},
            "categories": CATEGORIES}


def check(data_dir: Path, runner: Optional[Callable[[], str]] = None) -> dict:
    """Takes a new snapshot, compares it with the stored one and keeps the new one as the baseline."""
    percorso = _path(data_dir)
    try:
        dati = json.loads(securestore.read_text(percorso))
    except (OSError, ValueError):
        dati = {}
    adesso = datetime.now().isoformat(timespec="seconds")
    nuovo = snapshot(runner)
    precedente = dati.get("baseline")
    differenze = compare(precedente, nuovo) if precedente else {"added": [], "removed": [], "changed": []}
    totale = sum(len(v) for v in differenze.values())
    if precedente:  # a category that could not be read this time keeps its previous content
        for categoria, voci in nuovo.items():
            if not voci and precedente.get(categoria):
                nuovo[categoria] = precedente[categoria]
    esito = dict(differenze, at=adesso, first=not precedente, total=totale)
    dati.update(baseline=nuovo, checked=adesso, last=esito)
    dati.setdefault("baseline_from", adesso)
    if totale:
        dati["history"] = (dati.get("history", []) + [esito])[-50:]
    percorso.parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(percorso, json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    try:  # the dated copy that "Back to the last good configuration" goes back to (2.8)
        from .goodconfig import save_snapshot
        save_snapshot(percorso.parent, nuovo)
    except OSError:
        pass
    return esito


def describe(voce: dict) -> str:
    return f"{CATEGORIES.get(voce['category'], voce['category'])}: {voce['item']}" + (f" ({voce['detail'][:120]})" if voce.get("detail") else "")


def drift_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    esito = check(cartella)
    if esito["first"]:
        ctx.scrivi("First snapshot taken: from now on every new startup program, task, service, extension, proxy, hosts line, "
                   "antivirus exclusion or administrator is reported.")
        return Esito(Stato.OK, "baseline taken")
    for titolo, chiave in (("NEW", "added"), ("REMOVED", "removed"), ("CHANGED", "changed")):
        for voce in esito[chiave]:
            ctx.scrivi(f"  {titolo}  {describe(voce)}")
    if not esito["total"]:
        return Esito(Stato.OK, "nothing changed since the previous check")
    sospetti = esito["added"] + esito["changed"]
    if sospetti:
        testo = "Changes in the places programs use to start and hide:\n" + "\n".join("- " + describe(v) for v in sospetti[:25]) + \
                "\n\nIf you did not install anything, open Security in the console."
        notify.safe_event(cartella, "config_changed", testo, gruppo=hashlib.sha1(testo.encode("utf-8")).hexdigest()[:12])
    return Esito(Stato.AVVISO, f"{len(esito['added'])} new, {len(esito['changed'])} changed, {len(esito['removed'])} removed")
