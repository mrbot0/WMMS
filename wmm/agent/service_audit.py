"""Service analysis: which services of THIS PC can be switched off without anyone noticing.

Nothing is decided from a fixed list made on one PC. The script reads every installed service (who makes it, where its
program lives, how much memory its process takes) and what the PC has (printers, Bluetooth, fingerprint reader, smart
card reader, scanner, the Xbox app, Phone Link, company management, SSD). Rules then pick:

- Microsoft services that only send telemetry or serve hardware and apps this PC does not have;
- third-party updaters left running all day (set to Manual: the apps still update through their scheduled tasks);
- services that open the PC to the network for no reason (Remote Registry, Telnet, SNMP...);
- for review only, never applied on their own: remote-control tools, programs in unusual folders, heavy services.

Never proposed: anything protected by the suite, security software, drivers and hardware tools, backup and sync,
licensing, virtualization and VPNs. Changes go through ottimizza_pc.imposta_servizi, so every original start type is
kept in the service backup and "Restore modified services" puts it back."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

import ottimizza_pc as op

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$procs = @{}
Get-Process | ForEach-Object { $procs[$_.Id] = $_ }
$all = @(Get-CimInstance Win32_Service)
$perPid = $all | Where-Object { $_.ProcessId -gt 0 } | Group-Object ProcessId -AsHashTable -AsString
$company = @{}
$services = foreach ($s in $all) {
  $path = "$($s.PathName)"
  $exe = if ($path -match '^\s*"([^"]+)"') { $Matches[1] } elseif ($path -match '^\s*(.+?\.exe)\b') { $Matches[1] } else { $path.Trim() }
  $exe = [Environment]::ExpandEnvironmentVariables($exe)
  if (-not $company.ContainsKey($exe)) {
    $company[$exe] = if ($exe -and (Test-Path -LiteralPath $exe)) { "$([Diagnostics.FileVersionInfo]::GetVersionInfo($exe).CompanyName)".Trim() } else { '' }
  }
  $p = if ($s.ProcessId -gt 0) { $procs[[int]$s.ProcessId] }
  [ordered]@{ name = "$($s.Name)"; display = "$($s.DisplayName)"; start = "$($s.StartMode)";
    delayed = [bool]$s.DelayedAutoStart; state = "$($s.State)"; path = $exe; company = $company[$exe]; account = "$($s.StartName)";
    pid = [int]$s.ProcessId; shared = $(if ($s.ProcessId -gt 0) { @($perPid["$($s.ProcessId)"]).Count } else { 0 });
    memory_mb = $(if ($p) { [math]::Round($p.WorkingSet64 / 1MB) } else { 0 }) }
}
function Count($class, $skip) {
  @(Get-PnpDevice -Class $class -PresentOnly | Where-Object { -not $skip -or $_.InstanceId -notmatch $skip }).Count
}
$printers = @(Get-CimInstance Win32_Printer | Where-Object {
  $_.Name -notmatch 'PDF|XPS|OneNote|Fax' -and $_.PortName -notmatch '^(PORTPROMPT:|nul:|SHRFAX:|FILE:)' }).Count
$apps = @(Get-AppxPackage | ForEach-Object Name)
$mdm = @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Enrollments' | Where-Object { (Get-ItemProperty $_.PSPath).UPN }).Count -gt 0
$ssd = $null
try { $ssd = "$((Get-Partition -DriveLetter ($env:SystemDrive.TrimEnd(':')) | Get-Disk | Get-PhysicalDisk).MediaType)" -eq 'SSD' } catch { }
[ordered]@{
  services = @($services)
  context = [ordered]@{
    printers = $printers
    bluetooth = (Count 'Bluetooth' '^(BTHENUM|BTHLEDEVICE|BTHLE|BTH|SWD)\\')
    biometric = (Count 'Biometric' $null)
    scanners = (Count 'Image' $null)
    smartcard = (Count 'SmartCardReader' $null)
    xbox = [bool]($apps -match '^Microsoft\.(GamingApp|XboxApp)$')
    phone_link = [bool]($apps -match '^Microsoft\.YourPhone$')
    domain = [bool](Get-CimInstance Win32_ComputerSystem).PartOfDomain
    mdm = $mdm
    ssd = $ssd
  }
} | ConvertTo-Json -Depth 4 -Compress
"""

# Start types in the words of sc.exe, from the most to the least active.
RANK = {"auto": 3, "delayed-auto": 3, "demand": 2, "disabled": 1}
WMI_START = {"auto": "auto", "manual": "demand", "disabled": "disabled", "boot": "boot", "system": "system"}

