"""Hardware inventory and sensors: every component with its hardware IDs (for finding drivers and
datasheets online), temperatures and fans.

Windows exposes only some sensors without a vendor driver: ACPI thermal zones, disk temperatures
(storage reliability counters), NVIDIA GPUs through nvidia-smi and fans in Win32_Fan. When
LibreHardwareMonitor or OpenHardwareMonitor is running, its WMI sensors (CPU cores, motherboard,
every fan) are read too."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional

INVENTORY_TTL = 600
SENSORS_TTL = 3   # nvidia-smi answers in a fraction of a second
WMI_TTL = 20      # Windows sensors and storage counters take seconds to read
KELVIN_TENTHS = 2731.5
MONITOR_PACKAGE = "LibreHardwareMonitor.LibreHardwareMonitor"
MONITOR_EXE = "LibreHardwareMonitor.exe"

# The vendors seen most often, to name a device from its ID even without a driver.
VENDORS: Dict[str, str] = {
    "8086": "Intel", "8087": "Intel", "1022": "AMD", "1002": "AMD (ATI)", "10DE": "NVIDIA", "10EC": "Realtek", "0BDA": "Realtek",
    "14E4": "Broadcom", "168C": "Qualcomm Atheros", "17CB": "Qualcomm", "1B21": "ASMedia", "144D": "Samsung", "15B7": "Western Digital / SanDisk",
    "1987": "Phison", "1CC1": "ADATA", "126F": "Silicon Motion", "1E0F": "KIOXIA", "1C5C": "SK hynix", "2646": "Kingston", "1344": "Micron / Crucial",
    "1179": "Toshiba", "1B4B": "Marvell", "1D6A": "Aquantia", "1912": "Renesas", "104C": "Texas Instruments", "1217": "O2 Micro",
    "046D": "Logitech", "045E": "Microsoft", "1532": "Razer", "1038": "SteelSeries", "05AC": "Apple", "0781": "SanDisk", "1462": "MSI",
    "1043": "ASUS", "0B05": "ASUS", "1458": "Gigabyte", "1028": "Dell", "413C": "Dell", "103C": "HP", "03F0": "HP", "17AA": "Lenovo",
    "04F2": "Chicony", "13D3": "IMC Networks", "0489": "Foxconn", "1BCF": "Sunplus", "5986": "Acer / Bison", "0C45": "Microdia",
    "04E8": "Samsung", "1050": "Yubico", "054C": "Sony", "057E": "Nintendo", "2109": "VIA Labs", "05E3": "Genesys Logic", "1A40": "Terminus",
    "0951": "Kingston", "152D": "JMicron", "174C": "ASMedia", "8564": "Transcend", "0CF3": "Qualcomm Atheros",
}

HWID = re.compile(r"^(?P<bus>[A-Z0-9]+)\\(?P<rest>[^\\]+)", re.I)


def parse_hwid(device_id: str) -> dict:
    """Splits a PnP ID (PCI\\VEN_10DE&DEV_2484&SUBSYS_..., USB\\VID_046D&PID_C52B...) into the parts used to search online."""
    risultato = {"bus": "", "vendor_id": "", "device_id": "", "subsys": "", "rev": "", "vendor": "", "search": "", "lookup": ""}
    m = HWID.match(device_id or "")
    if not m:
        return risultato
    bus, resto = m.group("bus").upper(), m.group("rest").upper()
    risultato["bus"] = bus
    parti = dict(p.split("_", 1) for p in resto.split("&") if "_" in p)
    ven = parti.get("VEN") or parti.get("VID") or ""
    dev = parti.get("DEV") or parti.get("PID") or ""
    risultato.update(vendor_id=ven[:4], device_id=dev[:4], subsys=parti.get("SUBSYS", ""), rev=parti.get("REV", ""))
    risultato["vendor"] = VENDORS.get(ven[:4], "")
    if ven and dev:
        chiave_v, chiave_d = ("VEN", "DEV") if "VEN" in parti else ("VID", "PID")
        risultato["search"] = f"{bus}\\{chiave_v}_{ven[:4]}&{chiave_d}_{dev[:4]}"
        if bus in ("PCI", "USB"):
            risultato["lookup"] = f"{bus.lower()}/{ven[:4]}/{dev[:4]}"
    elif resto:
        risultato["search"] = f"{bus}\\{resto.split('&')[0]}"
    return risultato


def kelvin_tenths_to_c(value) -> Optional[float]:
    try:
        celsius = (float(value) - KELVIN_TENTHS) / 10
    except (TypeError, ValueError):
        return None
    return round(celsius, 1) if -40 < celsius < 150 else None


def _powershell(script: str, timeout: int = 90):
    codificato = base64.b64encode(("$ErrorActionPreference='SilentlyContinue';[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script)
                                  .encode("utf-16-le")).decode()
    risultato = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificato],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=timeout,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    testo = risultato.stdout.decode("utf-8", "replace").strip()
    return json.loads(testo) if testo else None


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


SCRIPT_INVENTORY = r"""
$r = [ordered]@{}
$cs = Get-CimInstance Win32_ComputerSystem; $bios = Get-CimInstance Win32_BIOS; $bb = Get-CimInstance Win32_BaseBoard
$csp = Get-CimInstance Win32_ComputerSystemProduct; $os = Get-CimInstance Win32_OperatingSystem
$r.system = [ordered]@{ manufacturer = $cs.Manufacturer; model = $cs.Model; sku = $cs.SystemSKUNumber; family = $cs.SystemFamily; type = "$($cs.PCSystemType)"
  uuid = $csp.UUID; serial = $bios.SerialNumber; bios_vendor = $bios.Manufacturer; bios_version = $bios.SMBIOSBIOSVersion
  bios_date = if ($bios.ReleaseDate) { $bios.ReleaseDate.ToString('yyyy-MM-dd') } else { '' }
  board_vendor = $bb.Manufacturer; board_model = $bb.Product; board_version = $bb.Version; board_serial = $bb.SerialNumber
  os = $os.Caption; os_version = $os.Version; os_build = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').DisplayVersion
  ram_total = [int64]$cs.TotalPhysicalMemory }
