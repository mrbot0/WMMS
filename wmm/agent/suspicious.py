"""Suspicious programs (2.8). For every program that is running or starts with Windows (Run keys, startup folders,
services, scheduled tasks) this checks the digital signature and where the file lives, and flags what malware does:
an invalid signature, a Windows file name outside the Windows folder, a program started from a temporary or download
folder, a double extension, a hidden PowerShell command at startup. Optionally, with a free VirusTotal key of your own,
the SHA-256 fingerprint (never the file) of the flagged programs is looked up: at most 4 a check, cached for 7 days."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ottimizza_pc import Esito, Stato

from . import notify
from .crashes import as_list, run_json

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
function ExePath([string]$c) {
  if (-not $c) { return $null }
  $c = [Environment]::ExpandEnvironmentVariables($c.Trim())
  if ($c -match '^"([^"]+)"') { return $Matches[1] }
  if ($c -match '^(.+?\.(exe|com|scr|bat|cmd|ps1|vbs|js|hta))(\s|$)') { return $Matches[1] }
  return ($c -split '\s+')[0]
}
$items = New-Object System.Collections.ArrayList
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath } | ForEach-Object {
  [void]$items.Add([ordered]@{ source = 'running'; name = $_.Name; command = "$($_.CommandLine)"; path = $_.ExecutablePath }) }
foreach ($k in 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
               'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
               'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce') {
  $p = Get-ItemProperty $k
  if ($p) { foreach ($v in $p.PSObject.Properties) { if ($v.Name -notlike 'PS*') {
    [void]$items.Add([ordered]@{ source = 'run_key'; name = $v.Name; command = "$($v.Value)"; path = (ExePath "$($v.Value)") }) } } }
}
$sh = New-Object -ComObject WScript.Shell
foreach ($d in [Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup')) {
  Get-ChildItem $d -File | Where-Object { $_.Name -ne 'desktop.ini' } | ForEach-Object {
    $t = $_.FullName; $cmd = $t
    if ($_.Extension -eq '.lnk') { $l = $sh.CreateShortcut($_.FullName); $t = $l.TargetPath; $cmd = "$($l.TargetPath) $($l.Arguments)" }
    [void]$items.Add([ordered]@{ source = 'startup_folder'; name = $_.Name; command = $cmd; path = $t }) }
}
Get-CimInstance Win32_Service | Where-Object { $_.StartMode -ne 'Disabled' -and $_.PathName -and $_.PathName -notmatch 'svchost\.exe' } | ForEach-Object {
  [void]$items.Add([ordered]@{ source = 'service'; name = $_.Name; command = "$($_.PathName)"; path = (ExePath "$($_.PathName)") }) }
Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' -and $_.State -ne 'Disabled' } | ForEach-Object {
  $tn = "$($_.TaskPath)$($_.TaskName)"
  foreach ($a in @($_.Actions)) { if ($a.Execute) {
    [void]$items.Add([ordered]@{ source = 'task'; name = $tn; command = "$($a.Execute) $($a.Arguments)".Trim(); path = (ExePath "$($a.Execute)") }) } } }
$files = @{}
foreach ($i in $items) {
  $p = "$($i.path)"
  if ($p -and -not $files.ContainsKey($p.ToLower()) -and $files.Count -lt 400 -and (Test-Path -LiteralPath $p -PathType Leaf)) {
    $s = Get-AuthenticodeSignature -LiteralPath $p
    $h = Get-FileHash -LiteralPath $p -Algorithm SHA256
    $files[$p.ToLower()] = [ordered]@{ path = $p; status = "$($s.Status)"; signer = "$($s.SignerCertificate.Subject)"; sha256 = "$($h.Hash)".ToLower();
      size = (Get-Item -LiteralPath $p).Length }
  }
}
[ordered]@{ items = @($items); files = @($files.Values) } | ConvertTo-Json -Depth 4 -Compress
"""

SYSTEM_NAMES = {"svchost.exe", "lsass.exe", "csrss.exe", "winlogon.exe", "services.exe", "smss.exe", "wininit.exe", "dllhost.exe",
                "rundll32.exe", "taskhostw.exe", "spoolsv.exe", "conhost.exe", "explorer.exe", "lsm.exe", "ctfmon.exe", "dwm.exe"}
RISKY_FOLDERS = re.compile(r"\\(temp|tmp|downloads|\$recycle\.bin)\\|\\users\\public\\|\\appdata\\local\\temp\\|^[a-z]:\\programdata\\[^\\]+$|"
                           r"\\appdata\\roaming\\[^\\]+\.(exe|scr|com)$", re.I)
TRUSTED_FOLDERS = re.compile(r"^[a-z]:\\(windows|program files|program files \(x86\))\\", re.I)
DOUBLE_EXTENSION = re.compile(r"\.(pdf|docx?|xlsx?|jpe?g|png|txt|zip|mp4)\.(exe|scr|com|bat|cmd|vbs|js)$", re.I)
HIDDEN_SCRIPT = re.compile(r"(powershell|pwsh)(\.exe)?\b.*\s-(e|en|enc|encodedcommand)\s|mshta(\.exe)?\s+(https?|javascript|vbscript):|"
                           r"(wscript|cscript)(\.exe)?\s.*\\(temp|appdata)\\", re.I)
