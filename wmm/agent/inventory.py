"""Read-only inventory for the Performance, Storage, Network, Startup & Apps,
Security and Updates areas. Like collectors.py, failures become entries in `errors`."""
from __future__ import annotations

import ctypes
import hashlib
import heapq
import os
import re
import stat
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import wmm  # noqa: F401
import ottimizza_pc as op

from .collectors import _powershell, old_files_size
from .tools import BROWSER_CACHES, THUMBNAIL_CACHE, WER_FOLDERS, expand

GB = 1024 ** 3
PING_COUNT = 4
POWER_PLANS = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "balanced",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "high",
    "a1841308-3bcb-4fda-aec4-e2b56ec2fdaf": "saver",
    "e9a42b02-d5df-448d-aa00-03f14749eb61": "ultimate",
}
STORAGE_BUDGET_SECONDS = 15
REPARSE_POINT = 0x400


# ---------- startup and apps (registry, pure helpers) ----------

def approved_enabled(data: Optional[bytes]) -> bool:
    """StartupApproved values: first byte 2/6 enabled, odd values disabled; missing means enabled."""
    if not data:
        return True
    return data[0] % 2 == 0


def approved_value(enabled: bool, filetime: int) -> bytes:
    if enabled:
        return bytes([2]) + bytes(11)
    return bytes([3, 0, 0, 0]) + int(filetime).to_bytes(8, "little")


def startup_id(scope: str, kind: str, name: str) -> str:
    return hashlib.sha1(f"{scope}|{kind}|{name}".encode("utf-8")).hexdigest()[:16]


