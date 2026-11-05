"""2.12: thirty everyday features, the agent side. Every function here reads; the few that change something (moving
files to the Recycle Bin, the nightly winget update, the copy of the user's files, rules, delegations) say so and go
through the same preview, permission and audit checks as every other change.

  why the PC is slow right now · when the disk will be full · folder map · duplicate and forgotten files · recent
  installs · risky browser extensions · listening ports explained · end of support of this Windows · calendar of the
  updates · step-by-step internet check · nightly winget update with exceptions · inventory label with QR code · copy of
  the user's files to a disk or NAS · rules "when X happens, run Y" · what changed since yesterday · goals · diagnostic
  package · temporary delegation of a role · access review."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import secrets
import socket
import subprocess
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from ottimizza_pc import Esito, Stato

from . import crashes, securestore


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_file(path: Path, predefinito):
    try:
        return json.loads(securestore.read_text(path))
    except (OSError, ValueError):
        return predefinito


def _write_json(path: Path, dati) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(path, json.dumps(dati, indent=1, ensure_ascii=False))


# ======================================================================= 1. why the PC is slow right now

SCRIPT_SLOW = r"""
$n = [Environment]::ProcessorCount
$a = @{}; Get-Process | ForEach-Object { $a[$_.Id] = $_.CPU }
Start-Sleep -Milliseconds 1500
$top = Get-Process | ForEach-Object {
  $d = 0; if ($a.ContainsKey($_.Id) -and $_.CPU -ne $null -and $a[$_.Id] -ne $null) { $d = ($_.CPU - $a[$_.Id]) / 1.5 / $n * 100 }
  [pscustomobject]@{ name = $_.ProcessName; cpu = [math]::Round($d, 1); mem_mb = [math]::Round($_.WorkingSet64 / 1MB) } }
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average
$disk = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'" -ErrorAction SilentlyContinue
$plan = (powercfg /getactivescheme) -replace '^.*\((.*)\)\s*$', '$1'
[ordered]@{
  cpu = $cpu; cores = $n
  mem_total_mb = [math]::Round($os.TotalVisibleMemorySize / 1KB); mem_free_mb = [math]::Round($os.FreePhysicalMemory / 1KB)
  disk_busy = if ($disk) { 100 - $disk.PercentIdleTime } else { $null }; disk_queue = if ($disk) { $disk.CurrentDiskQueueLength } else { $null }
  uptime_days = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalDays, 1); power_plan = "$plan"
  top_cpu = @($top | Sort-Object cpu -Descending | Select-Object -First 5); top_mem = @($top | Sort-Object mem_mb -Descending | Select-Object -First 5)
} | ConvertTo-Json -Depth 4 -Compress
"""

BACKGROUND = {
    "tiworker": "Windows Update is installing updates", "trustedinstaller": "Windows Update is installing updates",
    "msmpeng": "Microsoft Defender is scanning the PC", "mpdefendercoreservice": "Microsoft Defender is scanning the PC",
    "searchindexer": "Windows Search is indexing files", "searchprotocolhost": "Windows Search is indexing files",
    "onedrive": "OneDrive is synchronizing files", "compattelrunner": "Windows telemetry is collecting data",
    "msiexec": "a program is being installed", "wuauclt": "Windows Update is working", "svchost": "a Windows service is busy",
}


def explain_slow(d: dict) -> dict:
    """What slows the PC in this sample, in plain words, with the tools that help."""
    cause: List[dict] = []
    cpu = d.get("cpu") or 0
    top_cpu = [p for p in (d.get("top_cpu") or []) if isinstance(p, dict) and str(p.get("name", "")).lower() not in ("idle", "system idle process")]
    if cpu >= 85:
        primo = top_cpu[0] if top_cpu else {}
        nome = str(primo.get("name", ""))
        motivo = BACKGROUND.get(nome.lower())
        cause.append({"level": "error", "title": f"The processor is at {cpu:.0f}%",
                      "detail": (f"{nome} uses {primo.get('cpu', 0):.0f}% of it" + (f": {motivo}. It usually ends by itself." if motivo else ".")) if nome else "",
                      "tools": ["performance.top_processes"]})
    totale, libera = d.get("mem_total_mb") or 0, d.get("mem_free_mb") or 0
    if totale and libera / totale < 0.10:
        primo = (d.get("top_mem") or [{}])[0]
        cause.append({"level": "error", "title": f"Memory is almost full ({libera} MB free of {totale} MB)",
                      "detail": f"{primo.get('name', '?')} uses {primo.get('mem_mb', 0)} MB. Close programs you do not use, or add memory.",
                      "tools": ["performance.memory_report"]})
    if (d.get("disk_busy") or 0) >= 90 or (d.get("disk_queue") or 0) >= 3:
        cause.append({"level": "warning", "title": f"The disk is busy {d.get('disk_busy') or 0:.0f}% of the time",
                      "detail": "Everything waits for the disk: updates, antivirus scans or a slow hard disk. An SSD makes the biggest difference.",
                      "tools": ["storage.disk_speed", "storage.disk_health"]})
    if (d.get("uptime_days") or 0) >= 7:
        cause.append({"level": "warning", "title": f"The PC has not restarted for {d.get('uptime_days'):.0f} days",
                      "detail": "A restart frees memory held by programs and finishes pending updates.", "tools": ["updates.pending_reboot"]})
    if re.search(r"saver|risparmio", str(d.get("power_plan", "")), re.I):
        cause.append({"level": "warning", "title": f"The power plan is {d.get('power_plan')}",
                      "detail": "It slows the processor to save energy. Balanced is the right choice for most PCs.", "tools": ["performance.power_plans_report"]})
    for p in top_cpu[:3]:
        motivo = BACKGROUND.get(str(p.get("name", "")).lower())
        if motivo and cpu < 85 and (p.get("cpu") or 0) >= 15:
            cause.append({"level": "info", "title": motivo[0].upper() + motivo[1:], "detail": f"{p['name']} uses {p['cpu']:.0f}% of the processor.", "tools": []})
    ordine = {"error": 0, "warning": 1, "info": 2}
    cause.sort(key=lambda c: ordine[c["level"]])
    verdetto = cause[0]["title"] if cause else "Nothing is slowing the PC right now"
    return {"sample": d, "causes": cause, "verdict": verdetto, "ok": not any(c["level"] != "info" for c in cause), "at": now()}


def slow_now(runner: Optional[Callable[[], str]] = None) -> dict:
    return explain_slow(crashes.run_json(SCRIPT_SLOW, runner, timeout=60))


# ======================================================================= 2. when the disk will be full

def disk_forecast(punti: List[tuple], oggi: Optional[datetime] = None) -> dict:
    """punti: (iso date, free GB, total GB) of drive C over time. Least squares on the last 90 days."""
    oggi = oggi or datetime.now()
    validi = []
    for quando, libero, totale in punti:
        try:
            t = datetime.fromisoformat(str(quando)[:19])
        except ValueError:
            continue
        if libero is not None and (oggi - t).days <= 90:
            validi.append(((t - oggi).total_seconds() / 86400, float(libero), float(totale or 0)))
    validi.sort()
    esito: dict = {"points": [{"days_ago": round(-x, 1), "free_gb": round(y, 1)} for x, y, _ in validi], "free_gb": validi[-1][1] if validi else None,
             "total_gb": validi[-1][2] if validi else None, "per_month_gb": None, "full_on": None, "days": None}
    if len(validi) < 3 or validi[-1][0] - validi[0][0] < 3:
        esito["reason"] = "Not enough history yet: the forecast needs scans on at least 3 different days."
        return esito
    n = len(validi)
    mx = sum(x for x, _, _ in validi) / n
    my = sum(y for _, y, _ in validi) / n
    den = sum((x - mx) ** 2 for x, _, _ in validi)
    pendenza = sum((x - mx) * (y - my) for x, y, _ in validi) / den if den else 0.0
    esito["per_month_gb"] = round(pendenza * 30, 2)
    if pendenza >= -0.01:
        esito["reason"] = "The free space is stable or growing."
        return esito
    giorni = int(validi[-1][1] / -pendenza)
    esito["days"] = giorni
    esito["full_on"] = (oggi + timedelta(days=giorni)).date().isoformat()
    return esito


# ======================================================================= 3-5. folder map, duplicates, forgotten files

USER_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def default_folders(casa: Optional[Path] = None) -> List[Path]:
    casa = casa or user_home()
    return [casa / c for c in USER_FOLDERS if (casa / c).is_dir()]


def _safe_dir(percorso: str) -> Path:
    p = Path(percorso)
    if not p.is_absolute() or str(p).startswith("\\\\") or not p.is_dir():
        raise ValueError("A folder on a drive of this PC.")
    return p


def folder_map(percorso: str = "", limite_secondi: float = 20.0) -> dict:
    """Size of every subfolder of a folder (one level, sizes include everything below), for the treemap."""
    radice = _safe_dir(percorso) if percorso else user_home()
    fine = time.monotonic() + limite_secondi
    troncato = False

    def peso(p: str) -> tuple:
        nonlocal troncato
        totale, file = 0, 0
        pila = [p]
        while pila:
            if time.monotonic() > fine:
                troncato = True
                break
            corrente = pila.pop()
            try:
                with os.scandir(corrente) as voci:
                    for v in voci:
                        try:
                            if v.is_symlink():
                                continue
                            if v.is_dir(follow_symlinks=False):
                                pila.append(v.path)
                            else:
                                totale += v.stat(follow_symlinks=False).st_size
                                file += 1
                        except OSError:
                            continue
            except OSError:
                continue
        return totale, file

    figli, sciolti, n_sciolti = [], 0, 0
    try:
        voci = list(os.scandir(radice))
    except OSError as e:
        raise ValueError(f"The folder cannot be read: {e}") from None
    for v in voci:
        try:
            if v.is_symlink():
                continue
            if v.is_dir(follow_symlinks=False):
                b, f = peso(v.path)
                figli.append({"name": v.name, "path": v.path, "bytes": b, "files": f})
            else:
                sciolti += v.stat(follow_symlinks=False).st_size
                n_sciolti += 1
        except OSError:
            continue
    figli.sort(key=lambda x: -x["bytes"])
    return {"path": str(radice), "parent": str(radice.parent) if radice.parent != radice else None, "children": figli,
            "files_bytes": sciolti, "files": n_sciolti, "total": sciolti + sum(c["bytes"] for c in figli), "truncated": troncato}


def _walk(cartelle: Iterable[Path], limite: int = 50000):
    n = 0
    for c in cartelle:
        for radice, dirs, files in os.walk(c):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "AppData")]
            for f in files:
                n += 1
                if n > limite:
                    return
                yield os.path.join(radice, f)


def _hash(percorso: str, inizio_solo: bool) -> Optional[str]:
    h = hashlib.sha256()
    try:
        with open(percorso, "rb") as f:
            if inizio_solo:
                h.update(f.read(65536))
            else:
                for blocco in iter(lambda: f.read(1 << 20), b""):
                    h.update(blocco)
    except OSError:
        return None
    return h.hexdigest()


def duplicates(cartelle: Optional[List[Path]] = None, minimo: int = 1 << 20, limite: int = 50000) -> dict:
    """Identical files (same size, same start, same content) in the user's folders, the largest waste first."""
    cartelle = cartelle or default_folders()
    per_dim: Dict[int, List[str]] = {}
    for p in _walk(cartelle, limite):
        try:
            d = os.path.getsize(p)
        except OSError:
            continue
        if d >= minimo:
            per_dim.setdefault(d, []).append(p)
    gruppi: List[dict] = []
    for dim, elenco in per_dim.items():
        if len(elenco) < 2:
            continue
        inizi: Dict[str, List[str]] = {}
        for p in elenco:
            h = _hash(p, True)
            if h:
                inizi.setdefault(h, []).append(p)
        for simili in inizi.values():
            if len(simili) < 2:
                continue
            pieni: Dict[str, List[str]] = {}
            for p in simili:
                h = _hash(p, False)
                if h:
                    pieni.setdefault(h, []).append(p)
            for uguali in pieni.values():
                if len(uguali) > 1:
                    file = sorted(({"path": p, "modified": datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")} for p in uguali),
                                  key=lambda x: x["modified"])
                    gruppi.append({"size": dim, "files": file, "waste": dim * (len(uguali) - 1)})
    gruppi.sort(key=lambda g: -g["waste"])
    return {"groups": gruppi[:300], "waste": sum(g["waste"] for g in gruppi), "folders": [str(c) for c in cartelle]}


def forgotten(cartelle: Optional[List[Path]] = None, minimo: int = 100 << 20, giorni: int = 365, oggi: Optional[float] = None) -> dict:
    """Large files nobody opened or changed for a long time."""
    soglia = (oggi or time.time()) - giorni * 86400
    trovati = []
    for p in _walk(cartelle or default_folders()):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size >= minimo and max(st.st_atime, st.st_mtime) < soglia:
            trovati.append({"path": p, "size": st.st_size, "last": datetime.fromtimestamp(max(st.st_atime, st.st_mtime)).date().isoformat()})
    trovati.sort(key=lambda f: -f["size"])
    return {"files": trovati[:500], "total": sum(f["size"] for f in trovati), "days": giorni}


def recycle(percorsi: List[str], ammessi: Optional[List[Path]] = None, preview: bool = False, runner=None) -> dict:
    """Moves files of the user's folders to the Recycle Bin (they can be put back from there)."""
    radici = [os.path.normcase(str(p.resolve())) + os.sep for p in (ammessi or default_folders())]
    validi, rifiutati = [], []
    for p in percorsi if isinstance(percorsi, list) else []:
        if not isinstance(p, str):
            continue
        try:
            reale = os.path.normcase(str(Path(p).resolve()))
        except OSError:
            rifiutati.append(p)
            continue
        if any(reale.startswith(r) for r in radici) and os.path.isfile(reale):
            validi.append(str(Path(p).resolve()))
        else:
            rifiutati.append(p)
    if preview or not validi:
        return {"moved": 0, "would_move": len(validi), "refused": rifiutati, "preview": preview}
    # The paths travel as base64 JSON: data, never script text (a name with a typographic quote cannot break out).
    elenco = base64.b64encode(json.dumps(validi[:500]).encode("utf-8")).decode("ascii")
    script = ("Add-Type -AssemblyName Microsoft.VisualBasic; $ok = 0; $l = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + elenco + "')) | ConvertFrom-Json; "
              "foreach ($f in @($l)) { try { "
              "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($f, 'OnlyErrorDialogs', 'SendToRecycleBin'); $ok++ } catch {} }; "
              "[ordered]@{ moved = $ok } | ConvertTo-Json -Compress")
    r = crashes.run_json(script, runner, timeout=300)
    return {"moved": int(r.get("moved") or 0), "refused": rifiutati, "preview": False}


# ======================================================================= 6. recent installs

def recent_installs(elenco_app: List[dict], giorni: int = 30, oggi: Optional[date] = None) -> List[dict]:
    oggi = oggi or date.today()
    fuori: List[dict] = []
    for a in elenco_app:
        try:
            d = date.fromisoformat(str(a.get("installed") or "")[:10])
        except ValueError:
            continue
        eta = (oggi - d).days
        if 0 <= eta <= giorni:
            fuori.append({"id": a.get("id"), "name": a.get("name"), "version": a.get("version"), "publisher": a.get("publisher"),
                          "installed": d.isoformat(), "days": eta, "status": a.get("status"), "size_mb": a.get("size_mb")})
    fuori.sort(key=lambda x: x["installed"], reverse=True)
    return fuori


# ======================================================================= 9. risky browser extensions

RISKY = {"<all_urls>": (3, "reads and changes every website"), "*://*/*": (3, "reads and changes every website"),
         "http://*/*": (3, "reads and changes every website"), "https://*/*": (3, "reads and changes every website"),
         "debugger": (3, "can control the browser like a developer tool"), "proxy": (3, "can route your traffic elsewhere"),
         "management": (3, "can turn other extensions on and off"), "nativeMessaging": (2, "talks to programs on the PC"),
         "webRequest": (2, "sees every request the browser makes"), "webRequestBlocking": (2, "can block or change requests"),
         "cookies": (2, "reads the cookies of websites (sign-ins)"), "history": (2, "reads the browsing history"),
         "clipboardRead": (2, "reads what you copy"), "privacy": (2, "changes privacy settings"), "desktopCapture": (2, "can record the screen"),
         "downloads": (1, "manages downloads"), "tabs": (1, "sees the open tabs"), "scripting": (1, "injects scripts into pages")}
BROWSERS = {"Chrome": r"Google\Chrome\User Data", "Edge": r"Microsoft\Edge\User Data", "Brave": r"BraveSoftware\Brave-Browser\User Data"}


def score_extension(permessi: List[str]) -> dict:
    motivi, punti = [], 0
    for p in permessi:
        voce = RISKY.get(p) or (RISKY["<all_urls>"] if isinstance(p, str) and re.fullmatch(r"(\*|https?)://\*/\*", p) else None)
        if voce and voce[1] not in motivi:
            punti += voce[0]
            motivi.append(voce[1])
    livello = "high" if punti >= 6 else "medium" if punti >= 3 else "low"
    return {"score": punti, "level": livello, "reasons": motivi}


def _name(cartella: Path, manifest: dict) -> str:
    nome = str(manifest.get("name") or "")
    m = re.fullmatch(r"__MSG_(\w+)__", nome)
    if m:
        for lingua in (manifest.get("default_locale") or "en", "en", "en_US"):
            try:
                messaggi = json.loads((cartella / "_locales" / lingua / "messages.json").read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            for k, v in messaggi.items():
                if k.lower() == m.group(1).lower() and isinstance(v, dict):
                    return str(v.get("message") or nome)
    return nome


def browser_extensions(local_appdata: Optional[Path] = None) -> List[dict]:
    base = Path(local_appdata or os.environ.get("LOCALAPPDATA") or "")
    fuori: List[dict] = []
    for browser, rel in BROWSERS.items():
        dati = base / rel
        if not dati.is_dir():
            continue
        for profilo in [p for p in dati.iterdir() if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile"))]:
            ext = profilo / "Extensions"
            if not ext.is_dir():
                continue
            for ident in ext.iterdir():
                versioni = sorted([v for v in ident.iterdir() if v.is_dir()], key=lambda v: v.name) if ident.is_dir() else []
                if not versioni:
                    continue
                try:
                    m = json.loads((versioni[-1] / "manifest.json").read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    continue
                permessi = [p for p in list(m.get("permissions") or []) + list(m.get("host_permissions") or []) +
                            [x for cs in (m.get("content_scripts") or []) if isinstance(cs, dict) for x in (cs.get("matches") or [])] if isinstance(p, str)]
                voto = score_extension(permessi)
                fuori.append({"browser": browser, "profile": profilo.name, "id": ident.name, "name": _name(versioni[-1], m),
                              "version": versioni[-1].name, **voto})
    ordine = {"high": 0, "medium": 1, "low": 2}
    fuori.sort(key=lambda e: (ordine[e["level"]], -e["score"], e["name"].lower()))
    return fuori


# ======================================================================= 12. listening ports explained

SCRIPT_PORTS = r"""
$p = @{}; Get-Process | ForEach-Object { $p[$_.Id] = $_.ProcessName }
$l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  [pscustomobject]@{ port = $_.LocalPort; address = $_.LocalAddress; pid = $_.OwningProcess; process = $p[[int]$_.OwningProcess] } }
[ordered]@{ ports = @($l) } | ConvertTo-Json -Depth 3 -Compress
"""
KNOWN_PORTS = {
    21: ("FTP server", "Sends files without encryption.", "high"), 22: ("SSH server", "Remote command line.", "medium"),
    23: ("Telnet", "Remote access without encryption: turn it off.", "high"), 80: ("Web server", "A program publishes web pages.", "medium"),
    135: ("Windows RPC", "Lets Windows components talk to each other. Normal.", "low"),
    139: ("File sharing (NetBIOS)", "Old file sharing.", "medium"), 443: ("Web server (HTTPS)", "A program publishes web pages.", "medium"),
    445: ("File and printer sharing (SMB)", "Normal on office networks; should never be reachable from the internet.", "medium"),
    1433: ("SQL Server", "A database.", "medium"), 1900: ("SSDP / UPnP", "Discovery of devices on the network.", "low"),
    3306: ("MySQL", "A database.", "medium"), 3389: ("Remote Desktop", "Remote access to this PC: keep it only if you use it.", "high"),
    5040: ("Windows service", "Used by Windows. Normal.", "low"), 5357: ("Network discovery (WSD)", "Shows this PC to the network. Normal.", "low"),
    5432: ("PostgreSQL", "A database.", "medium"), 5900: ("VNC", "Remote control of this PC.", "high"),
    5985: ("WinRM (PowerShell remoting)", "Remote management.", "medium"), 5986: ("WinRM over HTTPS", "Remote management.", "medium"),
    7680: ("Delivery Optimization", "Windows Update shares updates with nearby PCs. Normal.", "low"),
    8765: ("Windows Maintenance Manager", "This console (only this PC).", "low"), 8770: ("WMM central server", "The central server of this app.", "low"),
}


def explain_ports(elenco: List[dict]) -> List[dict]:
    fuori: List[dict] = []
    visti: set = set()
    for p in elenco:
        try:
            porta = int(str(p.get("port")))
        except (TypeError, ValueError):
            continue
        indirizzo = str(p.get("address") or "")
        chiave = (porta, p.get("process"))
        if chiave in visti:
            continue
        visti.add(chiave)
        locale = indirizzo in ("127.0.0.1", "::1")
        processo = str(p.get("process") or "")
        nome, testo, rischio = KNOWN_PORTS.get(porta) or (
            ("Windows RPC (dynamic)", "Windows components. Normal.", "low") if 49152 <= porta <= 65535 and processo.lower() in
            ("lsass", "wininit", "services", "spoolsv", "svchost") else ("Program", f"{processo or 'A program'} waits for connections.", "medium"))
        if locale:
            rischio, testo = "low", testo + " Only programs on this PC can reach it."
        fuori.append({"port": porta, "address": indirizzo, "process": processo, "pid": p.get("pid"), "name": nome, "text": testo,
                      "risk": rischio, "local_only": locale})
    ordine = {"high": 0, "medium": 1, "low": 2}
    fuori.sort(key=lambda x: (ordine[x["risk"]], x["port"]))
    return fuori


def listening_ports(runner=None) -> List[dict]:
    return explain_ports(crashes.as_list(crashes.run_json(SCRIPT_PORTS, runner).get("ports")))


# ======================================================================= 11. BitLocker and the recovery key

SCRIPT_BITLOCKER = r"""
$v = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction SilentlyContinue
if (-not $v) { '{"readable": false}'; exit 0 }
[ordered]@{ readable = $true; status = "$($v.ProtectionStatus)"; percent = $v.EncryptionPercentage; method = "$($v.EncryptionMethod)"
  protectors = @($v.KeyProtector | ForEach-Object { "$($_.KeyProtectorType)" }) } | ConvertTo-Json -Compress
"""


def explain_bitlocker(d: dict) -> dict:
    """Whether drive C: is encrypted and whether a recovery key exists, with what to do."""
    if not d.get("readable"):
        return {"state": "unknown", "title": "BitLocker cannot be read", "text": "Restart the console as administrator to read BitLocker.", "key": None}
    protezioni = [str(p) for p in d.get("protectors") or []]
    chiave = "RecoveryPassword" in protezioni
    acceso = str(d.get("status")) in ("On", "1")
    if not acceso:
        return {"state": "off", "title": "Drive C: is not encrypted", "key": chiave, "percent": d.get("percent"),
                "text": "A stolen or lost PC gives away every file. Turn on BitLocker (or Device encryption) and keep the recovery key somewhere safe."}
    if not chiave:
        return {"state": "nokey", "title": "Drive C: is encrypted, but has no recovery key", "key": False, "percent": d.get("percent"),
                "text": "If Windows asks for the key (after a BIOS update or a new motherboard) the data is lost. Add a recovery password and save it."}
    return {"state": "ok", "title": "Drive C: is encrypted and has a recovery key", "key": True, "percent": d.get("percent"), "method": d.get("method"),
            "text": "Make sure the key is saved: in the Microsoft account (account.microsoft.com/devices/recoverykey), in Entra ID or Active Directory, "
                    "or printed and kept away from the PC."}


def bitlocker(runner=None) -> dict:
    return explain_bitlocker(crashes.run_json(SCRIPT_BITLOCKER, runner))


# ======================================================================= 39. end of support of this Windows

# Microsoft lifecycle (as published when 2.12 was made): build -> (name, Home/Pro end, Enterprise/Education end).
WINDOWS_LIFECYCLE = {
    19045: ("Windows 10 22H2", "2025-10-14", "2025-10-14"), 22000: ("Windows 11 21H2", "2023-10-10", "2024-10-08"),
    22621: ("Windows 11 22H2", "2024-10-08", "2025-10-14"), 22631: ("Windows 11 23H2", "2025-11-11", "2026-11-10"),
    26100: ("Windows 11 24H2", "2026-10-13", "2027-10-12"), 26200: ("Windows 11 25H2", "2027-10-12", "2028-10-10"),
}


def windows_support(build: int, edition: str, oggi: Optional[date] = None) -> dict:
    oggi = oggi or date.today()
    impresa = bool(re.search(r"enterprise|education", edition or "", re.I))
    voce = WINDOWS_LIFECYCLE.get(build)
    if voce is None:
        nuova = build > max(WINDOWS_LIFECYCLE)
        return {"build": build, "edition": edition, "name": None, "end": None, "days": None, "status": "unknown" if nuova else "ended",
                "note": "This build is newer than the table of this version of the app (Insider or a new release)." if nuova else
                "This build is out of support: update to a newer version of Windows."}
    fine = date.fromisoformat(voce[2] if impresa else voce[1])
    giorni = (fine - oggi).days
    stato = "ended" if giorni < 0 else "soon" if giorni <= 180 else "ok"
    return {"build": build, "edition": edition, "name": voce[0], "end": fine.isoformat(), "days": giorni, "status": stato,
            "note": "No more security updates: update to a newer version of Windows." if stato == "ended" else
            "Plan the update to a newer version before this date." if stato == "soon" else "Supported."}


def windows_version() -> dict:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            build = int(winreg.QueryValueEx(k, "CurrentBuild")[0])
            edizione = str(winreg.QueryValueEx(k, "EditionID")[0])
    except (OSError, ImportError, ValueError):
        return {"build": 0, "edition": "", "status": "unknown", "note": "The Windows version cannot be read."}
    return windows_support(build, edizione)


# ======================================================================= 14. calendar of the updates

SCRIPT_UPDATES = r"""
$h = @()
try {
  $s = New-Object -ComObject Microsoft.Update.Session; $q = $s.CreateUpdateSearcher(); $n = $q.GetTotalHistoryCount()
  if ($n -gt 0) { $h = $q.QueryHistory(0, [math]::Min($n, 400)) | Where-Object { $_.Operation -eq 1 } | ForEach-Object {
    [pscustomobject]@{ date = $_.Date.ToString('s'); title = $_.Title; result = [int]$_.ResultCode } } }
} catch {}
$f = Get-HotFix -ErrorAction SilentlyContinue | Where-Object InstalledOn | ForEach-Object {
  [pscustomobject]@{ date = $_.InstalledOn.ToString('s'); title = "$($_.HotFixID) $($_.Description)"; result = 2 } }
[ordered]@{ history = @($h); hotfix = @($f) } | ConvertTo-Json -Depth 3 -Compress
"""
RESULTS = {1: "in progress", 2: "installed", 3: "installed with errors", 4: "failed", 5: "cancelled"}


def update_calendar(runner=None) -> dict:
    d = crashes.run_json(SCRIPT_UPDATES, runner, timeout=120)
    visti: set = set()
    voci: List[dict] = []
    for v in crashes.as_list(d.get("history")) + crashes.as_list(d.get("hotfix")):
        trovato = re.search(r"KB\d{6,8}", str(v.get("title", "")))
        kb = trovato.group(0) if trovato else None
        chiave = (kb or v.get("title"), str(v.get("date", ""))[:10])
        if chiave in visti:
            continue
        visti.add(chiave)
        try:
            esito = RESULTS.get(int(v.get("result") or 0), "unknown")
        except (TypeError, ValueError):
            esito = "unknown"
        voci.append({"date": str(v.get("date", ""))[:10], "title": str(v.get("title", ""))[:200], "kb": kb, "result": esito})
    voci.sort(key=lambda v: v["date"], reverse=True)
    mesi: Dict[str, int] = {}
    for v in voci:
        mesi[v["date"][:7]] = mesi.get(v["date"][:7], 0) + 1
    return {"updates": voci, "months": mesi, "failed": sum(1 for v in voci if v["result"] == "failed"), "last": voci[0]["date"] if voci else None}


# ======================================================================= 15. step-by-step internet check

SCRIPT_NET = r"""
$c = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.NetAdapter.Status -eq 'Up' }
[ordered]@{ adapters = @($c | ForEach-Object { [ordered]@{ name = $_.InterfaceAlias; ipv4 = @($_.IPv4Address.IPAddress) -join ','
  gateway = @($_.IPv4DefaultGateway.NextHop) -join ',' } }) } | ConvertTo-Json -Depth 3 -Compress
"""


def _ping(host: str) -> bool:
    try:
        r = subprocess.run(["ping", "-n", "2", "-w", "1500", host], capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0 and "TTL=" in r.stdout.upper()
    except (OSError, subprocess.SubprocessError):
        return False


def _dns(nome: str) -> bool:
    try:
        return bool(socket.getaddrinfo(nome, 443))
    except OSError:
        return False


def _http() -> str:
    try:
        with urllib.request.urlopen("http://www.msftconnecttest.com/connecttest.txt", timeout=6) as r:
            return "ok" if r.read(100).decode("ascii", "replace").strip() == "Microsoft Connect Test" else "portal"
    except OSError:
        return "fail"


def _https() -> bool:
    import ssl
    try:
        with socket.create_connection(("www.microsoft.com", 443), timeout=6) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname="www.microsoft.com"):
                return True
    except OSError:
        return False


def internet_check(adapters: Optional[Callable[[], dict]] = None, ping=_ping, dns=_dns, http=_http, https=_https) -> dict:
    """Checks the connection layer by layer and stops at the first that fails: there is the problem."""
    passi: List[dict] = []

    def passo(nome: str, ok: bool, bene: str, male: str, strumenti: List[str]) -> bool:
        passi.append({"step": nome, "ok": ok, "text": bene if ok else male, "tools": [] if ok else strumenti})
        return ok

    def fine() -> dict:
        ok = all(p["ok"] for p in passi)
        return {"steps": passi, "ok": ok, "verdict": "The connection works." if ok else passi[-1]["text"], "at": now()}
    schede = crashes.as_list((adapters or (lambda: crashes.run_json(SCRIPT_NET)))().get("adapters"))
    if not passo("Network adapter", bool(schede), f"Connected through {', '.join(str(s.get('name', '?')) for s in schede)}.",
                 "No network adapter is connected: check the cable or turn on Wi-Fi.", ["network.restart_adapters", "network.wifi_report"]):
        return fine()
    ips = [ip for s in schede for ip in str(s.get("ipv4") or "").split(",") if ip]
    buoni = [ip for ip in ips if not ip.startswith("169.254.")]
    if not passo("Address (DHCP)", bool(buoni), f"Address {', '.join(buoni)}.",
                 "The router gave no address (169.254.x.x or none): restart the router or renew the address.", ["network.renew_ip", "network.reset_tcpip"]):
        return fine()
    gateway = next((g for s in schede for g in str(s.get("gateway") or "").split(",") if g), "")
    if not passo("Router", bool(gateway) and ping(gateway), f"The router {gateway} answers.",
                 "The router does not answer: restart it, or check the cable or the Wi-Fi signal." if gateway else "No router (gateway) is set.",
                 ["network.renew_ip", "network.restart_adapters"]):
        return fine()
    if not passo("Names (DNS)", dns("www.microsoft.com"), "Website names are found.",
                 "Website names are not found: the DNS does not answer. Clear the DNS cache or use another DNS.",
                 ["network.flush_dns", "network.dns_benchmark", "network.dns_auto"]):
        return fine()
    h = http()
    if not passo("Internet", h == "ok", "Internet answers.",
                 "A sign-in page is in the way (hotel or public Wi-Fi): open a browser and sign in." if h == "portal" else
                 "Internet does not answer: the provider or the router may be down, or a proxy blocks it.",
                 ["network.reset_proxy", "network.ncsi_reset", "network.speed_test"]):
        return fine()
    passo("Secure sites (HTTPS)", https(), "Secure websites open.",
          "Secure websites do not open: check the date and time of the PC, the antivirus web filter or the proxy.", ["network.reset_proxy", "network.winsock_reset"])
    return fine()


# ======================================================================= 8. nightly winget update with exceptions

def winget_upgradable(runner=None) -> List[str]:
    """IDs that winget can upgrade."""
    try:
        testo = runner() if runner else subprocess.run(["winget", "upgrade", "--include-unknown", "--accept-source-agreements"], capture_output=True, text=True,
                                                      timeout=180, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    ids, dentro = [], False
    for riga in (testo or "").splitlines():
        if re.match(r"^-{5,}", riga.strip()):
            dentro = True
            continue
        if dentro:
            for p in riga.split()[1:]:
                if re.fullmatch(r"[A-Za-z0-9][\w\-+]*\.[\w.\-+]+", p) and not re.fullmatch(r"[\d.]+", p):
                    ids.append(p)
                    break
    return sorted(set(ids))


def winget_nightly(ctx, data_dir: Optional[Path] = None) -> Esito:
    from . import appsettings, deploy
    from .watch import DATA_DIR
    esclusi = set(appsettings.load(Path(data_dir or DATA_DIR)).get("winget_exclusions") or [])
    ids = winget_upgradable()
    da_fare = [i for i in ids if i not in esclusi]
    if not da_fare:
        return Esito(Stato.OK, f"Nothing to update ({len(ids)} available, {len(ids) - len(da_fare)} excluded).")
    falliti = []
    for i in da_fare:
        ctx.scrivi(f"Updating {i}…")
        r = deploy.run("update", i, preview=ctx.anteprima)
        if not r.get("ok", True):
            falliti.append(i)
    nota = f"{len(da_fare) - len(falliti)} programs updated, {len(esclusi & set(ids))} excluded" + (f", failed: {', '.join(falliti)}" if falliti else "")
    return Esito(Stato.AVVISO if falliti else Stato.OK, nota)


# ======================================================================= 19. copy of the user's files

def backup_settings_clean(valori: dict) -> dict:
    target = str(valori.get("target") or "").strip()
    if target and not re.fullmatch(r"([A-Za-z]:\\|\\\\[\w.\-]+\\[\w$.\- ]+)[^<>\"|?*]{0,200}", target):
        raise ValueError("The destination is a folder on another disk (E:\\Backup) or on a NAS (\\\\nas\\share).")
    cartelle = valori.get("folders") or ["Documents", "Desktop", "Pictures"]
    if not isinstance(cartelle, list) or any(c not in USER_FOLDERS for c in cartelle):
        raise ValueError("Folders: " + ", ".join(USER_FOLDERS) + ".")
    casa = os.path.normcase(str(user_home()))
    if target and os.path.normcase(target).startswith(casa):
        raise ValueError("The copy must go to another disk or to a NAS, not inside your own folders.")
    return {"target": target, "folders": cartelle}


def user_backup(ctx, data_dir: Optional[Path] = None) -> Esito:
    from . import appsettings
    from .watch import DATA_DIR
    cartella_dati = Path(data_dir or DATA_DIR)
    s = appsettings.load(cartella_dati).get("file_backup") or {}
    if not s.get("target"):
        return Esito(Stato.AVVISO, "No destination set: Settings › Backup of your files.")
    destinazione = os.path.join(s["target"], socket.gethostname())
    if not ctx.anteprima and not os.path.isdir(s["target"]):
        _write_json(cartella_dati / "file_backup_status.json", {"at": now(), "ok": False, "detail": "destination not reachable"})
        return Esito(Stato.ERRORE, f"{s['target']} is not reachable: connect the disk or the NAS.")
    errori = 0
    for nome in s.get("folders") or ["Documents", "Desktop", "Pictures"]:
        sorgente = user_home() / nome
        if not sorgente.is_dir():
            continue
        # robocopy: exit codes below 8 mean success (files copied, extra files, nothing to do).
        e = ctx.comando(["robocopy", str(sorgente), os.path.join(destinazione, nome), "/E", "/XO", "/XJ", "/R:1", "/W:1", "/MT:8", "/NP", "/NFL", "/NDL"],
                        validi=range(8))
        if e.stato not in (Stato.OK, Stato.ANTEPRIMA):
            errori += 1
    if not ctx.anteprima:
        _write_json(cartella_dati / "file_backup_status.json", {"at": now(), "ok": errori == 0,
                                                                 "detail": destinazione + (f" ({errori} folders with errors)" if errori else "")})
    return Esito(Stato.OK if not errori else Stato.AVVISO, f"Files copied to {destinazione}" + (f"; {errori} folders with errors" if errori else ""))


def backup_status(data_dir: Path) -> dict:
    return _json_file(Path(data_dir) / "file_backup_status.json", {})


# ======================================================================= 20. rules "when X happens, run Y"

QUEUE = "automation_queue.json"
RULE_GAP = 1800  # a rule fires at most once every 30 minutes


def clean_rules(regole, catalogo: dict, eventi: Iterable[str]) -> List[dict]:
    if not isinstance(regole, list) or len(regole) > 50:
        raise ValueError("Up to 50 rules.")
    noti = set(eventi)
    fuori = []
    for r in regole:
        if not isinstance(r, dict) or r.get("event") not in noti:
            raise ValueError("Unknown event.")
        azione = catalogo.get(r.get("action_id"))
        if azione is None or azione.risk != "safe" or azione.id.startswith("custom."):
            raise ValueError("A rule runs only safe tools of the catalog.")
        fuori.append({"id": str(r.get("id") or secrets.token_hex(4))[:12], "event": r["event"], "action_id": azione.id, "enabled": bool(r.get("enabled", True))})
    return fuori


def enqueue(data_dir: Path, evento: str) -> None:
    """Called for every alert event (any process): the agent runs the matching rules within a minute."""
    p = Path(data_dir) / QUEUE
    coda = [c for c in _json_file(p, []) if isinstance(c, dict)][-50:] + [{"event": evento, "at": now()}]
    _write_json(p, coda)


def process_rules(data_dir: Path, regole: List[dict], avvia: Callable[[str], None], adesso: Optional[float] = None) -> List[str]:
    """Runs the rules of the queued events; returns the tools started. avvia raises when the agent is busy."""
    p = Path(data_dir) / QUEUE
    coda = _json_file(p, [])
    if not coda:
        return []
    stato_p = Path(data_dir) / "automation_state.json"
    ultimi = _json_file(stato_p, {})
    adesso = adesso or time.time()
    partiti, resto = [], []
    for voce in coda:
        rimasto = False
        for r in [r for r in regole if r.get("enabled") and r.get("event") == voce.get("event")]:
            precedente = ultimi.get(r["id"])
            if precedente is not None and adesso - float(precedente) < RULE_GAP:
                continue
            try:
                avvia(r["action_id"])
            except Exception:  # noqa: BLE001 - busy: try again at the next tick
                rimasto = True
                continue
            ultimi[r["id"]] = adesso
            partiti.append(r["action_id"])
        if rimasto:
            resto.append(voce)
    _write_json(p, resto)
    _write_json(stato_p, ultimi)
    return partiti


# ======================================================================= 26-27. what changed since yesterday, goals

def changes(attuali: Dict[str, Optional[dict]], precedenti: Dict[str, Optional[dict]], esecuzioni: List[dict]) -> dict:
    """attuali / precedenti: the latest scan of every area and the one about a day before."""
    aree = []
    for area, s in attuali.items():
        p = precedenti.get(area)
        if not s or not p:
            continue
        prima = {r.get("title") for r in (p.get("data") or {}).get("recommendations", [])}
        dopo = {r.get("title") for r in (s.get("data") or {}).get("recommendations", [])}
        if s["score"] != p["score"] or dopo - prima or prima - dopo:
            aree.append({"area": area, "before": p["score"], "now": s["score"], "delta": s["score"] - p["score"],
                         "new": sorted(x for x in dopo - prima if x), "solved": sorted(x for x in prima - dopo if x)})
    aree.sort(key=lambda a: a["delta"])
    falliti = [e for e in esecuzioni if e.get("status") == "error"]
    return {"areas": aree, "runs": len(esecuzioni), "failed": [{"action_id": e.get("action_id"), "note": e.get("note")} for e in falliti[:10]],
            "since": min((p["created"] for p in precedenti.values() if p), default=None)}


AREAS = ("cleanup", "integrity", "services", "performance", "storage", "network", "startup", "security", "updates")
METRICS = ("overall", "c_free_pct", "c_free_gb", "open_issues") + tuple(f"area:{a}" for a in AREAS)


def clean_goals(obiettivi) -> List[dict]:
    if not isinstance(obiettivi, list) or len(obiettivi) > 30:
        raise ValueError("Up to 30 goals.")
    fuori = []
    for g in obiettivi:
        if not isinstance(g, dict) or g.get("metric") not in METRICS or g.get("op") not in (">=", "<=") or isinstance(g.get("value"), bool) \
                or not isinstance(g.get("value"), (int, float)):
            raise ValueError("A goal is a metric, >= or <= and a number.")
        fuori.append({"id": str(g.get("id") or secrets.token_hex(4))[:12], "metric": g["metric"], "op": g["op"], "value": g["value"],
                      "enabled": bool(g.get("enabled", True))})
    return fuori


def evaluate_goals(obiettivi: List[dict], valori: Dict[str, Optional[float]]) -> List[dict]:
    fuori = []
    for g in obiettivi:
        v = valori.get(g["metric"])
        ok = None if v is None else (v >= g["value"] if g["op"] == ">=" else v <= g["value"])
        fuori.append(dict(g, current=v, ok=ok))
    return fuori


# ======================================================================= 18. inventory label

def inventory_label(inventario: dict, hostname: str, machine_id: str, asset: str = "") -> dict:
    from . import qrcode
    hw = inventario.get("hardware") or {}
    campi = {"PC": hostname, "Asset": asset, "Maker": hw.get("manufacturer", ""), "Model": hw.get("model", ""), "Serial": hw.get("serial", ""),
             "CPU": hw.get("cpu", ""), "RAM": f"{hw.get('ram_gb')} GB" if hw.get("ram_gb") else "", "Windows": f"{hw.get('os', '')} {hw.get('build', '')}".strip()}
    testo = "WMM\n" + "\n".join(f"{k}: {v}" for k, v in campi.items() if v and k != "CPU") + f"\nID: {machine_id[:12]}"
    return {"fields": {k: v for k, v in campi.items() if v}, "qr": qrcode.svg(testo[:200], 3), "text": testo}


# ======================================================================= 22. diagnostic package

SECRET_KEYS = re.compile(r"secret|password|token|webhook|smtp_pass|api_key|chat_id|url", re.I)


def _redact(v):
    if isinstance(v, dict):
        return {k: ("[removed]" if SECRET_KEYS.search(str(k)) and x not in ("", None, False) else _redact(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_redact(x) for x in v]
    return v


def diagnostic_package(parti: Dict[str, object]) -> bytes:
    """A zip for the technician: one JSON per part, secrets removed."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        indice = []
        for nome, contenuto in parti.items():
            if isinstance(contenuto, str):
                z.writestr(nome, contenuto)
            else:
                z.writestr(nome + ".json", json.dumps(_redact(contenuto), indent=1, ensure_ascii=False, default=str))
            indice.append(nome)
        z.writestr("README.txt", "Windows Maintenance Manager - diagnostic package\nCreated " + now() + "\n\nContents:\n" + "\n".join("- " + i for i in indice) +
                   "\n\nPasswords, tokens, webhook addresses and other secrets were removed.\n")
    return buf.getvalue()


# ======================================================================= 81. temporary delegation of a role

DELEGATIONS = "delegations.json"


def delegations(data_dir: Path) -> List[dict]:
    return [d for d in _json_file(Path(data_dir) / DELEGATIONS, []) if isinstance(d, dict)]


def delegate(acc, data_dir: Path, username: str, role_id: str, ore: int, actor: Optional[dict]) -> dict:
    if isinstance(ore, bool) or not isinstance(ore, int) or not 1 <= ore <= 24 * 30:
        raise ValueError("From 1 hour to 30 days.")
    utente = next((u for u in acc.users() if u["username"].lower() == str(username).lower()), None)
    if utente is None:
        raise ValueError("User not found.")
    elenco = delegations(data_dir)
    if any(d["username"].lower() == utente["username"].lower() for d in elenco):
        raise ValueError("This user already has a temporary role: end it first.")
    chi = (actor or {}).get("username", "local")
    acc.update_user(utente["id"], {"role_id": role_id}, by=chi, actor=actor)
    voce = {"username": utente["username"], "user_id": utente["id"], "role_id": role_id, "previous_role": utente["role_id"],
            "until": (datetime.now() + timedelta(hours=ore)).isoformat(timespec="seconds"), "by": chi, "created": now()}
    _write_json(Path(data_dir) / DELEGATIONS, elenco + [voce])
    acc.audit(chi, "delegation.start", utente["username"], f"{role_id} until {voce['until']}")
    return voce


def end_delegations(acc, data_dir: Path, username: Optional[str] = None, adesso: Optional[datetime] = None) -> List[str]:
    """Puts back the previous role of the delegations that expired (or of one user, ended by hand)."""
    adesso = adesso or datetime.now()
    resto, finiti = [], []
    for d in delegations(data_dir):
        if datetime.fromisoformat(d["until"]) <= adesso or (username and d["username"].lower() == username.lower()):
            try:
                acc.update_user(d["user_id"], {"role_id": d["previous_role"]}, by="system")
                acc.audit("system", "delegation.end", d["username"], f"back to {d['previous_role']}")
            except Exception:  # noqa: BLE001 - user deleted meanwhile: drop the delegation
                pass
            finiti.append(d["username"])
        else:
            resto.append(d)
    if finiti:
        _write_json(Path(data_dir) / DELEGATIONS, resto)
    return finiti


# ======================================================================= 84. access review

def access_review(utenti: List[dict], gettoni: List[dict], revisione: dict, oggi: Optional[datetime] = None) -> dict:
    oggi = oggi or datetime.now()
    voci: List[dict] = []
    for u in utenti:
        motivi = []
        ultimo = u.get("last_login")
        try:
            giorni = (oggi - datetime.fromisoformat(str(ultimo)[:19])).days if ultimo else None
        except ValueError:
            giorni = None
        if u.get("status") == "active":
            if giorni is None:
                motivi.append("never signed in")
            elif giorni > 90:
                motivi.append(f"no sign-in for {giorni} days")
            if u.get("role_id") == "admin" and not u.get("totp_on"):
                motivi.append("administrator without two-step verification")
        voci.append({"username": u.get("username"), "role": u.get("role"), "status": u.get("status"), "last_login": ultimo, "days": giorni,
                     "two_step": bool(u.get("totp_on")), "flags": motivi})
    token = []
    for t in gettoni:
        if t.get("revoked"):
            continue
        try:
            scade = (datetime.fromisoformat(str(t.get("expires"))[:19]) - oggi).days if t.get("expires") else None
        except ValueError:
            scade = None
        if scade is None or scade <= 14 or not t.get("last_used"):
            token.append({"name": t.get("name"), "username": t.get("username"), "expires_in": scade, "last_used": t.get("last_used")})
    return {"users": voci, "flagged": sum(1 for v in voci if v["flags"]), "admins": sum(1 for u in utenti if u.get("role_id") == "admin"),
            "tokens": token, "last_review": revisione}