BAD_SIGNATURE = {"HashMismatch", "NotTrusted", "Incompatible", "NotSupportedFileFormat"}
FLAGS = {
    "bad_signature": ("high", "The digital signature is not valid: the file was changed after it was signed.",
                      "La firma digitale non è valida: il file è stato modificato dopo la firma."),
    "system_name": ("high", "It has the name of a Windows file but lives outside the Windows folder.",
                    "Ha il nome di un file di Windows ma si trova fuori dalla cartella di Windows."),
    "risky_folder": ("high", "It runs from a temporary, download or public folder.",
                     "Parte da una cartella temporanea, dei download o pubblica."),
    "double_extension": ("high", "A double extension (like .pdf.exe) hides a program behind a document.",
                         "Una doppia estensione (come .pdf.exe) nasconde un programma dietro un documento."),
    "hidden_script": ("high", "A hidden or encoded script command starts here.", "Da qui parte un comando di script nascosto o codificato."),
    "unsigned": ("medium", "Not signed and outside Program Files.", "Non firmato e fuori da Programmi."),
    "unsigned_installed": ("low", "Not signed (installed in Program Files).", "Non firmato (installato in Programmi)."),
}
LEVELS = {"high": 3, "medium": 2, "low": 1}
VT_URL = "https://www.virustotal.com/api/v3/files/"
VT_PER_CHECK = 4
VT_CACHE_DAYS = 7


def evaluate(dati: dict) -> List[dict]:
    """One row per file with its sources, flags and level (no row for signed files with nothing odd)."""
    def pulito(p: str) -> str:
        return p[4:] if p.startswith("\\\\?\\") else p  # \\?\C:\... is the long-path form of the same file
    file = {pulito(str(f.get("path", ""))).lower(): f for f in as_list(dati.get("files")) if isinstance(f, dict) and f.get("path")}
    gruppi: Dict[str, dict] = {}
    for voce in as_list(dati.get("items")):
        if not isinstance(voce, dict):
            continue
        percorso = pulito(str(voce.get("path") or ""))
        chiave = percorso.lower() or "cmd:" + str(voce.get("command", ""))[:200].lower()
        g = gruppi.setdefault(chiave, {"path": percorso, "sources": [], "commands": [], "file": file.get(percorso.lower())})
        fonte = {"source": str(voce.get("source")), "name": str(voce.get("name") or "")[:200]}
        if fonte not in g["sources"]:
            g["sources"].append(fonte)
        comando = str(voce.get("command") or "")[:400]
        if comando and comando not in g["commands"]:
            g["commands"].append(comando)
    righe = []
    for g in gruppi.values():
        percorso, f = g["path"], g["file"] or {}
        nome = re.split(r"[\\/]", percorso)[-1].lower() if percorso else ""
        segni = []
        stato = str(f.get("status") or "")
        if stato in BAD_SIGNATURE:
            segni.append("bad_signature")
        if nome in SYSTEM_NAMES and percorso and not re.match(r"^[a-z]:\\windows\\", percorso, re.I):
            segni.append("system_name")
        if percorso and RISKY_FOLDERS.search(percorso):
            segni.append("risky_folder")
        if DOUBLE_EXTENSION.search(nome):
            segni.append("double_extension")
        if any(HIDDEN_SCRIPT.search(c) for c in g["commands"]) and any(s["source"] != "running" for s in g["sources"]):
            segni.append("hidden_script")
        if stato == "NotSigned":
            segni.append("unsigned_installed" if TRUSTED_FOLDERS.match(percorso) else "unsigned")
        if not segni:
            continue
        livello = max((FLAGS[s][0] for s in segni), key=lambda l: LEVELS[l])
        righe.append({"path": percorso, "name": nome or (g["sources"][0]["name"] if g["sources"] else ""), "sources": g["sources"][:10],
                      "commands": g["commands"][:3], "signature": stato or "missing", "signer": str(f.get("signer") or "")[:200],
                      "sha256": str(f.get("sha256") or ""), "size": f.get("size"), "flags": segni,
                      "reasons": [FLAGS[s][1] for s in segni], "reasons_it": [FLAGS[s][2] for s in segni], "level": livello, "virustotal": None})
    righe.sort(key=lambda r: (-LEVELS[r["level"]], r["path"].lower()))
    return righe


# ---------- settings, cache and VirusTotal ----------

def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "suspicious.json"


def _read(data_dir: Path) -> dict:
    try:
        dati = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return dati if isinstance(dati, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data_dir: Path, dati: dict) -> None:
    _path(data_dir).parent.mkdir(parents=True, exist_ok=True)
    _path(data_dir).write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")


