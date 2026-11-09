"""Read-only data collection for each area. Errors become entries in `errors`."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import wmm  # noqa: F401
import ottimizza_pc as op

from . import service_audit

GB = 1024 ** 3

CLEANUP_CATEGORIES = {
    "user_temp": ("User temporary files", ["%TEMP%"]),
    "windows_temp": ("Windows temporary files", [r"C:\Windows\Temp"]),
    "update_cache": ("Windows Update download cache", [r"C:\Windows\SoftwareDistribution\Download"]),
    "shader_cache": ("Shader caches",[r"%LOCALAPPDATA%\D3DSCache", r"%LOCALAPPDATA%\NVIDIA\DXCache", r"%LOCALAPPDATA%\NVIDIA\GLCache"]),
    "crash_dumps": ("Application crash dumps", [r"%LOCALAPPDATA%\CrashDumps"]),
}
SYSTEM_DUMPS = ("System crash dumps", list(op.CARTELLE_DUMP))
MEMORY_DUMP = r"C:\Windows\MEMORY.DMP"
SCAN_BUDGET_SECONDS = 20

SERVICE_GROUPS = (
    ("safe", op.SERVIZI_SICURI),
    ("manual", op.SERVIZI_MANUALI),
    ("xbox", op.SERVIZI_XBOX),
    ("print", op.SERVIZI_STAMPA),
)
START_MODES = {"Auto": "auto", "Manual": "demand", "Disabled": "disabled", "Boot": "boot", "System": "system"}

SCRIPT_RECYCLE_BIN = r"""
$t = 0; $n = 0
foreach ($i in (New-Object -ComObject Shell.Application).Namespace(10).Items()) { $t += $i.Size; $n++ }
@{ bytes = [int64]$t; files = $n } | ConvertTo-Json -Compress
"""

SCRIPT_SERVICES = r"""
[ordered]@{
  services = @(Get-CimInstance Win32_Service | ForEach-Object { [ordered]@{ Name = $_.Name; DisplayName = $_.DisplayName; StartMode = "$($_.StartMode)"; State = "$($_.State)"; DelayedAutoStart = [bool]$_.DelayedAutoStart } })
  startup = @(Get-CimInstance Win32_StartupCommand | Select-Object -Unique Name | ForEach-Object Name | Sort-Object)
} | ConvertTo-Json -Depth 4 -Compress
"""


def _powershell(ctx, script: str, errors: List[str], what: str, timeout: int = 180) -> Optional[object]:
    try:
        risultato = ctx.powershell_json(script, timeout)
    except subprocess.TimeoutExpired:
        errors.append(f"{what}: timed out")
        return None
    except (ValueError, OSError) as errore:
        errors.append(f"{what}: {errore}")
        return None
    if risultato is None:
        errors.append(f"{what}: no data returned")
    return risultato


# ---------- system ----------

def translate_system(raw: dict) -> dict:
    sistema = raw.get("sistema") or {}
    memoria = raw.get("memoria") or {}
    stabilita = raw.get("stabilita") or {}
    sicurezza = raw.get("sicurezza") or {}
    gpu = raw.get("gpu") or {}
    return {
        "admin": bool(raw.get("admin")),
        "os": {
            "name": sistema.get("nome"), "build": sistema.get("build"), "cpu": sistema.get("cpu"),
            "board": sistema.get("schedaMadre"), "bios": sistema.get("bios"), "bios_date": sistema.get("dataBios"),
            "bios_age_days": sistema.get("etaBiosGiorni"), "uptime_hours": sistema.get("oreAccensione"),
            "startup_items": sistema.get("vociAvvio"),
        },
        "memory": {"free_gb": memoria.get("liberaGB"), "total_gb": memoria.get("totaleGB")},
        "processes": [{"name": p.get("nome"), "mb": p.get("MB")} for p in op.come_lista(raw.get("processi"))],
        "disks": [{
            "name": d.get("nome"), "media": d.get("tipo"), "health": d.get("salute"), "temperature": d.get("temperatura"),
            "wear": d.get("usura"), "power_on_hours": d.get("oreAccensione"), "read_errors": d.get("erroriLettura"),
        } for d in op.come_lista(raw.get("dischi"))],
        "volumes": [{
            "letter": v.get("lettera"), "free_gb": v.get("liberoGB"), "total_gb": v.get("totaleGB"), "health": v.get("salute"),
        } for v in op.come_lista(raw.get("volumi"))],
        "gpu": {"name": gpu.get("nome"), "driver": gpu.get("driver"), "status": gpu.get("stato")},
        "stability": {
            "unexpected_shutdowns": stabilita.get("spegnimenti") or 0, "whea": stabilita.get("whea") or 0,
            "disk_errors": stabilita.get("disco") or 0, "dumps": stabilita.get("dump") or 0, "dumps_gb": stabilita.get("dumpGB") or 0,
        },
        "security": {
            "defender": sicurezza.get("defender"), "signature_age_days": sicurezza.get("firmeGiorni"),
            "firewall_off": bool(sicurezza.get("firewallSpenti")), "bitlocker": sicurezza.get("bitlocker") or "",
        },
        "reboot_pending": bool(raw.get("riavvioInSospeso")),
        "updates": [str(u) for u in op.come_lista(raw.get("aggiornamenti"))],
    }


def collect_system(ctx) -> dict:
    errori: List[str] = []
    raw = _powershell(ctx, op.SCRIPT_CHECKUP, errori, "System inventory", timeout=240)
    dati = translate_system(raw if isinstance(raw, dict) else {})
    dati["errors"] = errori
    return dati


# ---------- cleanup ----------

REPARSE_POINT = 0x400


def old_files_size(root: str, limit: float, deadline: Optional[float] = None) -> Tuple[int, int, bool]:
    """Same rules as ottimizza_pc.file_da_pulire, but with os.scandir: on Windows the
    directory listing already carries size, time and attributes, so no extra stat calls.
    Stops at `deadline` (time.monotonic) and returns complete=False."""
    bloccati = {nome.lower() for nome in op.ESCLUSI_PULIZIA}
    totale = file = 0
    pila = [root]
    while pila:
        if deadline is not None and time.monotonic() > deadline:
            return totale, file, False
        try:
            voci = os.scandir(pila.pop())
        except OSError:
            continue
        with voci:
            for voce in voci:
                try:
                    info = voce.stat(follow_symlinks=False)
                except OSError:
                    continue
                if voce.is_symlink() or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if voce.name.lower() not in bloccati:
                        pila.append(voce.path)
                elif stat.S_ISREG(info.st_mode) and info.st_mtime < limit:
                    totale += info.st_size
                    file += 1
    return totale, file, True


def measure_folders(categories: Dict[str, List[str]], limit: float, deadline: Optional[float] = None,
                    budget: Optional[float] = None) -> List[dict]:
    """`budget` gives every category its own time limit (a huge %TEMP% must not starve the others)."""
    risultato = []
    for categoria, cartelle in categories.items():
        totale = file = 0
        parziale = False
        if budget is not None:
            deadline = time.monotonic() + budget
        for modello in cartelle:
            radice = os.path.expandvars(modello)
            if "%" in radice or not os.path.isdir(radice):
                continue
            peso, numero, completo = old_files_size(radice, limit, deadline)
            totale += peso
            file += numero
            parziale = parziale or not completo
        risultato.append({"id": categoria, "bytes": totale, "files": file, "partial": parziale})
    return risultato


def collect_cleanup(ctx, system: dict) -> dict:
    errori: List[str] = []
    limite = time.time() - op.GIORNI_FILE_VECCHI * 86400
    categorie = measure_folders({k: v[1] for k, v in CLEANUP_CATEGORIES.items()}, limite, budget=SCAN_BUDGET_SECONDS)
    avvisi: List[str] = []
    for voce in categorie:
        voce["name"] = CLEANUP_CATEGORIES[voce["id"]][0]
        if voce["partial"]:
            # A partial size is still reliable as a minimum: a warning, not a failed scan.
            avvisi.append(f"{voce['name']}: very large folder, measured for {SCAN_BUDGET_SECONDS} s (the value is a minimum)")
    dump = measure_folders({"system_dumps": SYSTEM_DUMPS[1]}, time.time() + 86400)[0]
    try:
        dump["bytes"] += os.path.getsize(MEMORY_DUMP)
        dump["files"] += 1
    except OSError:
        pass
    dump["name"] = SYSTEM_DUMPS[0]
    categorie.append(dump)
    cestino = _powershell(ctx, SCRIPT_RECYCLE_BIN, errori, "Recycle Bin", timeout=60)
    cestino = cestino if isinstance(cestino, dict) else {}
    categorie.append({"id": "recycle_bin", "name": "Recycle Bin", "bytes": int(cestino.get("bytes") or 0), "files": int(cestino.get("files") or 0)})
    return {
        "categories": categorie,
        "recoverable_bytes": sum(c["bytes"] for c in categorie),
        "volumes": system.get("volumes") or [],
        "warnings": avvisi,
        "errors": errori,
    }


# ---------- integrity ----------

def collect_integrity(system: dict, last_checks: Dict[str, dict]) -> dict:
    controlli = {azione: last_checks[azione] for azione in
                 ("integrity.dism", "integrity.sfc", "integrity.disk_scan", "integrity.trim", "integrity.disk_repair")
                 if azione in last_checks}
    return {
        "disks": system.get("disks") or [],
        "volumes": system.get("volumes") or [],
        "stability": system.get("stability") or {},
        "security": system.get("security") or {},
        "reboot_pending": system.get("reboot_pending", False),
        "bios_age_days": (system.get("os") or {}).get("bios_age_days"),
        "bios": (system.get("os") or {}).get("bios"),
        "bios_date": (system.get("os") or {}).get("bios_date"),
        "updates": system.get("updates") or [],
        "checks": controlli,
        "errors": list(system.get("errors") or []),
    }


# ---------- services ----------

def summarize_services(services: List[dict], startup: List[str]) -> dict:
    per_nome = {s.get("Name"): s for s in services}
    totali = {"total": len(services), "auto": 0, "manual": 0, "disabled": 0, "running": 0, "stopped": 0}
    for servizio in services:
        modo = servizio.get("StartMode")
        if modo == "Auto":
            totali["auto"] += 1
        elif modo == "Manual":
            totali["manual"] += 1
        elif modo == "Disabled":
            totali["disabled"] += 1
        if servizio.get("State") == "Running":
            totali["running"] += 1
        elif servizio.get("State") == "Stopped":
            totali["stopped"] += 1
    def avvio_di(servizio: dict) -> str:
        avvio = START_MODES.get(servizio.get("StartMode"), str(servizio.get("StartMode")).lower())
        return "delayed-auto" if avvio == "auto" and servizio.get("DelayedAutoStart") else avvio

    gestiti = []
    for gruppo, nomi in SERVICE_GROUPS:
        for nome in nomi:
            servizio = per_nome.get(nome)
            if servizio is None:
                continue
            gestiti.append({"name": nome, "group": gruppo, "start": avvio_di(servizio), "running": servizio.get("State") == "Running"})
    tutti = sorted(({"name": s.get("Name"), "display": s.get("DisplayName") or s.get("Name"), "start": avvio_di(s),
                     "state": s.get("State"), "protected": s.get("Name") in op.SERVIZI_PROTETTI} for s in services if s.get("Name")),
                   key=lambda s: str(s["display"]).lower())
    return {
        "totals": totali,
        "managed": gestiti,
        "all": tutti,
        "protected_present": sum(1 for nome in op.SERVIZI_PROTETTI if nome in per_nome),
        "startup": list(startup),
    }


def collect_services(ctx) -> dict:
    errori: List[str] = []
    raw = _powershell(ctx, SCRIPT_SERVICES, errori, "Services", timeout=120)
    raw = raw if isinstance(raw, dict) else {}
    dati = summarize_services(op.come_lista(raw.get("services")), [str(s) for s in op.come_lista(raw.get("startup"))])
    try:
        dati["audit"] = service_audit.analyze(ctx.powershell_json(service_audit.SCRIPT, 180))
    except (subprocess.TimeoutExpired, ValueError, OSError) as errore:
        dati["audit"] = service_audit.analyze(None)
        errori.append(f"Service analysis: {errore}")
    try:
        dati["backup_count"] = len(op.leggi_backup())
    except (OSError, json.JSONDecodeError) as errore:
        dati["backup_count"] = 0
        errori.append(f"Service backup: {errore}")
    dati["errors"] = errori
    return dati