def parse_uninstall_entry(values: dict) -> Optional[dict]:
    nome = values.get("DisplayName")
    if not nome or values.get("SystemComponent") == 1 or values.get("ParentKeyName"):
        return None
    data = str(values.get("InstallDate") or "")
    installata = f"{data[:4]}-{data[4:6]}-{data[6:8]}" if re.fullmatch(r"\d{8}", data) else None
    dimensione = values.get("EstimatedSize")
    return {
        "name": str(nome), "publisher": str(values.get("Publisher") or ""), "version": str(values.get("DisplayVersion") or ""),
        "installed": installata, "size_mb": round(dimensione / 1024, 1) if isinstance(dimensione, int) else None,
    }


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
UNINSTALL_KEYS = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _hive(nome: str):
    import winreg
    return {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[nome]


def _values(hive: str, key: str) -> Dict[str, object]:
    import winreg
    valori: Dict[str, object] = {}
    try:
        with winreg.OpenKey(_hive(hive), key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as chiave:
            indice = 0
            while True:
                try:
                    nome, dato, _ = winreg.EnumValue(chiave, indice)
                except OSError:
                    break
                valori[nome] = dato
                indice += 1
    except OSError:
        pass
    return valori


def startup_sources() -> List[dict]:
    """Where startup entries live and where Windows stores their enabled state."""
    return [
        {"scope": "HKCU", "kind": "Run", "location": "Registry (current user)", "key": RUN_KEY, "approved": ("HKCU", APPROVED_KEY + r"\Run")},
        {"scope": "HKLM", "kind": "Run", "location": "Registry (all users)", "key": RUN_KEY, "approved": ("HKLM", APPROVED_KEY + r"\Run")},
        {"scope": "HKLM", "kind": "Run32", "location": "Registry (all users, 32-bit)",
         "key": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "approved": ("HKLM", APPROVED_KEY + r"\Run32")},
        {"scope": "HKCU", "kind": "StartupFolder", "location": "Startup folder (current user)",
         "folder": os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"), "approved": ("HKCU", APPROVED_KEY + r"\StartupFolder")},
        {"scope": "HKLM", "kind": "StartupFolder", "location": "Startup folder (all users)",
         "folder": os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp"), "approved": ("HKLM", APPROVED_KEY + r"\StartupFolder")},
    ]


def startup_items() -> List[dict]:
    voci = []
    for fonte in startup_sources():
        approvati = _values(*fonte["approved"])
        if "folder" in fonte:
            try:
                nomi = [n for n in os.listdir(fonte["folder"]) if n.lower() != "desktop.ini"]
            except OSError:
                nomi = []
            elementi = [(n, os.path.join(fonte["folder"], n)) for n in nomi]
        else:
            elementi = [(n, str(v)) for n, v in _values(fonte["scope"], fonte["key"]).items() if n]
        for nome, comando in elementi:
            dato = approvati.get(nome)
            voci.append({
                "id": startup_id(fonte["scope"], fonte["kind"], nome), "name": nome, "command": comando,
                "location": fonte["location"], "scope": fonte["scope"], "kind": fonte["kind"],
                "enabled": approved_enabled(dato if isinstance(dato, bytes) else None),
            })
    return sorted(voci, key=lambda v: v["name"].lower())


# Startup entries that must keep running: security, hardware drivers, VPN, management agents, backup, passwords.
ESSENTIAL_STARTUP = (
    "securityhealth", "windowsdefender", "msmpeng", "defender", "avast", "avg", "eset", "egui", "kaspersky", "avp", "bitdefender", "norton",
    "mcafee", "sophos", "malwarebytes", "trend micro", "webroot", "sentinel", "crowdstrike", "cylance", "panda", "f-secure", "gdata",
    "realtek", "rtkaud", "rthdvcpl", "nahimic", "waves", "maxxaudio", "dolby", "conexant", "synaptics", "syntp", "elan", "etdctrl", "alps",
    "precision touchpad", "wacom", "igfx", "hotkey", "fnkey", "bluetooth", "btsw",
    "anyconnect", "vpnui", "forticlient", "fortitray", "globalprotect", "pangpa", "openvpn", "wireguard", "zscaler", "netskope",
    "ninjarmm", "kaseya", "datto", "connectwise", "screenconnect", "intune", "sccm", "ccmexec", "lansweeper", "veeam", "acronis",
    "keepass", "1password", "bitwarden", "lastpass", "dashlane", "ctfmon",
    # peripheral control software (devices stop working as configured without it) and anti-cheat
    "elgato", "streamdeck", "stream deck", "wavelink", "wave link", "sd plugin", "razer", "lghub", "logioptions", "logi options",
    "icue", "corsair", "armoury", "steelseries", "vanguard", "vgtray",
)


def is_essential_startup(item: dict) -> bool:
    testo = f"{item.get('name', '')} {item.get('command', '')}".lower()
    return any(chiave in testo for chiave in ESSENTIAL_STARTUP)


def set_startup_enabled(item: dict, enabled: bool) -> None:
    """Same mechanism as Task Manager › Startup apps: the entry stays, Windows skips it."""
    import winreg
    fonte = [f for f in startup_sources() if f["scope"] == item["scope"] and f["kind"] == item["kind"]][0]
    hive, chiave = fonte["approved"]
    # FILETIME: 100 ns intervals since 1601-01-01.
    adesso = int((time.time() + 11644473600) * 10_000_000)
    with winreg.CreateKeyEx(_hive(hive), chiave, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as handle:
        winreg.SetValueEx(handle, item["name"], 0, winreg.REG_BINARY, approved_value(enabled, adesso))


def installed_apps() -> List[dict]:
    import winreg
    app: Dict[Tuple[str, str], dict] = {}
    for hive, chiave in UNINSTALL_KEYS:
        try:
            radice = winreg.OpenKey(_hive(hive), chiave, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue
        with radice:
            indice = 0
            while True:
                try:
                    sotto = winreg.EnumKey(radice, indice)
                except OSError:
                    break
                indice += 1
                voce = parse_uninstall_entry(_values(hive, chiave + "\\" + sotto))
                if voce:
                    app[(voce["name"], voce["version"])] = voce
    return sorted(app.values(), key=lambda a: a["name"].lower())


SCRIPT_TASKS = r"""
@(Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' -and $_.TaskPath -notlike '\WindowsMaintenanceManager\*' } | ForEach-Object {
  [ordered]@{ name = $_.TaskName; path = $_.TaskPath; state = "$($_.State)"; author = "$($_.Author)" } }) | ConvertTo-Json -Depth 3 -Compress
"""


def collect_startup(ctx) -> dict:
    errori: List[str] = []
    try:
        voci = startup_items()
    except OSError as errore:
        voci = []
        errori.append(f"Startup entries: {errore}")
    try:
        app = installed_apps()
    except OSError as errore:
        app = []
        errori.append(f"Installed applications: {errore}")
    attivita = _powershell(ctx, SCRIPT_TASKS, errori, "Scheduled tasks", timeout=90)
    return {"items": voci, "apps": app, "tasks": op.come_lista(attivita), "errors": errori}


# ---------- performance ----------

def parse_power_scheme(text: str) -> Optional[dict]:
    trovato = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*\(([^)]*)\)", text or "", re.I)
    if not trovato:
        return None
    guid = trovato.group(1).lower()
    return {"guid": guid, "name": trovato.group(2).strip(), "plan": POWER_PLANS.get(guid, "custom")}


SCRIPT_PERFORMANCE = r"""
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
function Reg($p, $n) { (Get-ItemProperty -Path $p -Name $n -ErrorAction SilentlyContinue).$n }
[ordered]@{
  cpu = [ordered]@{ name = "$($cpu.Name)".Trim(); cores = $cpu.NumberOfCores; logical = $cpu.NumberOfLogicalProcessors; clock_mhz = $cpu.MaxClockSpeed; load = $cpu.LoadPercentage }
  modules = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object { [ordered]@{ capacity_gb = [math]::Round($_.Capacity / 1GB, 1); speed = $_.ConfiguredClockSpeed; manufacturer = "$($_.Manufacturer)".Trim(); slot = "$($_.DeviceLocator)" } })
  pagefile_automatic = [bool]$cs.AutomaticManagedPagefile
  pagefiles = @(Get-CimInstance Win32_PageFileUsage | ForEach-Object { [ordered]@{ name = $_.Name; allocated_mb = $_.AllocatedBaseSize; current_mb = $_.CurrentUsage; peak_mb = $_.PeakUsage } })
  power = "$(powercfg /getactivescheme)"
  visual_effects = Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects' 'VisualFXSetting'
  fast_startup = Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' 'HiberbootEnabled'
  game_dvr = Reg 'HKCU:\System\GameConfigStore' 'GameDVR_Enabled'
  battery = [bool](Get-CimInstance Win32_Battery)
  battery_charge = (Get-CimInstance Win32_Battery | Select-Object -First 1).EstimatedChargeRemaining
  battery_designed = (Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue | Select-Object -First 1).DesignedCapacity
  battery_full = (Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue | Select-Object -First 1).FullChargedCapacity
  by_memory = @(Get-Process | Group-Object ProcessName | ForEach-Object { [ordered]@{ name = $_.Name; mb = [int](($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB); count = $_.Count } } | Sort-Object { $_.mb } -Descending | Select-Object -First 10)
  by_cpu = @(Get-Process | Where-Object CPU | Group-Object ProcessName | ForEach-Object { [ordered]@{ name = $_.Name; seconds = [math]::Round(($_.Group | Measure-Object CPU -Sum).Sum, 1) } } | Sort-Object { $_.seconds } -Descending | Select-Object -First 10)
} | ConvertTo-Json -Depth 4 -Compress
"""


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory_status() -> dict:
    stato = MEMORYSTATUSEX()
    stato.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato))
    commit_totale = stato.ullTotalPageFile or 1
    return {
        "total_gb": round(stato.ullTotalPhys / GB, 1), "free_gb": round(stato.ullAvailPhys / GB, 1),
        "load_pct": int(stato.dwMemoryLoad),
        "commit_limit_gb": round(stato.ullTotalPageFile / GB, 1),
        "commit_used_gb": round((stato.ullTotalPageFile - stato.ullAvailPageFile) / GB, 1),
        "commit_pct": int(round(100 * (commit_totale - stato.ullAvailPageFile) / commit_totale)),
    }


def battery_health(designed: Optional[int], full: Optional[int]) -> Optional[int]:
    """Full charge capacity as a percentage of the design capacity (wear)."""
    if not designed or full is None:
        return None
    return min(100, int(round(100 * full / designed)))


def collect_performance(ctx, system: dict) -> dict:
    errori: List[str] = []
    raw = _powershell(ctx, SCRIPT_PERFORMANCE, errori, "Performance inventory", timeout=120)
    raw = raw if isinstance(raw, dict) else {}
    memoria = memory_status()
    memoria["modules"] = op.come_lista(raw.get("modules"))
    bool_or_none = lambda v: None if v is None else bool(v)  # noqa: E731
    return {
        "cpu": raw.get("cpu") or {},
        "memory": memoria,
        "pagefile": {"automatic": bool(raw.get("pagefile_automatic")), "files": op.come_lista(raw.get("pagefiles"))},
        "power": parse_power_scheme(raw.get("power") or "") or {"plan": "unknown", "name": "Unknown", "guid": ""},
        "visual_effects": raw.get("visual_effects"),
        "fast_startup": bool_or_none(raw.get("fast_startup")),
        "game_dvr": bool_or_none(raw.get("game_dvr")),
        "battery": bool(raw.get("battery")),
        "battery_info": {"charge_pct": raw.get("battery_charge"),
                         "designed_mwh": raw.get("battery_designed"), "full_mwh": raw.get("battery_full"),
                         "health_pct": battery_health(raw.get("battery_designed"), raw.get("battery_full"))} if raw.get("battery") else None,
        "uptime_hours": (system.get("os") or {}).get("uptime_hours"),
        "processes": {"memory": op.come_lista(raw.get("by_memory")), "cpu": op.come_lista(raw.get("by_cpu"))},
        "errors": errori,
    }


# ---------- storage ----------

def scan_tree(root: str, deadline: float, top_n: int = 15) -> dict:
    """Size of each first-level folder of `root` plus the largest files, within `deadline`."""
    cartelle: Dict[str, dict] = {}
    grandi: List[Tuple[int, str]] = []
    completo = True
    try:
        voci = list(os.scandir(root))
    except OSError:
        return {"folders": [], "files": [], "complete": True}
    pila: List[Tuple[str, Optional[str]]] = []
    for voce in voci:
        try:
            info = voce.stat(follow_symlinks=False)
        except OSError:
            continue
        if voce.is_symlink() or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
            continue
        if stat.S_ISDIR(info.st_mode):
            cartelle[voce.name] = {"name": voce.name, "path": voce.path, "bytes": 0, "files": 0}
            pila.append((voce.path, voce.name))
        elif stat.S_ISREG(info.st_mode):
            heapq.heappush(grandi, (info.st_size, voce.path))
            if len(grandi) > top_n:
                heapq.heappop(grandi)
    while pila:
        if time.monotonic() > deadline:
            completo = False
            break
        percorso, primo = pila.pop()
        try:
            iteratore = os.scandir(percorso)
        except OSError:
            continue
        with iteratore:
            for voce in iteratore:
                try:
                    info = voce.stat(follow_symlinks=False)
                except OSError:
                    continue
                if voce.is_symlink() or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    pila.append((voce.path, primo))
                elif stat.S_ISREG(info.st_mode):
                    cartelle[primo]["bytes"] += info.st_size
                    cartelle[primo]["files"] += 1
                    heapq.heappush(grandi, (info.st_size, voce.path))
                    if len(grandi) > top_n:
                        heapq.heappop(grandi)
    return {
        "folders": sorted(cartelle.values(), key=lambda c: c["bytes"], reverse=True),
        "files": [{"path": p, "bytes": b} for b, p in sorted(grandi, reverse=True)],
        "complete": completo,
    }


def _size_of(targets: List[Tuple[str, Optional[str]]]) -> Tuple[int, int]:
    from .tools import wipe
    totale, file, _ = wipe(targets, preview=True)
    return totale, file


SCRIPT_STORAGE = r"""
[ordered]@{
  shadow = @(Get-CimInstance Win32_ShadowStorage | ForEach-Object {
    $v = Get-CimInstance Win32_Volume | Where-Object DeviceID -eq $_.Volume.DeviceID
    [ordered]@{ volume = "$($v.DriveLetter)"; used_gb = [math]::Round($_.UsedSpace / 1GB, 1); allocated_gb = [math]::Round($_.AllocatedSpace / 1GB, 1); max_gb = [math]::Round($_.MaxSpace / 1GB, 1) } })
  storage_sense = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy' -Name '01' -ErrorAction SilentlyContinue).'01'
} | ConvertTo-Json -Depth 4 -Compress
"""


def collect_storage(ctx, system: dict, last_checks: Dict[str, dict]) -> dict:
    errori: List[str] = []
    avvisi: List[str] = []
    categorie = []
    for ident, nome, obiettivi in (
        ("browser_cache", "Browser caches", [(p, None) for p in expand(BROWSER_CACHES)]),
        ("wer", "Windows Error Reporting", [(p, None) for p in expand(WER_FOLDERS)]),
        ("thumbnails", "Thumbnail cache", [(os.path.expandvars(THUMBNAIL_CACHE[0]), THUMBNAIL_CACHE[1])]),
    ):
        totale, numero = _size_of(obiettivi)
        categorie.append({"id": ident, "name": nome, "bytes": totale, "files": numero})
    profilo = scan_tree(os.path.expandvars("%USERPROFILE%"), time.monotonic() + STORAGE_BUDGET_SECONDS)
    if not profilo["complete"]:
        avvisi.append(f"User profile: very large, measured for {STORAGE_BUDGET_SECONDS} s (sizes are a minimum)")
    vecchio = None
    if os.path.isdir(r"C:\Windows.old"):
        vecchio, _, completo = old_files_size(r"C:\Windows.old", time.time() + 86400, time.monotonic() + 5)
        if not completo:
            avvisi.append("Windows.old: measured for 5 s (size is a minimum)")
    raw = _powershell(ctx, SCRIPT_STORAGE, errori, "Storage settings", timeout=60)
    raw = raw if isinstance(raw, dict) else {}
    senso = raw.get("storage_sense")
    return {
        "categories": categorie,
        "folders": profilo["folders"][:12],
        "files": profilo["files"],
        "profile_complete": profilo["complete"],
        "windows_old_bytes": vecchio or 0,
        "shadow": op.come_lista(raw.get("shadow")),
        "storage_sense": None if senso is None else bool(senso),
        "volumes": system.get("volumes") or [],
        "disks": system.get("disks") or [],
        "checks": {k: v for k, v in last_checks.items() if k.startswith("storage.")},
        "warnings": avvisi,
        "errors": errori,
    }


# ---------- network ----------

SCRIPT_NETWORK = r"""
function Ping($ip) { ,@(Test-Connection -ComputerName $ip -Count 4 -ErrorAction SilentlyContinue | ForEach-Object { $_.ResponseTime }) }
$gw = (Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4DefaultGateway.NextHop
$dns = Measure-Command { $script:ok = Resolve-DnsName 'www.microsoft.com' -DnsOnly -ErrorAction SilentlyContinue }
[ordered]@{
  adapters = @(Get-NetAdapter -Physical | ForEach-Object {
    $c = Get-NetIPConfiguration -InterfaceIndex $_.ifIndex -ErrorAction SilentlyContinue
    [ordered]@{ name = $_.Name; description = $_.InterfaceDescription; status = "$($_.Status)"; speed = "$($_.LinkSpeed)"; mac = $_.MacAddress; media = "$($_.PhysicalMediaType)"
      ipv4 = @($c.IPv4Address.IPAddress); gateway = @($c.IPv4DefaultGateway.NextHop); dns = @($c.DNSServer | Where-Object AddressFamily -eq 2 | ForEach-Object ServerAddresses) } })
  routerAddress = "$gw"
  router = if ($gw) { Ping $gw } else { @() }
  cloudflare = Ping '1.1.1.1'
  google = Ping '8.8.8.8'
  dnsMs = [int]$dns.TotalMilliseconds
  dnsOk = [bool]$script:ok
  connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue).Count
} | ConvertTo-Json -Depth 4 -Compress
"""


def link_speed_mbps(text: str) -> Optional[int]:
    trovato = re.match(r"\s*([\d.]+)\s*([KMG])bps", text or "", re.I)
    if not trovato:
        return None
    fattore = {"K": 0.001, "M": 1, "G": 1000}[trovato.group(2).upper()]
    return int(round(float(trovato.group(1)) * fattore))


def summarize_network(raw: dict) -> dict:
    schede = []
    for scheda in op.come_lista(raw.get("adapters")):
        schede.append({
            "name": scheda.get("name"), "description": scheda.get("description"), "status": scheda.get("status"),
            "speed": scheda.get("speed"), "speed_mbps": link_speed_mbps(scheda.get("speed") or ""), "mac": scheda.get("mac"),
            "media": scheda.get("media"), "ipv4": op.come_lista(scheda.get("ipv4")), "gateway": op.come_lista(scheda.get("gateway")),
            "dns": op.come_lista(scheda.get("dns")),
        })
    destinazioni = []
    for nome, chiave, indirizzo in (("Router", "router", raw.get("routerAddress") or ""), ("Cloudflare", "cloudflare", "1.1.1.1"), ("Google", "google", "8.8.8.8")):
        if chiave == "router" and not indirizzo:
            continue
        tempi = [float(t) for t in op.come_lista(raw.get(chiave)) if t is not None]
        s = op.statistiche_ping(tempi, PING_COUNT)
        destinazioni.append({"name": nome, "address": indirizzo, "avg": s["media"], "max": s["massimo"], "jitter": s["jitter"],
                             "lost": int(s["persi"]), "sent": PING_COUNT, "samples": tempi})
    return {"adapters": schede, "targets": destinazioni, "dns_ms": raw.get("dnsMs"), "dns_ok": bool(raw.get("dnsOk")),
            "connections": raw.get("connections")}


def collect_network(ctx) -> dict:
    errori: List[str] = []
    raw = _powershell(ctx, SCRIPT_NETWORK, errori, "Network test", timeout=120)
    dati = summarize_network(raw if isinstance(raw, dict) else {})
    dati["errors"] = errori
    return dati


# ---------- extra settings read from the registry ----------

def _reg(hive: str, key: str, name: str):
    import winreg
    try:
        with winreg.OpenKey(_hive(hive), key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as chiave:
            return winreg.QueryValueEx(chiave, name)[0]
    except OSError:
        return None


def parse_hosts(text: str) -> List[str]:
    """Active hosts file entries, without comments and the default localhost lines."""
    voci = []
    for riga in (text or "").splitlines():
        riga = riga.split("#", 1)[0].strip()
        parti = riga.split()
        if len(parti) < 2 or parti[1].lower() == "localhost":
            continue
        voci.append(" ".join(parti[:2]))
    return voci


def _read_hosts() -> List[str]:
    try:
        with open(os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts"), encoding="utf-8", errors="replace") as file:
            return parse_hosts(file.read())
    except OSError:
        return []


INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"


def extras_for(area: str) -> dict:
    """Small settings that complete an area; each is None when it cannot be read."""
    if area == "network":
        return {"proxy": {"enabled": bool(_reg("HKCU", INTERNET_SETTINGS, "ProxyEnable")), "server": _reg("HKCU", INTERNET_SETTINGS, "ProxyServer") or ""},
                "hosts_entries": _read_hosts()}
    if area == "performance":
        acceso = _reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled")
        try:
            dimensione = round(os.stat(os.path.expandvars(r"%SystemDrive%\hiberfil.sys")).st_size / GB, 1)
        except OSError:
            dimensione = None
        spente = _reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled")
        # Without the registry value, an existing hiberfil.sys means hibernation is on.
        attiva = bool(acceso) if acceso is not None else (True if dimensione else None)
        return {"hibernation": {"enabled": attiva, "size_gb": dimensione}, "background_apps": spente != 1}
    if area == "security":
        autorun = [_reg(h, AUTORUN_KEY, "NoDriveTypeAutoRun") for h in ("HKLM", "HKCU")]
        intervallo = _reg("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore", "RPSessionInterval")
        return {"autorun_disabled": any(v == 255 for v in autorun), "restore_enabled": None if intervallo is None else intervallo != 0}
    if area == "updates":
        import shutil
        return {"winget": bool(shutil.which("winget"))}
    if area == "integrity":
        stato = op.Contesto.leggi(["sc", "query", "W32Time"])
        return {"time_service": {"running": op.servizio_attivo(stato),
                                 "server": _reg("HKLM", r"SYSTEM\CurrentControlSet\Services\W32Time\Parameters", "NtpServer") or ""}}
    return {}


# ---------- event log ----------

SCRIPT_EVENTS = r"""
$since = (Get-Date).AddDays(-7)
@(Get-WinEvent -FilterHashtable @{ LogName = 'System', 'Application'; Level = 1, 2; StartTime = $since } -MaxEvents 3000 -ErrorAction SilentlyContinue |
  Group-Object ProviderName, LogName | ForEach-Object {
    $last = $_.Group | Sort-Object TimeCreated -Descending | Select-Object -First 1
    [ordered]@{ source = $last.ProviderName; log = $last.LogName; count = $_.Count; level = [int]$last.Level; last = $last.TimeCreated.ToString('s'); message = "$($last.Message)" -replace '\s+', ' ' }
  } | Sort-Object { $_.count } -Descending | Select-Object -First 12) | ConvertTo-Json -Depth 3 -Compress
"""


def summarize_events(raw) -> dict:
    """Errors of the last 7 days grouped by source, largest first."""
    voci = [dict(v, message=str(v.get("message") or "")[:200]) for v in op.come_lista(raw) if isinstance(v, dict)]
    voci.sort(key=lambda v: v.get("count") or 0, reverse=True)
    return {"total": sum(v.get("count") or 0 for v in voci), "top": voci}


def collect_events(ctx) -> Tuple[dict, List[str]]:
    avvisi: List[str] = []
    raw = _powershell(ctx, SCRIPT_EVENTS, avvisi, "Event log", timeout=90)
    return summarize_events(raw), avvisi


# ---------- security ----------

SCRIPT_SECURITY = r"""
function Reg($p, $n) { (Get-ItemProperty -Path $p -Name $n -ErrorAction SilentlyContinue).$n }
$mp = Get-MpComputerStatus
$tpm = Get-Tpm
$sb = $null; try { $sb = Confirm-SecureBootUEFI } catch { }
$smb = Get-SmbServerConfiguration
[ordered]@{
  defender = if ($mp) { [ordered]@{ realtime = $mp.RealTimeProtectionEnabled; antivirus = $mp.AntivirusEnabled; signature_age_days = $mp.AntivirusSignatureAge
    quick_scan_age_days = $mp.QuickScanAge; full_scan_age_days = $mp.FullScanAge; tamper = $mp.IsTamperProtected; engine = "$($mp.AMEngineVersion)"; mode = "$($mp.AMRunningMode)" } } else { $null }
  firewall = @(Get-NetFirewallProfile | ForEach-Object { [ordered]@{ name = "$($_.Name)"; enabled = [bool]$_.Enabled } })
  uac = [ordered]@{ enabled = Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'EnableLUA'; level = Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'ConsentPromptBehaviorAdmin' }
  smartscreen = Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' 'SmartScreenEnabled'
  smartscreen_policy = Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'EnableSmartScreen'
  secure_boot = $sb
  tpm = if ($tpm) { [ordered]@{ present = [bool]$tpm.TpmPresent; ready = [bool]$tpm.TpmReady } } else { $null }
  bitlocker = @(Get-BitLockerVolume | ForEach-Object { [ordered]@{ mount = "$($_.MountPoint)"; protection = "$($_.ProtectionStatus)"; encrypted = $_.EncryptionPercentage } })
  rdp_deny = Reg 'HKLM:\System\CurrentControlSet\Control\Terminal Server' 'fDenyTSConnections'
  smb1 = if ($smb) { [bool]$smb.EnableSMB1Protocol } else { $null }
  pua = (Get-MpPreference -ErrorAction SilentlyContinue).PUAProtection
  admins = @(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Name)" })
  guest = (Get-LocalUser -ErrorAction SilentlyContinue | Where-Object { "$($_.SID)" -like '*-501' }).Enabled
  restore_points = @(Get-ComputerRestorePoint | ForEach-Object { [ordered]@{ description = $_.Description; created = $_.ConvertToDateTime($_.CreationTime).ToString('s'); type = "$($_.RestorePointType)" } })
} | ConvertTo-Json -Depth 4 -Compress
"""


def collect_security(ctx) -> dict:
    errori: List[str] = []
    raw = _powershell(ctx, SCRIPT_SECURITY, errori, "Security inventory", timeout=120)
    raw = raw if isinstance(raw, dict) else {}
    uac = raw.get("uac") or {}
    politica = raw.get("smartscreen_policy")
    smartscreen = "Off" if politica == 0 else (raw.get("smartscreen") or ("On" if politica == 1 else None))
    rdp = raw.get("rdp_deny")
    ospite = raw.get("guest")
    return {
        "defender": raw.get("defender") or {},
        "firewall": op.come_lista(raw.get("firewall")),
        "uac": {"enabled": None if uac.get("enabled") is None else bool(uac.get("enabled")), "level": uac.get("level")},
        "smartscreen": smartscreen,
        "secure_boot": raw.get("secure_boot"),
        "tpm": raw.get("tpm"),
        "bitlocker": op.come_lista(raw.get("bitlocker")),
        "rdp_enabled": None if rdp is None else rdp == 0,
        "smb1": raw.get("smb1"),
        "pua_protection": None if raw.get("pua") is None else raw.get("pua") == 1,
        "admins": [str(a) for a in op.come_lista(raw.get("admins"))],
        "guest_enabled": None if ospite is None else bool(ospite),
        "restore_points": sorted(op.come_lista(raw.get("restore_points")), key=lambda r: r.get("created") or "", reverse=True),
        "errors": errori,
    }


# ---------- updates and drivers ----------

SCRIPT_UPDATES = r"""
$r = [ordered]@{}
try {
  $session = New-Object -ComObject Microsoft.Update.Session
  $searcher = $session.CreateUpdateSearcher()
  $found = $searcher.Search("IsInstalled=0 and IsHidden=0 and Type='Software'")
  $r.pending = @($found.Updates | ForEach-Object { [ordered]@{ title = $_.Title; severity = "$($_.MsrcSeverity)"; kb = ($_.KBArticleIDs -join ','); size_mb = [math]::Round($_.MaxDownloadSize / 1MB, 1); categories = @($_.Categories | ForEach-Object { $_.Name }) } })
  $r.search_ok = $true
  $count = $searcher.GetTotalHistoryCount()
  $r.history = @(if ($count -gt 0) { $searcher.QueryHistory(0, [math]::Min(15, $count)) | Where-Object Title | ForEach-Object { [ordered]@{ title = $_.Title; date = $_.Date.ToString('s'); result = [int]$_.ResultCode } } })
} catch { $r.search_ok = $false; $r.search_error = "$($_.Exception.Message)" }
$r.problem_devices = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | ForEach-Object { [ordered]@{ name = "$($_.Name)"; class = "$($_.PNPClass)"; code = $_.ConfigManagerErrorCode } })
$r.drivers = @(Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DriverProviderName -and $_.DriverProviderName -ne 'Microsoft' -and $_.DriverDate -and $_.DeviceName } | ForEach-Object { [ordered]@{ name = "$($_.DeviceName)"; provider = "$($_.DriverProviderName)"; version = "$($_.DriverVersion)"; date = $_.DriverDate.ToString('yyyy-MM-dd'); class = "$($_.DeviceClass)" } })
$r.reboot_required = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
$r | ConvertTo-Json -Depth 5 -Compress
"""

UPDATE_RESULTS = {0: "not started", 1: "in progress", 2: "succeeded", 3: "succeeded with errors", 4: "failed", 5: "aborted"}


def collect_updates(ctx) -> dict:
    errori: List[str] = []
    avvisi: List[str] = []
    raw = _powershell(ctx, SCRIPT_UPDATES, errori, "Windows Update", timeout=240)
    raw = raw if isinstance(raw, dict) else {}
    if raw and not raw.get("search_ok"):
        avvisi.append("Windows Update could not be searched (offline or service stopped): " + str(raw.get("search_error") or "")[:160])
    oggi = datetime.now().date()
    driver = []
    for voce in op.come_lista(raw.get("drivers")):
        try:
            voce["age_days"] = (oggi - datetime.strptime(voce.get("date", ""), "%Y-%m-%d").date()).days
        except ValueError:
            voce["age_days"] = None
        driver.append(voce)
    driver.sort(key=lambda d: d.get("age_days") or 0, reverse=True)
    storia = op.come_lista(raw.get("history"))
    for voce in storia:
        voce["result"] = UPDATE_RESULTS.get(voce.get("result"), str(voce.get("result")))
    return {
        "search_ok": bool(raw.get("search_ok")),
        "pending": op.come_lista(raw.get("pending")),
        "history": storia,
        "problem_devices": op.come_lista(raw.get("problem_devices")),
        "drivers": driver,
        "reboot_required": bool(raw.get("reboot_required")),
        "warnings": avvisi,
        "errors": errori,
    }