$r.cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { [ordered]@{ name = $_.Name.Trim(); vendor = $_.Manufacturer; id = $_.ProcessorId
  caption = $_.Caption; socket = $_.SocketDesignation; cores = $_.NumberOfCores; threads = $_.NumberOfLogicalProcessors; max_mhz = $_.MaxClockSpeed
  current_mhz = $_.CurrentClockSpeed; l2_kb = $_.L2CacheSize; l3_kb = $_.L3CacheSize; virtualization = $_.VirtualizationFirmwareEnabled; device = $_.PNPDeviceID } })
$arr = Get-CimInstance Win32_PhysicalMemoryArray | Select-Object -First 1
$r.memory_slots = [ordered]@{ slots = $arr.MemoryDevices; max_bytes = [int64]$arr.MaxCapacityEx * 1024 }
$r.memory = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object { [ordered]@{ slot = $_.DeviceLocator; bank = $_.BankLabel; bytes = [int64]$_.Capacity
  mhz = $_.Speed; configured_mhz = $_.ConfiguredClockSpeed; vendor = $_.Manufacturer; part = "$($_.PartNumber)".Trim(); serial = $_.SerialNumber
  type = $_.SMBIOSMemoryType; form = $_.FormFactor; voltage_mv = $_.ConfiguredVoltage } })
$vram = @{}
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath; if ($p.MatchingDeviceId -and $p.'HardwareInformation.qwMemorySize') { $vram[$p.MatchingDeviceId.ToUpper()] = [int64]$p.'HardwareInformation.qwMemorySize' } }
$r.gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { $id = "$($_.PNPDeviceID)".ToUpper(); $mem = [int64]$_.AdapterRAM
  foreach ($k in $vram.Keys) { if ($id.StartsWith($k)) { $mem = $vram[$k] } }
  [ordered]@{ name = $_.Name; vendor = $_.AdapterCompatibility; device = $_.PNPDeviceID; driver = $_.DriverVersion
  driver_date = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' }; vram = $mem; processor = $_.VideoProcessor
  resolution = if ($_.CurrentHorizontalResolution) { "$($_.CurrentHorizontalResolution) x $($_.CurrentVerticalResolution)" } else { '' }; hz = $_.CurrentRefreshRate; status = $_.Status } })
$pd = @{}; Get-PhysicalDisk | ForEach-Object { $pd["$($_.DeviceId)"] = $_ }
$r.disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { $p = $pd["$($_.Index)"]
  [ordered]@{ index = $_.Index; model = $_.Model; device = $_.PNPDeviceID; interface = $_.InterfaceType; bytes = [int64]$_.Size; firmware = $_.FirmwareRevision
  serial = "$($_.SerialNumber)".Trim(); partitions = $_.Partitions; media = if ($p) { "$($p.MediaType)" } else { '' }; bus = if ($p) { "$($p.BusType)" } else { '' }
  health = if ($p) { "$($p.HealthStatus)" } else { '' } } })