CATEGORIES = {
    "telemetry": "Telemetry",
    "updater": "Updater always on",
    "insecure": "Security risk",
    "unused": "Not used on this PC",
    "remote": "Remote control",
    "suspicious": "Unusual location",
    "heavy": "Heavy",
}

# Microsoft services that every Windows has and almost nobody needs: (category, target, why).
MICROSOFT_OPTIONAL = {
    "DiagTrack": ("telemetry", "disabled", "Sends usage and diagnostic data to Microsoft all the time."),
    "RetailDemo": ("unused", "disabled", "The demo mode of PCs on display in shops."),
    "MapsBroker": ("unused", "disabled", "Downloads offline maps for the Maps app, which current Windows no longer has."),
    "Fax": ("unused", "disabled", "Sends faxes through a modem."),
    "WMPNetworkSvc": ("unused", "disabled", "Shares the Windows Media Player library with other devices on the network."),
    "WalletService": ("unused", "disabled", "Payments inside Windows apps, a feature nobody uses."),
    "RemoteRegistry": ("insecure", "disabled", "Lets other computers read and change the registry of this PC over the network."),
    "TlntSvr": ("insecure", "disabled", "Telnet server: remote control without encryption."),
    "SNMP": ("insecure", "disabled", "An old network management protocol that sends its passwords in clear text."),
    "SNMPTRAP": ("insecure", "disabled", "Receives SNMP messages, an old protocol without encryption."),
    "RemoteAccess": ("insecure", "disabled", "Routing and Remote Access: makes the PC a router or a dial-in server."),
    "edgeupdate": ("updater", "demand", "Edge updater: Edge still updates itself through its scheduled task."),
    "edgeupdatem": ("updater", "demand", "Edge updater: Edge still updates itself through its scheduled task."),
}
XBOX = ("XblAuthManager", "XblGameSave", "XboxNetApiSvc", "GamingServices", "GamingServicesNet")  # not XboxGipSvc: controllers
# Services of a kind of hardware: (context key, why). Only proposed when that hardware is missing and the service is on.
HARDWARE = {
    "bthserv": ("bluetooth", "Bluetooth support, but this PC has no Bluetooth adapter."),
    "BTAGService": ("bluetooth", "Bluetooth audio, but this PC has no Bluetooth adapter."),
    "BthAvctpSvc": ("bluetooth", "Bluetooth remote controls, but this PC has no Bluetooth adapter."),
    "WbioSrvc": ("biometric", "Fingerprint and face sign-in, but this PC has no such reader or camera."),
    "SCardSvr": ("smartcard", "Smart cards, but this PC has no card reader."),
    "ScDeviceEnum": ("smartcard", "Smart cards, but this PC has no card reader."),
    "stisvc": ("scanners", "Scanners and cameras through WIA, but this PC has none."),
}

# Never proposed, whatever they do: security, data, licences, development and virtualization, encryption, anti-cheat.
KEEP_ALWAYS = re.compile(
    r"defender|antivir|anti-virus|antimalware|malware|avast|\bavg\b|bitdefender|\beset\b|kaspersky|norton|symantec|mcafee|sophos|"
    r"trend ?micro|f-secure|webroot|panda|avira|comodo|emsisoft|crowdstrike|sentinel ?one|carbon ?black|cylance|firewall|endpoint|"
    r"backup|onedrive|dropbox|google ?drive|icloud|box ?drive|nextcloud|veeam|acronis|macrium|"
    r"licen[cs]|flexnet|flexera|sentinel|hasp|codemeter|wibu|"
    r"vmware|virtualbox|\bvbox|hyper-v|docker|\bwsl|\b(?:my|ms|postgre)?sql|postgres|\bmongo|\bredis\b|apache|nginx|tomcat|"
    r"password|bitwarden|1password|keepass|lastpass|dashlane|crypt|bitlocker|veracrypt|"
    r"anti-?cheat|easyanticheat|battleye|vanguard|faceit|\bvg[ck]\b|"
    r"\bvpn|openvpn|wireguard|tap-windows|forti|cisco|globalprotect|zscaler",
    re.I)
# Hardware and driver tools: their updaters and telemetry can go, the rest stays.
KEEP_HARDWARE = re.compile(
    r"audio|sound|realtek|nahimic|dolby|waves|\bdts\b|nvidia|nvdisplay|nvcontainer|radeon|\bamd\b|intel|thunderbolt|synaptics|"
    r"\belan|touchpad|precision|bluetooth|wireless|wlan|wi-?fi|ethernet|killer|network|\bfan\b|thermal|battery|power|hotkey|"
    r"keyboard|mouse|logitech|corsair|razer|steelseries|hyperx|asus|armoury|\bmsi\b|gigabyte|aorus|dell|lenovo|\bhp\b|acer|"
    r"samsung|print|scan|epson|canon|brother|xerox|ricoh|lexmark|kyocera|camera|webcam|tablet|wacom|pen\b|display|monitor",
    re.I)
