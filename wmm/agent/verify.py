"""Before / after checks for the fixes. A check is a short read-only PowerShell script that prints one line (the state
the fix is meant to change) and, when it can be judged, a rule that says whether that state is healthy. The runner
reads it before the fix and again after, so the result says "fixed", "already fine", "not fixed" or "changed".

Fixes without a check of their own are judged by the registry journal (wmm/agent/undo.py): the values they wrote."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, Optional

VERDICTS = ("fixed", "already_ok", "not_fixed", "worse", "changed", "unchanged", "applied", "already_set", "unknown")
TIMEOUT = 45


@dataclass(frozen=True)
class Check:
    label: str
    script: str
    ok: Optional[Callable[[str], bool]] = None


def _service(name: str) -> str:
    return f"$s = Get-Service {name} -ErrorAction SilentlyContinue; if ($s) {{ \"$($s.Status)\" }} else {{ 'Missing' }}"


def _running(value: str) -> bool:
    return value.startswith("Running")


def _equals(expected: str) -> Callable[[str], bool]:
    return lambda value: value == expected


def _devices(classes: str, noun: str) -> str:
    return (f"$d = @(Get-PnpDevice -Class {classes} -PresentOnly -ErrorAction SilentlyContinue); "
            f"if (-not $d) {{ 'No {noun} found' }} elseif ($d | Where-Object Status -ne 'OK') {{ '{noun} with errors' }} else {{ '{noun} OK' }}")


def _service_and_devices(service: str, classes: str, noun: str) -> str:
    return f"$a = $({_service(service)}); $b = $({_devices(classes, noun)}); \"$a / $b\""


INTERNET = ("$p = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.IPv4Connectivity -eq 'Internet' -or $_.IPv6Connectivity -eq 'Internet' }); "
            "$n = if ($p) { 'Internet' } else { 'No internet' }; "
            "$d = try { [void][Net.Dns]::GetHostAddresses('www.microsoft.com'); 'DNS ok' } catch { 'DNS fails' }; \"$n, $d\"")
CHECK_INTERNET = Check("Internet connection and name resolution", INTERNET, _equals("Internet, DNS ok"))


def _dns(*servers: str) -> Check:
    script = ("(@(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object ServerAddresses | "
              "ForEach-Object ServerAddresses) | Sort-Object -Unique) -join ', '")
    return Check("DNS servers of the adapters", script, lambda value: all(s in value for s in servers))


def _registry(path: str, name: str, label: str, ok: Optional[Callable[[str], bool]] = None) -> Check:
    script = (f"$v = (Get-ItemProperty '{path}' -Name '{name}' -ErrorAction SilentlyContinue).'{name}'; "
              "if ($null -eq $v) { 'absent' } else { \"$v\" }")
    return Check(label, script, ok)


def _active_plan(guid: str) -> Check:
    return Check("Active power plan", "(powercfg /getactivescheme) -join ' '", lambda value: guid.lower() in value.lower())


_UX = r"HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
_BITS_STUCK = ("$j = @(Get-BitsTransfer -AllUsers -ErrorAction SilentlyContinue | Where-Object { $_.JobState -in 'Error','TransientError','Suspended' }); "
               "\"$($j.Count) stuck transfers\"")
_PRINT = ("$q = @(Get-Printer -ErrorAction SilentlyContinue | ForEach-Object { Get-PrintJob -PrinterObject $_ -ErrorAction SilentlyContinue }); "
          "$s = (Get-Service Spooler -ErrorAction SilentlyContinue).Status; \"Spooler $s, $($q.Count) jobs queued\"")
_FIREWALL = "$o = @(Get-NetFirewallProfile -ErrorAction SilentlyContinue | Where-Object Enabled -eq $false); \"$($o.Count) profiles off\""
_PROFILES = "(@(Get-NetConnectionProfile -ErrorAction SilentlyContinue | ForEach-Object { \"$($_.Name): $($_.NetworkCategory)\" })) -join '; '"
_DISCOVERY = ("$r = @(Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752' -ErrorAction SilentlyContinue | Where-Object { $_.Profile -match 'Private' }); "
              "$f = (Get-Service FDResPub -ErrorAction SilentlyContinue).Status; "
              "$on = $r.Count -gt 0 -and -not ($r | Where-Object Enabled -eq 'False'); \"Discovery rules $(if ($on) { 'on' } else { 'off' }), FDResPub $f\"")
_GUEST = "$g = Get-LocalUser -ErrorAction SilentlyContinue | Where-Object { $_.SID -like '*-501' }; if ($g) { \"Enabled: $($g.Enabled)\" } else { 'absent' }"
_STANDBY = ("$m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction SilentlyContinue; "
            "\"$([math]::Round(($m.StandbyCacheNormalPriorityBytes + $m.StandbyCacheReserveBytes + $m.StandbyCacheCoreBytes) / 1MB)) MB standby\"")
_WIFI = ("$a = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.NdisPhysicalMedium -eq 9 }); "
         "$s = (Get-Service WlanSvc -ErrorAction SilentlyContinue).Status; \"WlanSvc $s, Wi-Fi $(if ($a) { ($a | ForEach-Object Status) -join '/' } else { 'none' })\"")
_HOSTS = ("$h = Join-Path $env:SystemRoot 'System32\\drivers\\etc\\hosts'; "
          "\"$(@(Get-Content $h -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\\s*[^#\\s]' }).Count) active lines\"")
_WU_POLICIES = ("$n = 0; foreach ($k in 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate', 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU') { "
                "$p = Get-ItemProperty $k -ErrorAction SilentlyContinue; if ($p) { $n += @($p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' }).Count } }; "
                "\"$n update policies\"")


def _process(*names: str) -> Check:
    script = ("(@(" + ", ".join(f"'{n}'" for n in names) + ") | ForEach-Object { if (Get-Process $_ -ErrorAction SilentlyContinue) "
              "{ \"$_ running\" } else { \"$_ not running\" } }) -join ', '")
    return Check("Processes", script, lambda value: "not running" not in value)


def _defender(prop: str, label: str, ok: Callable[[str], bool]) -> Check:
    return Check(label, f"$m = Get-MpComputerStatus -ErrorAction SilentlyContinue; if ($m) {{ \"$($m.{prop})\" }} else {{ 'Defender unavailable' }}", ok)


def _pref(prop: str, label: str, ok: Callable[[str], bool]) -> Check:
    return Check(label, f"$m = Get-MpPreference -ErrorAction SilentlyContinue; if ($m) {{ \"$($m.{prop})\" }} else {{ 'Defender unavailable' }}", ok)


def _number_at_most(limit: int) -> Callable[[str], bool]:
    def ok(value: str) -> bool:
        trovato = re.match(r"\s*(\d+)", value)
        return bool(trovato) and int(trovato.group(1)) <= limit
    return ok


_BALANCED, _HIGH = "381b4222-f694-41f0-9685-ff5bb260df2e", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
_CONNECTIVITY_FIXES = ("network.flush_dns", "network.renew_ip", "network.ncsi_reset", "network.reset_proxy", "network.winsock_reset", "network.reset",
                       "network.reset_tcpip", "network.restart_adapters", "network.dns_auto", "services.restart_network_location", "network.optimize",
                       "network.purge_netbios", "network.clear_arp")

CHECKS: Dict[str, Check] = {
    # network
    **{a: CHECK_INTERNET for a in _CONNECTIVITY_FIXES},
    "network.dns_cloudflare": _dns("1.1.1.1"),
    "network.dns_google": _dns("8.8.8.8"),
    "network.dns_quad9": _dns("9.9.9.9"),
    "network.dns_adguard": _dns("94.140.14.14"),
    "network.profile_private": Check("Network profiles", _PROFILES, lambda value: "Public" not in value),
    "network.discovery_on": Check("Network discovery", _DISCOVERY, lambda value: value.startswith("Discovery rules on") and "Running" in value),
    "network.autotuning_normal": Check("Receive window auto-tuning",
                                       "(Get-NetTCPSetting -SettingName Internet -ErrorAction SilentlyContinue).AutoTuningLevelLocal", _equals("Normal")),
    "network.reset_hosts": Check("Hosts file", _HOSTS, _equals("0 active lines")),
    "network.reset_firewall": Check("Firewall profiles", _FIREWALL, _equals("0 profiles off")),
    # devices and services
    "services.restart_camera": Check("Camera devices", _devices("Camera,Image", "Camera"), _equals("Camera OK")),
    "services.restart_bluetooth": Check("Bluetooth service and devices", _service_and_devices("bthserv", "Bluetooth", "Bluetooth"),
                                        lambda value: value.startswith("Running") and "Bluetooth OK" in value),
    "services.restart_audio": Check("Windows Audio and sound devices", _service_and_devices("Audiosrv", "AudioEndpoint", "Sound device"),
                                    lambda value: value.startswith("Running") and "Sound device OK" in value),
    "services.restart_spooler": Check("Print spooler", _PRINT, lambda value: value.startswith("Spooler Running")),
    "services.clear_print_queue": Check("Print queue", _PRINT, _equals("Spooler Running, 0 jobs queued")),
    "services.restart_wlan": Check("Wi-Fi service and adapter", _WIFI, lambda value: value.startswith("WlanSvc Running") and "Wi-Fi Up" in value),
    "services.restart_search": Check("Windows Search service", _service("WSearch"), _running),
    "services.rebuild_search_index": Check("Windows Search service", _service("WSearch"), _running),
    "services.restart_time": Check("Windows Time service", _service("W32Time"), _running),
    "integrity.time_sync": Check("Windows Time service", _service("W32Time"), _running),
    "services.restart_cryptsvc": Check("Cryptographic Services", _service("CryptSvc"), _running),
    "services.restart_biometrics": Check("Windows Hello service and readers", _service_and_devices("WbioSrvc", "Biometric", "Reader"),
                                         lambda value: value.startswith("Running") and "Reader OK" in value),
    "services.restart_text_input": _process("ctfmon"),
    "startup.reset_start_menu": _process("StartMenuExperienceHost", "explorer"),
    "performance.restart_explorer": _process("explorer"),
    "startup.reset_notifications": Check("Notification service", _service("WpnService"), _running),
    "integrity.reregister_msi": Check("Windows Installer service", "(Get-Service msiserver -ErrorAction SilentlyContinue).StartType",
                                      lambda value: value in ("Manual", "Automatic")),
    # updates
    "services.restart_wu": Check("Background transfers", _BITS_STUCK, _equals("0 stuck transfers")),
    "updates.bits_reset": Check("Background transfers", _BITS_STUCK, _equals("0 stuck transfers")),
    "integrity.reset_wu": Check("Windows Update service", _service("wuauserv"), lambda value: value != "Missing"),
    "updates.resume_updates": _registry(_UX, "PauseUpdatesExpiryTime", "Update pause", _equals("absent")),
    "updates.remove_wu_policies": Check("Windows Update policies", _WU_POLICIES, _equals("0 update policies")),
    "integrity.verifier_off": _registry(r"HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "VerifyDrivers",
                                        "Driver Verifier", _equals("absent")),
    # security
    "security.firewall_on": Check("Firewall profiles", _FIREWALL, _equals("0 profiles off")),
    "security.update_signatures": _defender("AntivirusSignatureAge", "Antivirus signature age (days)", _number_at_most(1)),
    "security.quick_scan": _defender("QuickScanAge", "Days since the last quick scan", _number_at_most(0)),
    "security.full_scan": _defender("FullScanAge", "Days since the last full scan", _number_at_most(0)),
    "security.disable_smb1": Check("SMBv1 server", "(Get-SmbServerConfiguration -ErrorAction SilentlyContinue).EnableSMB1Protocol", _equals("False")),
    "security.pua_protection": _pref("PUAProtection", "Unwanted app blocking", _equals("1")),
    "security.network_protection": _pref("EnableNetworkProtection", "Network protection", _equals("1")),
    "security.defender_cloud_on": _pref("MAPSReporting", "Cloud protection", lambda value: value in ("1", "2")),
    "security.disable_guest": Check("Guest account", _GUEST, lambda value: value in ("Enabled: False", "absent")),
    # performance and storage
    "performance.power_balanced": _active_plan(_BALANCED),
    "performance.power_high": _active_plan(_HIGH),
    "performance.free_memory": Check("Standby memory", _STANDBY),
    "performance.hibernation_off": _registry(r"HKLM:\SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled", "Hibernation", _equals("0")),
    "performance.hibernation_on": _registry(r"HKLM:\SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled", "Hibernation", _equals("1")),
    "storage.trim_enable": _registry(r"HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem", "DisableDeleteNotification", "TRIM disabled flag",
                                     lambda value: value in ("0", "absent")),
}


def run_script(script: str, timeout: int = TIMEOUT) -> str:
    """The last line the check printed (read-only PowerShell, no window)."""
    from .tools import powershell_command
    finito = subprocess.run(powershell_command(script), capture_output=True, text=True, timeout=timeout,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), encoding="utf-8", errors="replace")
    righe = [r.strip() for r in (finito.stdout or "").splitlines() if r.strip()]
    return (righe[-1] if righe else "no output")[:200]


def read(check: Check, runner: Optional[Callable[[str], str]] = None) -> Optional[str]:
    try:
        return (runner or run_script)(check.script)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def verdict(check: Check, prima: Optional[str], dopo: Optional[str]) -> str:
    if prima is None or dopo is None:
        return "unknown"
    if check.ok is None:
        return "unchanged" if prima == dopo else "changed"
    sano_prima, sano_dopo = check.ok(prima), check.ok(dopo)
    if sano_dopo:
        return "already_ok" if sano_prima else "fixed"
    return "worse" if sano_prima else "not_fixed"


class Probe:
    """The check of one fix: read before it runs (on creation), finish() after."""

    def __init__(self, action_id: str, runner: Optional[Callable[[str], str]] = None):
        self.check = CHECKS.get(action_id)
        self.runner = runner
        self.before = read(self.check, runner) if self.check else None

    def finish(self, registry_changes: Optional[list] = None, registry_seen: int = 0) -> Optional[dict]:
        if self.check is not None:
            dopo = read(self.check, self.runner)
            return {"label": self.check.label, "before": self.before, "after": dopo, "verdict": verdict(self.check, self.before, dopo)}
        if registry_seen:
            cambiati = len(registry_changes or [])
            return {"label": "Registry values written by the fix", "before": f"{registry_seen} values read",
                    "after": f"{cambiati} changed", "verdict": "applied" if cambiati else "already_set"}
        return None


LABELS = {"fixed": "Fixed", "already_ok": "Already fine", "not_fixed": "Not fixed", "worse": "Worse than before", "changed": "Changed",
          "unchanged": "Nothing changed", "applied": "Applied", "already_set": "Already set", "unknown": "Not verified"}


def summary(risultato: dict) -> str:
    return f"Check: {risultato['label']}: before \"{risultato['before']}\", after \"{risultato['after']}\" - {LABELS[risultato['verdict']]}"