$r.network = @(Get-NetAdapter -Physical | ForEach-Object { [ordered]@{ name = $_.Name; description = $_.InterfaceDescription; mac = $_.MacAddress
  speed = $_.LinkSpeed; status = "$($_.Status)"; driver = $_.DriverVersion; driver_provider = $_.DriverProvider
  driver_date = $_.DriverDate; device = $_.PnPDeviceID; media = "$($_.PhysicalMediaType)" } })
$dec = { param($a) if ($a) { -join ($a | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) } else { '' } }
$r.monitors = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID | ForEach-Object { [ordered]@{ name = & $dec $_.UserFriendlyName
  vendor = & $dec $_.ManufacturerName; product = & $dec $_.ProductCodeID; serial = & $dec $_.SerialNumberID; year = $_.YearOfManufacture
  device = ($_.InstanceName -replace '_0$', '') } })
$r.audio = @(Get-CimInstance Win32_SoundDevice | ForEach-Object { [ordered]@{ name = $_.Name; vendor = $_.Manufacturer; device = $_.PNPDeviceID; status = $_.Status } })
$bat = Get-CimInstance Win32_Battery
if ($bat) {
  $st = Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData | Select-Object -First 1
  $fc = Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity | Select-Object -First 1
  $r.battery = [ordered]@{ name = $bat.Name; charge = $bat.EstimatedChargeRemaining; status = $bat.BatteryStatus; chemistry = $bat.Chemistry
    designed_mwh = $st.DesignedCapacity; full_mwh = $fc.FullChargedCapacity; vendor = $st.ManufactureName; serial = $st.SerialNumber; device = $bat.PNPDeviceID }
}
$drv = @{}
Get-CimInstance Win32_PnPSignedDriver | ForEach-Object { if ($_.DeviceID) { $drv[$_.DeviceID.ToUpper()] = $_ } }
$r.devices = @(Get-CimInstance Win32_PnPEntity | ForEach-Object { $d = $drv["$($_.PNPDeviceID)".ToUpper()]
  [ordered]@{ name = $_.Name; class = $_.PNPClass; vendor = $_.Manufacturer; device = $_.PNPDeviceID; hardware_ids = @($_.HardwareID | Select-Object -First 4)
  compatible_ids = @($_.CompatibleID | Select-Object -First 2); status = $_.Status; error = $_.ConfigManagerErrorCode; present = $_.Present; service = $_.Service
  driver = if ($d) { $d.DriverVersion } else { '' }; driver_date = if ($d -and $d.DriverDate) { $d.DriverDate.ToString('yyyy-MM-dd') } else { '' }
  driver_provider = if ($d) { $d.DriverProviderName } else { '' }; inf = if ($d) { $d.InfName } else { '' } } })
$r | ConvertTo-Json -Depth 5 -Compress
"""

SCRIPT_SENSORS = r"""
$r = [ordered]@{ zones = @(); acpi = @(); disks = @(); fans = @(); lhm = @(); lhm_source = '' }
$r.zones = @(Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | ForEach-Object {
  [ordered]@{ name = $_.Name; tenths_k = $_.HighPrecisionTemperature; kelvin = $_.Temperature; throttle = $_.PercentPassiveLimit } })
$r.acpi = @(Get-CimInstance -Namespace root\wmi -ClassName MSAcpi_ThermalZoneTemperature | ForEach-Object {
  [ordered]@{ name = $_.InstanceName; tenths_k = $_.CurrentTemperature; critical_tenths_k = $_.CriticalTripPoint } })
$r.disks = @(Get-PhysicalDisk | ForEach-Object { $c = $_ | Get-StorageReliabilityCounter
  [ordered]@{ name = $_.FriendlyName; index = $_.DeviceId; celsius = $c.Temperature; max_celsius = $c.TemperatureMax; wear = $c.Wear; hours = $c.PowerOnHours } })