UPDATER = re.compile(r"updat|upgrad|maintenance service|autoupdate|live ?update|\bupd(?:svc|ater)?\b", re.I)
TELEMETRY = re.compile(r"telemetr|analytic|crash ?report|usage ?(?:data|stat)|customer experience|experience improvement|"
                       r"feedback|promot|\bads? ?service", re.I)
REMOTE = re.compile(r"teamviewer|anydesk|rustdesk|splashtop|logmein|screenconnect|connectwise|atera|chrome ?remote|chromoting|"
                    r"ammyy|vnc|remote ?utilities|supremo|dameware|bomgar|beyondtrust|parsec|nomachine|zoho ?assist|getscreen", re.I)
USER_WRITABLE = re.compile(r"\\(?:appdata|temp|downloads)\\|\\users\\public\\|^[a-z]:\\programdata\\[^\\]+\.exe$", re.I)
HEAVY_MB = 150


def _start(servizio: dict) -> str:
    avvio = WMI_START.get(str(servizio.get("start") or "").lower(), str(servizio.get("start") or "").lower())
    return "delayed-auto" if avvio == "auto" and servizio.get("delayed") else avvio


def is_microsoft(servizio: dict) -> bool:
    azienda = str(servizio.get("company") or "")
    if azienda:
        # Some Windows components (Xbox, GameInput) carry the name of the old Windows driver kit instead.
        return "microsoft" in azienda.lower() or azienda.lower().startswith("windows (r)")
    # No company in the file (or the file cannot be read): Windows folder means Windows.
    return bool(re.match(r"^[a-z]:\\windows\\", str(servizio.get("path") or ""), re.I))


def _text(servizio: dict) -> str:
    return " ".join(str(servizio.get(k) or "") for k in ("name", "display", "company", "path"))


def _finding(servizio: dict, categoria: str, obiettivo: str, motivo: str, selezionato: bool) -> Optional[dict]:
    attuale = _start(servizio)
    if attuale not in RANK or RANK[obiettivo] >= RANK[attuale]:
        return None  # boot/system drivers, or already at (or below) the target
    return {"name": servizio["name"], "display": servizio.get("display") or servizio["name"], "company": servizio.get("company") or "",
            "category": categoria, "label": CATEGORIES[categoria], "start": attuale, "target": obiettivo,
            "running": servizio.get("state") == "Running", "memory_mb": servizio.get("memory_mb") or 0,
            "shared": (servizio.get("shared") or 0) > 1, "reason": motivo, "selected": selezionato}


def _microsoft(servizio: dict, ctx: dict, gestito: bool) -> Optional[dict]:
    nome = servizio["name"]
    on = _start(servizio) in ("auto", "delayed-auto") or servizio.get("state") == "Running"
    if nome in MICROSOFT_OPTIONAL:
        categoria, obiettivo, motivo = MICROSOFT_OPTIONAL[nome]
        if gestito and categoria in ("insecure", "updater"):
            return _finding(servizio, categoria, obiettivo, motivo + " This PC is managed by a company: check with IT first.", False)
        return _finding(servizio, categoria, obiettivo, motivo, True)
    if nome == "dmwappushservice" and not gestito:
        return _finding(servizio, "telemetry", "disabled", "Delivers telemetry and device-management messages; this PC is not managed by a company.", True)
    if nome == "WinRM" and not gestito and _start(servizio) in ("auto", "delayed-auto"):
        return _finding(servizio, "insecure", "demand", "Remote management of the PC is always listening, and no company manages this PC.", True)
    if nome in XBOX and ctx.get("xbox") is False:
        return _finding(servizio, "unused", "disabled", "Xbox and Game Pass services, but the Xbox app is not installed.", True)
    if nome == "PhoneSvc" and ctx.get("phone_link") is False:
        return _finding(servizio, "unused", "disabled", "Phone calls from the PC, but Phone Link is not installed.", True)
    if nome in HARDWARE and ctx.get(HARDWARE[nome][0]) == 0 and on:
        return _finding(servizio, "unused", "demand", HARDWARE[nome][1], True)
    if nome in ("Spooler", "PrintNotify") and ctx.get("printers") == 0:
        return _finding(servizio, "unused", "disabled", "No printer is installed. Microsoft Print to PDF stops working too.", False)
    if nome == "SysMain" and ctx.get("ssd") is True and on:
        return _finding(servizio, "heavy", "disabled", "Preloads apps into memory; on an SSD the gain is small, but it can keep the disk busy.", False)
    if nome == "SharedAccess" and _start(servizio) in ("auto", "delayed-auto") and not gestito:
        return _finding(servizio, "insecure", "demand", "Internet Connection Sharing starts with Windows; the mobile hotspot still starts it when needed.", False)
    return None