def settings(data_dir: Path) -> dict:
    return {"virustotal": bool(_read(data_dir).get("vt_key"))}


def save_settings(data_dir: Path, chiave) -> dict:
    """The VirusTotal key, kept encrypted for this Windows user (DPAPI); an empty value removes it."""
    if not isinstance(chiave, str) or (chiave and not re.fullmatch(r"[0-9a-f]{64}", chiave.strip())):
        raise ValueError("A VirusTotal API key is 64 hexadecimal characters.")
    dati = _read(data_dir)
    if chiave.strip():
        dati["vt_key"] = notify.protect(chiave.strip())
    else:
        dati.pop("vt_key", None)
    _write(data_dir, dati)
    return settings(data_dir)


def vt_lookup(chiave: str, sha256: str, opener=None) -> dict:
    richiesta = urllib.request.Request(VT_URL + sha256, headers={"x-apikey": chiave, "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(richiesta, timeout=15) as risposta:
            dati = json.loads(risposta.read(512 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as errore:
        if errore.code == 404:
            return {"known": False}
        return {"error": "the key was refused" if errore.code in (401, 403) else "limit reached" if errore.code == 429 else f"HTTP {errore.code}"}
    except (OSError, ValueError) as errore:
        return {"error": str(getattr(errore, "reason", errore))[:120]}
    stats = ((dati.get("data") or {}).get("attributes") or {}).get("last_analysis_stats") or {}
    totale = sum(v for v in stats.values() if isinstance(v, int))
    return {"known": True, "malicious": int(stats.get("malicious") or 0), "suspicious": int(stats.get("suspicious") or 0), "engines": totale}


def add_reputation(data_dir: Path, righe: List[dict], lookup=None, now: Optional[float] = None) -> int:
    """VirusTotal answers for the high and medium rows: from the cache when fresh, else at most VT_PER_CHECK lookups."""
    dati = _read(data_dir)
    from . import appsettings
    chiave = notify.unprotect(dati.get("vt_key", "")) if dati.get("vt_key") and appsettings.allowed(data_dir, "virustotal") else ""
    cache = dati.setdefault("cache", {})
    adesso = now or time.time()
    chiesti = 0
    for r in righe:
        h = r.get("sha256")
        if not h or r["level"] == "low":
            continue
        memoria = cache.get(h)
        if memoria and adesso - memoria.get("t", 0) < VT_CACHE_DAYS * 86400:
            r["virustotal"] = memoria["result"]
            continue
        if not chiave or chiesti >= VT_PER_CHECK:
            continue
        risultato = (lookup or vt_lookup)(chiave, h)
        chiesti += 1
        r["virustotal"] = risultato
        if "error" not in risultato:
            cache[h] = {"t": adesso, "result": risultato}
        if risultato.get("malicious"):
            r["level"] = "high"
    if chiesti:
        dati["cache"] = dict(sorted(cache.items(), key=lambda kv: kv[1].get("t", 0))[-500:])
        _write(data_dir, dati)
    return chiesti


def check(data_dir: Path, runner: Optional[Callable[[], str]] = None, lookup=None) -> dict:
    dati = run_json(SCRIPT, runner, timeout=300)
    righe = evaluate(dati)
    add_reputation(data_dir, righe, lookup)
    esito = {"checked": datetime.now().isoformat(timespec="seconds"), "items": len(as_list(dati.get("items"))),
             "files": len(as_list(dati.get("files"))), "rows": righe,
             "counts": {l: sum(1 for r in righe if r["level"] == l) for l in LEVELS}, "virustotal": settings(data_dir)["virustotal"]}
    salvati = _read(data_dir)
    salvati["last"] = esito
    _write(data_dir, salvati)
    return esito


def last(data_dir: Path) -> Optional[dict]:
    dati = _read(data_dir).get("last")
    if isinstance(dati, dict):
        dati["virustotal"] = settings(data_dir)["virustotal"]
    return dati


def suspicious_programs(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    esito = check(Path(data_dir) if data_dir else DATA_DIR)
    for r in esito["rows"]:
        if r["level"] == "low":
            continue
        vt = r.get("virustotal") or {}
        extra = f"  VirusTotal: {vt['malicious']}/{vt['engines']} engines" if vt.get("known") else ""
        ctx.scrivi(f"{r['level'].upper():<6} {r['path'] or r['name']}  ({', '.join(s['source'] for s in r['sources'])}){extra}")
        for motivo in r["reasons"]:
            ctx.scrivi(f"       {motivo}")
    alti = esito["counts"]["high"]
    ctx.scrivi(f"{esito['files']} programs checked, {esito['counts']['low']} unsigned programs in Program Files not listed.")
    if alti or esito["counts"]["medium"]:
        return Esito(Stato.AVVISO, f"{alti} suspicious, {esito['counts']['medium']} to check")
    return Esito(Stato.OK, f"{esito['files']} programs checked, nothing suspicious")