$r.fans = @(Get-CimInstance Win32_Fan | ForEach-Object { [ordered]@{ name = $_.Name; rpm = $_.DesiredSpeed; status = $_.Status; active = $_.ActiveCooling } })
foreach ($ns in 'root\LibreHardwareMonitor', 'root\OpenHardwareMonitor') {
  $s = @(Get-CimInstance -Namespace $ns -ClassName Sensor | Where-Object { $_.SensorType -in 'Temperature', 'Fan', 'Control', 'Load', 'Power', 'Clock' })
  if ($s.Count) { $r.lhm_source = ($ns -replace 'root\\', ''); $r.lhm = @($s | ForEach-Object { [ordered]@{ name = $_.Name; type = $_.SensorType
    value = [math]::Round([double]$_.Value, 1); max = [math]::Round([double]$_.Max, 1); parent = $_.Parent; id = $_.Identifier } }); break }
}
$r | ConvertTo-Json -Depth 4 -Compress
"""

NVIDIA_FIELDS = ("name", "temperature.gpu", "fan.speed", "utilization.gpu", "power.draw", "clocks.gr", "memory.used", "memory.total")
LHM_GROUPS = {"CPU": "Processor", "AMDCPU": "Processor", "INTELCPU": "Processor", "LPC": "Motherboard", "MAINBOARD": "Motherboard",
              "MOTHERBOARD": "Motherboard", "GPU-NVIDIA": "Graphics", "GPU-AMD": "Graphics", "GPU-INTEL": "Graphics", "NVIDIAGPU": "Graphics",
              "ATIGPU": "Graphics", "NVME": "Disks", "HDD": "Disks", "SSD": "Disks", "STORAGE": "Disks", "RAM": "Memory", "MEMORY": "Memory"}


def _nvidia_smi() -> Optional[str]:
    trovato = shutil.which("nvidia-smi")
    if trovato:
        return trovato
    for percorso in (os.path.expandvars(r"%SystemRoot%\System32\nvidia-smi.exe"),
                     os.path.expandvars(r"%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe")):
        if os.path.isfile(percorso):
            return percorso
    return None


def _number(text) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None  # "[N/A]" or "[Not Supported]"


def parse_nvidia(text: str) -> List[dict]:
    schede = []
    for riga in (text or "").splitlines():
        valori = [v.strip() for v in riga.split(",")]
        if len(valori) != len(NVIDIA_FIELDS):
            continue
        dati = dict(zip(NVIDIA_FIELDS, valori))
        schede.append({"name": dati["name"], "celsius": _number(dati["temperature.gpu"]), "fan_percent": _number(dati["fan.speed"]),
                       "load_percent": _number(dati["utilization.gpu"]), "watts": _number(dati["power.draw"]), "mhz": _number(dati["clocks.gr"]),
                       "memory_used_mb": _number(dati["memory.used"]), "memory_total_mb": _number(dati["memory.total"])})
    return schede


def _nvidia() -> List[dict]:
    eseguibile = _nvidia_smi()
    if not eseguibile:
        return []
    try:
        risultato = subprocess.run([eseguibile, "--query-gpu=" + ",".join(NVIDIA_FIELDS), "--format=csv,noheader,nounits"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_nvidia(risultato.stdout.decode("utf-8", "replace"))


def _zone_name(name) -> str:
    testo = re.split(r"[\\.]", str(name or ""))[-1].strip("_")  # \_TZ.TZ00 and ACPI\ThermalZone\TZ00_0 -> TZ00
    return "Thermal zone " + (testo or "?")


def summarize_sensors(raw: dict, gpus: List[dict]) -> dict:
    """One list of temperatures and one of fans, whatever the source."""
    raw = raw if isinstance(raw, dict) else {}
    temperature, ventole, altro = [], [], []
    for z in _list(raw.get("zones")):
        c = kelvin_tenths_to_c(z.get("tenths_k")) if z.get("tenths_k") else (round(z["kelvin"] - 273.15, 1) if z.get("kelvin") else None)
        if c is not None:
            frenata = z.get("throttle")
            temperature.append({"name": _zone_name(z.get("name")), "group": "Motherboard / ACPI", "celsius": c, "source": "Windows thermal zone",
                                "note": f"Throttling to {frenata}%" if frenata not in (None, 0, 100) else ""})
    if not temperature:
        for z in _list(raw.get("acpi")):
            c = kelvin_tenths_to_c(z.get("tenths_k"))
            if c is not None:
                temperature.append({"name": _zone_name(z.get("name")), "group": "Motherboard / ACPI", "celsius": c,
                                    "max": kelvin_tenths_to_c(z.get("critical_tenths_k")), "source": "ACPI"})
    for d in _list(raw.get("disks")):
        if d.get("celsius"):
            note = [f"Wear {d['wear']}%" if d.get("wear") else "", f"{d['hours']} h powered on" if d.get("hours") else ""]
            temperature.append({"name": d.get("name") or f"Disk {d.get('index')}", "group": "Disks", "celsius": float(d["celsius"]),
                                "max": float(d["max_celsius"]) if d.get("max_celsius") else None, "source": "Storage reliability counter",
                                "note": " · ".join(n for n in note if n)})
    for g in gpus:
        if g.get("celsius") is not None:
            note = [f"{g['load_percent']:.0f}% load" if g.get("load_percent") is not None else "",
                    f"{g['watts']:.0f} W" if g.get("watts") is not None else ""]
            temperature.append({"name": g["name"], "group": "Graphics", "celsius": g["celsius"], "source": "nvidia-smi",
                                "note": " · ".join(n for n in note if n)})
        if g.get("fan_percent") is not None:
            ventole.append({"name": g["name"] + " fan", "group": "Graphics", "percent": g["fan_percent"], "source": "nvidia-smi"})
    for f in _list(raw.get("fans")):
        ventole.append({"name": f.get("name") or "Fan", "group": "System", "rpm": f.get("rpm") or None, "status": f.get("status"), "source": "Win32_Fan"})
    sorgente = raw.get("lhm_source") or ""
    for s in _list(raw.get("lhm")):
        radice = str(s.get("parent") or s.get("id") or "").strip("/").split("/")[0].upper()
        gruppo = LHM_GROUPS.get(radice, radice.title() or sorgente)
        valore = s.get("value")
        if s.get("type") == "Temperature" and valore:
            temperature.append({"name": s.get("name"), "group": gruppo, "celsius": valore, "max": s.get("max") or None, "source": sorgente})
        elif s.get("type") == "Fan":
            ventole.append({"name": s.get("name"), "group": gruppo, "rpm": valore, "max": s.get("max") or None, "source": sorgente})
        elif s.get("type") == "Control" and "fan" in str(s.get("name", "")).lower():
            ventole.append({"name": s.get("name"), "group": gruppo, "percent": valore, "source": sorgente})
        elif s.get("type") in ("Load", "Power", "Clock") and gruppo in ("Processor", "Graphics"):
            altro.append({"name": s.get("name"), "group": gruppo, "type": s.get("type"), "value": valore, "source": sorgente})
    for t in temperature:
        limite = 70 if t["group"] == "Disks" else 90
        t["state"] = "error" if t["celsius"] >= limite else "warning" if t["celsius"] >= limite - 15 else "ok"
    return {"temperatures": temperature, "fans": ventole, "other": altro, "gpus": gpus, "monitor_tool": sorgente,
            "hottest": max((t["celsius"] for t in temperature), default=None)}


class MonitorToolError(RuntimeError):
    """The sensor tool could not be installed or started."""


def monitor_tool_path() -> Optional[str]:
    """Where LibreHardwareMonitor is installed for all users, if anywhere.

    The agent starts it with administrator rights, so only Program Files is searched: a copy under the
    user profile (%LOCALAPPDATA%, per-user winget) could be replaced by any program the user runs."""
    programmi = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidati = [os.path.join(programmi, "LibreHardwareMonitor", MONITOR_EXE)]
    radice = os.path.join(programmi, "WinGet", "Packages")
    try:
        cartelle = [os.path.join(radice, c) for c in os.listdir(radice) if c.split("_")[0] == MONITOR_PACKAGE]
    except OSError:
        cartelle = []
    for cartella in cartelle:
        for base, _, file in os.walk(cartella):
            if MONITOR_EXE in file:
                candidati.append(os.path.join(base, MONITOR_EXE))
    return next((p for p in candidati if os.path.isfile(p)), None)


def _folders_up_to(percorso: str, radice: str) -> List[str]:
    """The file and every folder above it, up to and including `radice`."""
    voci, corrente = [percorso], os.path.dirname(percorso)
    radice = os.path.normcase(os.path.realpath(radice))
    while True:
        voci.append(corrente)
        if os.path.normcase(corrente) == radice or os.path.dirname(corrente) == corrente:
            return voci
        corrente = os.path.dirname(corrente)


def monitor_tool_running() -> bool:
    risultato = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {MONITOR_EXE}", "/NH"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return MONITOR_EXE.lower() in risultato.stdout.decode("oem", "replace").lower()


def install_monitor_tool() -> str:
    """Installs LibreHardwareMonitor with winget; returns its output. RuntimeError when winget is missing or fails."""
    winget = shutil.which("winget")
    if not winget:
        raise MonitorToolError("winget is not available on this PC: install App Installer from the Microsoft Store, "
                           "or download LibreHardwareMonitor from its GitHub page.")
    # --scope machine: Program Files, writable only by administrators (see start_monitor_tool).
    risultato = subprocess.run([winget, "install", "--id", MONITOR_PACKAGE, "-e", "--scope", "machine", "--silent", "--accept-source-agreements",
                                "--accept-package-agreements", "--disable-interactivity"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    uscita = risultato.stdout.decode("utf-8", "replace")
    if risultato.returncode != 0 and not monitor_tool_path():
        raise MonitorToolError("winget could not install LibreHardwareMonitor: " + uscita.strip()[-400:])
    return uscita


def start_monitor_tool(unprotected: Optional[Callable[[List[str]], List[str]]] = None) -> str:
    """Starts LibreHardwareMonitor, elevated like the agent, only when standard users cannot change the file or its folders."""
    percorso = monitor_tool_path()
    if not percorso:
        raise MonitorToolError("LibreHardwareMonitor is not installed for all users (Program Files).")
    percorso = os.path.realpath(percorso)
    programmi = os.path.realpath(os.environ.get("ProgramFiles", r"C:\Program Files"))
    if os.path.normcase(os.path.commonpath([percorso, programmi])) != os.path.normcase(programmi):
        raise MonitorToolError(f"{percorso} is outside Program Files: it is not started with administrator rights.")
    if unprotected is None:
        from .scheduler import unprotected_paths as unprotected
    aperti = unprotected(_folders_up_to(percorso, programmi))
    if aperti:
        raise MonitorToolError("LibreHardwareMonitor is not started: standard users can change " + ", ".join(aperti[:3]) +
                               ". Reinstall it for all users or fix the folder permissions.")
    if not monitor_tool_running():
        subprocess.Popen([percorso], cwd=os.path.dirname(percorso), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    return percorso


class HardwareReader:
    def __init__(self):
        self._lock = threading.Lock()
        self._inventory: Optional[dict] = None
        self._inventory_at = 0.0
        self._sensors: Optional[dict] = None
        self._sensors_at = 0.0
        self._wmi: dict = {}
        self._wmi_at = 0.0

    def inventory(self, fresh: bool = False) -> dict:
        with self._lock:
            if not fresh and self._inventory and time.time() - self._inventory_at < INVENTORY_TTL:
                return self._inventory
        inizio = time.monotonic()
        try:
            raw = _powershell(SCRIPT_INVENTORY, timeout=120)
        except (OSError, subprocess.TimeoutExpired, ValueError) as errore:
            raise RuntimeError(f"Could not read the hardware inventory: {errore}") from None
        raw = raw if isinstance(raw, dict) else {}
        raw["system"] = raw.get("system") if isinstance(raw.get("system"), dict) else {}
        for chiave in ("cpu", "memory", "gpu", "disks", "network", "monitors", "audio", "devices"):
            raw[chiave] = _list(raw.get(chiave))
        for d in raw["devices"]:
            d["hardware_ids"] = _list(d.get("hardware_ids"))
            d["compatible_ids"] = _list(d.get("compatible_ids"))
            d["ids"] = parse_hwid(d["hardware_ids"][0] if d["hardware_ids"] else d.get("device") or "")
        for chiave in ("cpu", "gpu", "disks", "network", "audio"):
            for voce in raw[chiave]:
                voce["ids"] = parse_hwid(voce.get("device") or "")
        raw["seconds"] = round(time.monotonic() - inizio, 1)
        raw["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            self._inventory, self._inventory_at = raw, time.time()
        return raw

    def sensors(self, fresh: bool = False) -> dict:
        with self._lock:
            if not fresh and self._sensors and time.time() - self._sensors_at < SENSORS_TTL:
                return self._sensors
            raw, vecchio = self._wmi, fresh or time.time() - self._wmi_at >= WMI_TTL
        if vecchio:
            try:
                raw = _powershell(SCRIPT_SENSORS, timeout=45) or {}
            except (OSError, subprocess.TimeoutExpired, ValueError):
                raw = {}
            with self._lock:
                self._wmi, self._wmi_at = raw, time.time()
        dati = summarize_sensors(raw, _nvidia())
        dati["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        dati["monitor_installed"] = bool(dati["monitor_tool"]) or monitor_tool_path() is not None
        with self._lock:
            self._sensors, self._sensors_at = dati, time.time()
        return dati