def _third_party(servizio: dict, gestito: bool) -> Optional[dict]:
    testo = _text(servizio)
    if not servizio.get("path") or KEEP_ALWAYS.search(testo):  # no program to look at: nothing to judge
        return None
    on = _start(servizio) in ("auto", "delayed-auto") or servizio.get("state") == "Running"
    if UPDATER.search(testo) and _start(servizio) in ("auto", "delayed-auto"):
        motivo = "Checks for updates all day long. On Manual the program still updates itself through its scheduled task or when it opens."
        return _finding(servizio, "updater", "demand", motivo + (" This PC is managed by a company: check with IT first." if gestito else ""), not gestito)
    if TELEMETRY.search(testo):
        return _finding(servizio, "telemetry", "disabled", "Collects usage data or crash reports for the maker; the program works without it.", True)
    if KEEP_HARDWARE.search(testo):
        return None
    if REMOTE.search(testo) and on:
        return _finding(servizio, "remote", "demand", "Remote control is always ready to accept connections. If you do not use it every day, start it only when needed.", False)
    if USER_WRITABLE.search(str(servizio.get("path") or "")) and on:
        return _finding(servizio, "suspicious", "disabled", "Runs from a folder any program can write to (" + str(servizio.get("path")) + "): check what it is.", False)
    if (servizio.get("memory_mb") or 0) >= HEAVY_MB and (servizio.get("shared") or 0) <= 1 and _start(servizio) in ("auto", "delayed-auto") \
            and servizio.get("state") == "Running":
        return _finding(servizio, "heavy", "demand", f"Uses {servizio.get('memory_mb')} MB of memory from the start of Windows.", False)
    return None


def analyze(raw: object) -> dict:
    """Findings for the services of this PC: the selected ones are safe to apply, the others are for review."""
    raw = raw if isinstance(raw, dict) else {}
    ctx = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    gestito = bool(ctx.get("domain") or ctx.get("mdm"))
    servizi = [s for s in op.come_lista(raw.get("services")) if isinstance(s, dict) and s.get("name")]
    protetti = {n.lower() for n in op.SERVIZI_PROTETTI}
    risultati: List[dict] = []
    for servizio in servizi:
        if servizio["name"].lower() in protetti:
            continue
        trovato = _microsoft(servizio, ctx, gestito) if is_microsoft(servizio) else _third_party(servizio, gestito)
        if trovato:
            risultati.append(trovato)
    ordine = list(CATEGORIES)
    risultati.sort(key=lambda f: (not f["selected"], ordine.index(f["category"]), str(f["display"]).lower()))
    return {"findings": risultati, "context": ctx, "managed": gestito, "services": len(servizi),
            "third_party": sum(1 for s in servizi if not is_microsoft(s))}


def collect(ctx=None) -> dict:
    ctx = ctx or op.Contesto(anteprima=True)
    return analyze(ctx.powershell_json(SCRIPT, 180))


def apply(ctx, findings: Iterable[dict], names: Optional[Iterable[str]] = None) -> op.Esito:
    """Applies the chosen findings (by default the selected ones), each to its own target start type."""
    scelti = set(names) if names is not None else None
    per_obiettivo: Dict[str, List[str]] = {}
    for f in findings:
        if (scelti is None and f.get("selected")) or (scelti is not None and f["name"] in scelti):
            per_obiettivo.setdefault(f["target"], []).append(f["name"])
    if not per_obiettivo:
        return op.Esito(op.Stato.OK, "no service to change")
    riusciti = falliti = 0
    for obiettivo, nomi in per_obiettivo.items():
        r, f = op.imposta_servizi(ctx, nomi, obiettivo)
        riusciti, falliti = riusciti + r, falliti + f
    return op.esito_servizi(ctx, riusciti, falliti)


def apply_recommended(ctx) -> op.Esito:
    """The "Disable unnecessary services" action: analyse this PC, then apply only what is safe to apply."""
    analisi = collect(ctx)
    for f in analisi["findings"]:
        if f["selected"]:
            ctx.scrivi(f"  {f['display']} ({f['name']}): {f['label']}, {f['start']} -> {f['target']}")
    return apply(ctx, analisi["findings"])
