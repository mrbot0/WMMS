"""Implementations of the extended actions. Every function takes an ottimizza_pc
context, honors preview mode through ctx.modifica/ctx.comando and returns an Esito."""
from __future__ import annotations

import base64
import ctypes
import fnmatch
import glob
import os
import stat
from typing import List, Optional, Sequence, Tuple

import wmm  # noqa: F401
import ottimizza_pc as op
from ottimizza_pc import Esito, SequenzaFermata, Stato

REPARSE_POINT = 0x400
POWER_GUIDS = {
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "high": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
}
VISUAL_EFFECTS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
STORAGE_SENSE_KEY = r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy"

_CACHE_DIRS = ("Cache", "Code Cache", "GPUCache")
BROWSER_CACHES = [
    rf"%LOCALAPPDATA%\{browser}\User Data\*\{cartella}"
    for browser in (r"Microsoft\Edge", r"Google\Chrome", r"BraveSoftware\Brave-Browser")
    for cartella in _CACHE_DIRS
] + [r"%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*\cache2"]
WER_FOLDERS = [
    r"%ProgramData%\Microsoft\Windows\WER\ReportArchive",
    r"%ProgramData%\Microsoft\Windows\WER\ReportQueue",
    r"%ProgramData%\Microsoft\Windows\WER\Temp",
    r"%LOCALAPPDATA%\Microsoft\Windows\WER\ReportArchive",
    r"%LOCALAPPDATA%\Microsoft\Windows\WER\ReportQueue",
]
THUMBNAIL_CACHE = (r"%LOCALAPPDATA%\Microsoft\Windows\Explorer", "thumbcache_*.db")


# ---------- filesystem helpers ----------

def expand(patterns: Sequence[str]) -> List[str]:
    trovati = set()
    for modello in patterns:
        for percorso in glob.glob(os.path.expandvars(modello)):
            if os.path.isdir(percorso):
                trovati.add(percorso)
    return sorted(trovati)


def _files(root: str, pattern: Optional[str], older_than: Optional[float] = None, exclude: Sequence[str] = ()):
    """Regular files under root (pattern: only that folder), never following links or junctions.
    `older_than` keeps only files modified before that time; `exclude` skips folders by name."""
    bloccati = {nome.lower() for nome in exclude}
    pila = [root]
    while pila:
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
                    if pattern is None and voce.name.lower() not in bloccati:
                        pila.append(voce.path)
                elif stat.S_ISREG(info.st_mode) and (pattern is None or fnmatch.fnmatch(voce.name.lower(), pattern.lower())) \
                        and (older_than is None or info.st_mtime < older_than):
                    yield voce.path, info.st_size


def wipe(targets: Sequence[Tuple[str, Optional[str]]], preview: bool, older_than: Optional[float] = None,
         exclude: Sequence[str] = ()) -> Tuple[int, int, int]:
    """Deletes files (folders stay). Returns bytes freed, files deleted, files skipped (in use)."""
    totale = file = saltati = 0
    for cartella, pattern in targets:
        if not os.path.isdir(cartella):
            continue
        for percorso, peso in _files(cartella, pattern, older_than, exclude):
            if not preview:
                try:
                    os.remove(percorso)
                except OSError:
                    saltati += 1
                    continue
            totale += peso
            file += 1
    return totale, file, saltati


def _wipe_action(ctx, descrizione: str, targets: Sequence[Tuple[str, Optional[str]]]) -> Esito:
    anteprima = not ctx.modifica(descrizione)
    totale, file, saltati = wipe(targets, preview=anteprima)
    nota = f"{op.dimensione(totale)} in {file} files" + (f", {saltati} files in use were skipped" if saltati else "")
    ctx.scrivi(f"  {nota}")
    return Esito(Stato.ANTEPRIMA if anteprima else Stato.OK, nota)


def clean_temp(ctx) -> Esito:
    """Same rules as ottimizza_pc.pulizia_file (files older than GIORNI_FILE_VECCHI days, excluded
    folders, no links), with a scandir walk that is much faster on huge temp folders."""
    import time
    limite = time.time() - op.GIORNI_FILE_VECCHI * 86400
    anteprima = not ctx.modifica("Delete temporary files and caches older than %d days" % op.GIORNI_FILE_VECCHI)
    totale = file = saltati = 0
    for modello in op.CARTELLE_PULIZIA:
        radice = os.path.expandvars(modello)
        if "%" in radice or not os.path.isdir(radice):
            continue
        peso, numero, bloccati = wipe([(radice, None)], anteprima, limite, op.ESCLUSI_PULIZIA)
        ctx.scrivi(f"  {radice}: {op.dimensione(peso)}")
        totale, file, saltati = totale + peso, file + numero, saltati + bloccati
    if ctx.modifica("Clear Delivery Optimization cache"):
        ctx.powershell("Delete-DeliveryOptimizationCache -Force", timeout=300)
    nota = f"{op.dimensione(totale)} in {file} files" + (f", {saltati} files in use were skipped" if saltati else "")
    return Esito(Stato.ANTEPRIMA if anteprima else Stato.OK, nota)


def clean_browser_caches(ctx) -> Esito:
    return _wipe_action(ctx, "Delete browser cache files (Edge, Chrome, Brave, Firefox)", [(p, None) for p in expand(BROWSER_CACHES)])


def clean_error_reports(ctx) -> Esito:
    return _wipe_action(ctx, "Delete Windows Error Reporting files", [(p, None) for p in expand(WER_FOLDERS)])


def clean_thumbnails(ctx) -> Esito:
    return _wipe_action(ctx, "Delete thumbnail cache", [(os.path.expandvars(THUMBNAIL_CACHE[0]), THUMBNAIL_CACHE[1])])


# ---------- registry ----------

def write_dword(root: str, key: str, name: str, value: int) -> None:
    import winreg
    with winreg.CreateKeyEx(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, name, 0, winreg.REG_DWORD, int(value))


def set_visual_effects(ctx, best_performance: bool) -> Esito:
    valore = 2 if best_performance else 0
    if not ctx.modifica(f"Registry HKCU\\{VISUAL_EFFECTS_KEY}\\VisualFXSetting = {valore}"):
        return Esito(Stato.ANTEPRIMA)
    write_dword("HKEY_CURRENT_USER", VISUAL_EFFECTS_KEY, "VisualFXSetting", valore)
    return Esito(Stato.OK, "applies at the next sign-in")


def enable_storage_sense(ctx) -> Esito:
    if not ctx.modifica(f"Registry HKCU\\{STORAGE_SENSE_KEY}\\01 = 1"):
        return Esito(Stato.ANTEPRIMA)
    write_dword("HKEY_CURRENT_USER", STORAGE_SENSE_KEY, "01", 1)
    return Esito(Stato.OK, "Storage Sense enabled")


# ---------- commands ----------

def powershell_command(script: str) -> List[str]:
    codificato = base64.b64encode(("$ProgressPreference='SilentlyContinue';" + script).encode("utf-16-le")).decode()
    return ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificato]


def set_power_plan(ctx, plan: str) -> Esito:
    esito = ctx.comando(["powercfg", "/setactive", POWER_GUIDS[plan]])
    if esito.stato is Stato.OK:
        esito.nota = f"{plan} power plan active"
    return esito


def optimize_volumes(ctx) -> Esito:
    return ctx.comando(["defrag", "/C", "/O"])


def flush_network_caches(ctx) -> Esito:
    return op.comandi_in_serie(ctx, (["ipconfig", "/flushdns"], ["netsh", "interface", "ip", "delete", "arpcache"]))


def defender_quick_scan(ctx) -> Esito:
    return ctx.comando(powershell_command("Start-MpScan -ScanType QuickScan; 'Quick scan completed.'"))


def defender_update_signatures(ctx) -> Esito:
    return ctx.comando(powershell_command("Update-MpSignature; 'Signatures: ' + (Get-MpComputerStatus).AntivirusSignatureVersion"))


def disable_smb1(ctx) -> Esito:
    return ctx.comando(powershell_command("Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force; 'SMBv1 server disabled.'"))


def create_restore_point(ctx) -> Esito:
    try:
        return op.punto_ripristino(ctx)
    except SequenzaFermata as motivo:
        return Esito(Stato.ERRORE, str(motivo))


def windows_update_scan(ctx) -> Esito:
    return ctx.comando([os.path.expandvars(r"%SystemRoot%\System32\UsoClient.exe"), "StartScan"])


def optimize_startup(ctx) -> Esito:
    """Turns off every enabled startup entry that is not essential (same switch as Task Manager)."""
    from . import inventory
    da_spegnere = [v for v in inventory.startup_items() if v["enabled"] and not inventory.is_essential_startup(v)]
    mantenute = [v["name"] for v in inventory.startup_items() if v["enabled"] and inventory.is_essential_startup(v)]
    anteprima = getattr(ctx, "anteprima", False)
    spente = falliti = 0
    for voce in da_spegnere:
        if not ctx.modifica(f"Disable startup entry {voce['name']} ({voce['location']})"):
            continue
        try:
            inventory.set_startup_enabled(voce, False)
            spente += 1
        except OSError as errore:
            falliti += 1
            ctx.scrivi(f"  [error] {voce['name']}: {errore}")
    if mantenute:
        ctx.scrivi("  Kept (essential): " + ", ".join(mantenute))
    if anteprima:
        return Esito(Stato.ANTEPRIMA, f"{len(da_spegnere)} would be disabled, {len(mantenute)} kept")
    nota = f"{spente} disabled, {len(mantenute)} essential kept" + (f", {falliti} failed" if falliti else "")
    return Esito(Stato.AVVISO if falliti else Stato.OK, nota)


def restart_explorer(ctx) -> Esito:
    # Winlogon restarts the shell automatically (AutoRestartShell), unelevated as before.
    esito = ctx.comando(["taskkill", "/f", "/im", "explorer.exe"])
    if esito.stato is Stato.OK:
        esito.nota = "Explorer restarted"
    return esito


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class _TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", ctypes.c_uint32), ("Luid", _LUID), ("Attributes", ctypes.c_uint32)]


def _enable_privilege(name: str) -> bool:
    advapi, kernel = ctypes.windll.advapi32, ctypes.windll.kernel32
    token = ctypes.c_void_p()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(token)):  # ADJUST | QUERY
        return False
    try:
        privilegi = _TOKEN_PRIVILEGES(1, _LUID(), 0x2)  # SE_PRIVILEGE_ENABLED
        if not advapi.LookupPrivilegeValueW(None, name, ctypes.byref(privilegi.Luid)):
            return False
        advapi.AdjustTokenPrivileges(token, False, ctypes.byref(privilegi), 0, None, None)
        return kernel.GetLastError() == 0
    finally:
        kernel.CloseHandle(token)


SYSTEM_MEMORY_LIST_INFORMATION = 80
MEMORY_PURGE_STANDBY_LIST = 4


def free_standby_memory(ctx) -> Esito:
    """Empties the standby list (cached file pages), like RAMMap › Empty Standby List."""
    if not ctx.modifica("Empty the standby memory list"):
        return Esito(Stato.ANTEPRIMA)
    from .inventory import memory_status
    prima = memory_status()["free_gb"]
    if not _enable_privilege("SeProfileSingleProcessPrivilege"):
        return Esito(Stato.ERRORE, "the privilege to manage memory lists is not available (run as administrator)")
    comando = ctypes.c_int(MEMORY_PURGE_STANDBY_LIST)
    stato = ctypes.windll.ntdll.NtSetSystemInformation(SYSTEM_MEMORY_LIST_INFORMATION, ctypes.byref(comando), ctypes.sizeof(comando))
    if stato != 0:
        return Esito(Stato.ERRORE, f"NtSetSystemInformation failed (0x{stato & 0xFFFFFFFF:08X})")
    dopo = memory_status()["free_gb"]
    nota = f"free memory {prima} GB → {dopo} GB"
    ctx.scrivi(f"  {nota}")
    return Esito(Stato.OK, nota)


def clean_delivery_optimization(ctx) -> Esito:
    return ctx.comando(powershell_command("Delete-DeliveryOptimizationCache -Force; 'Delivery Optimization cache cleared.'"))


def renew_ip(ctx) -> Esito:
    return op.comandi_in_serie(ctx, (["ipconfig", "/release"], ["ipconfig", "/renew"], ["ipconfig", "/flushdns"]))


def defender_full_scan(ctx) -> Esito:
    return ctx.comando(powershell_command("Start-MpScan -ScanType FullScan; 'Full scan completed.'"))


def firewall_on(ctx) -> Esito:
    return ctx.comando(powershell_command("Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True; "
                                          "Get-NetFirewallProfile | ForEach-Object { \"$($_.Name): $($_.Enabled)\" }"))


def store_apps_update(ctx) -> Esito:
    return ctx.comando(powershell_command(
        "Get-CimInstance -Namespace 'root\\cimv2\\mdm\\dmmap' -ClassName 'MDM_EnterpriseModernAppManagement_AppManagement01' | "
        "Invoke-CimMethod -MethodName UpdateScanMethod | Out-Null; 'Microsoft Store update scan started.'"))


def wmi_verify(ctx) -> Esito:
    return ctx.comando(["winmgmt", "/verifyrepository"])


SCRIPT_RESET_WU = r"""
$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
'Stopping update services...'
Stop-Service wuauserv, bits, cryptsvc -Force
foreach ($p in "$env:SystemRoot\SoftwareDistribution", "$env:SystemRoot\System32\catroot2") {
  if (Test-Path $p) { Rename-Item $p "$(Split-Path $p -Leaf).wmm-$stamp"; "Renamed $p" }
}
'Starting update services...'
Start-Service cryptsvc, bits, wuauserv
'Windows Update components reset.'
"""


def reset_windows_update(ctx) -> Esito:
    return ctx.comando(powershell_command(SCRIPT_RESET_WU))


# ---------- extended actions (iteration 4) ----------

def write_string(root: str, key: str, name: str, value: str) -> None:
    import winreg
    with winreg.CreateKeyEx(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)


def _registry_action(ctx, descrizione: str, scrivi, nota: str) -> Esito:
    if not ctx.modifica(descrizione):
        return Esito(Stato.ANTEPRIMA)
    scrivi()
    return Esito(Stato.OK, nota)


def power_ultimate(ctx) -> Esito:
    return ctx.comando(powershell_command(
        "$o = powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61; "
        "$g = [regex]::Match(\"$o\", '[0-9a-fA-F-]{36}').Value; if (-not $g) { throw 'Ultimate Performance is not available' }; "
        "powercfg /setactive $g; \"Ultimate Performance active ($g)\""))


def set_hibernation(ctx, enabled: bool) -> Esito:
    return ctx.comando(["powercfg", "/hibernate", "on" if enabled else "off"])


def set_background_apps(ctx, enabled: bool) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications"
    return _registry_action(ctx, f"Registry HKCU\\{chiave}\\GlobalUserDisabled = {0 if enabled else 1}",
                            lambda: write_dword("HKEY_CURRENT_USER", chiave, "GlobalUserDisabled", 0 if enabled else 1),
                            "background apps " + ("allowed" if enabled else "stopped"))


def clean_windows_logs(ctx) -> Esito:
    import time
    radice = os.path.expandvars(r"%SystemRoot%\Logs")
    obiettivi = [(os.path.join(radice, "CBS"), "*.log"), (os.path.join(radice, "CBS"), "*.cab"), (os.path.join(radice, "DISM"), "*.log"),
                 (os.path.join(radice, "MoSetup"), "*.log"), (os.path.join(radice, "WindowsUpdate"), "*.etl")]
    anteprima = not ctx.modifica("Delete Windows setup and servicing logs older than 7 days")
    totale, file, saltati = wipe(obiettivi, anteprima, time.time() - 7 * 86400)
    nota = f"{op.dimensione(totale)} in {file} files" + (f", {saltati} in use" if saltati else "")
    ctx.scrivi(f"  {nota}")
    return Esito(Stato.ANTEPRIMA if anteprima else Stato.OK, nota)


def compact_os(ctx) -> Esito:
    return ctx.comando(["compact", "/compactos:always"])


def reset_winhttp_proxy(ctx) -> Esito:
    return ctx.comando(["netsh", "winhttp", "reset", "proxy"])


def reset_firewall(ctx) -> Esito:
    return ctx.comando(["netsh", "advfirewall", "reset"])


def smartscreen_on(ctx) -> Esito:
    chiave = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\SmartScreenEnabled = Warn",
                            lambda: write_string("HKEY_LOCAL_MACHINE", chiave, "SmartScreenEnabled", "Warn"), "SmartScreen set to warn")


def disable_autorun(ctx) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\NoDriveTypeAutoRun = 255",
                            lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "NoDriveTypeAutoRun", 255), "AutoRun disabled on all drives")


def uac_on(ctx) -> Esito:
    chiave = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    esito = _registry_action(ctx, f"Registry HKLM\\{chiave}\\EnableLUA = 1",
                             lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "EnableLUA", 1), "UAC enabled; restart required")
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
    return esito


def disable_guest(ctx) -> Esito:
    return ctx.comando(powershell_command("Get-LocalUser | Where-Object { \"$($_.SID)\" -like '*-501' } | Disable-LocalUser; 'Guest account disabled.'"))


def rdp_off(ctx) -> Esito:
    chiave = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\fDenyTSConnections = 1",
                            lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "fDenyTSConnections", 1), "Remote Desktop disabled")


def enable_system_restore(ctx) -> Esito:
    return ctx.comando(powershell_command("Enable-ComputerRestore -Drive \"$env:SystemDrive\\\"; 'System Restore enabled on the system drive.'"))


def pua_protection(ctx) -> Esito:
    return ctx.comando(powershell_command("Set-MpPreference -PUAProtection Enabled; 'Potentially unwanted app protection enabled.'"))


def winget_upgrade(ctx) -> Esito:
    return ctx.comando(["winget", "upgrade", "--all", "--silent", "--accept-package-agreements", "--accept-source-agreements",
                        "--disable-interactivity"])


def dism_scan(ctx) -> Esito:
    return ctx.comando(["DISM", "/Online", "/Cleanup-Image", "/ScanHealth"])


def rebuild_icon_cache(ctx) -> Esito:
    esito = ctx.comando(["taskkill", "/f", "/im", "explorer.exe"])
    if esito.stato is Stato.ANTEPRIMA:
        return esito
    cartella = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Explorer")
    totale, file, _ = wipe([(cartella, "iconcache_*.db"), (os.path.expandvars("%LOCALAPPDATA%"), "IconCache.db")], preview=False)
    return Esito(Stato.OK, f"{file} cache files removed ({op.dimensione(totale)}); Explorer restarts by itself")


def time_sync(ctx) -> Esito:
    return ctx.comando(powershell_command("Set-Service W32Time -StartupType Automatic; Start-Service W32Time; w32tm /resync /force"))


def store_reset(ctx) -> Esito:
    return ctx.comando(["wsreset.exe", "-i"])


def restart_service(ctx, nome: str) -> Esito:
    return ctx.comando(powershell_command(f"Restart-Service -Name '{nome}' -Force; (Get-Service -Name '{nome}').Status"))


def restore_all_startup(ctx) -> Esito:
    from . import inventory
    spente = [v for v in inventory.startup_items() if not v["enabled"]]
    riattivate = 0
    for voce in spente:
        if ctx.modifica(f"Enable startup entry {voce['name']}"):
            inventory.set_startup_enabled(voce, True)
            riattivate += 1
    if getattr(ctx, "anteprima", False):
        return Esito(Stato.ANTEPRIMA, f"{len(spente)} would be turned on")
    return Esito(Stato.OK, f"{riattivate} startup programs turned on")


SCRIPT_INSTALL_UPDATES = r"""
$session = New-Object -ComObject Microsoft.Update.Session
$found = $session.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0 and Type='Software' and BrowseOnly=0")
if ($found.Updates.Count -eq 0) { 'No updates to install.'; exit 0 }
$list = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $found.Updates) { if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$list.Add($u); "Queued: $($u.Title)" }
$dl = $session.CreateUpdateDownloader(); $dl.Updates = $list; 'Downloading...'; [void]$dl.Download()
$inst = $session.CreateUpdateInstaller(); $inst.Updates = $list; 'Installing...'; $res = $inst.Install()
"Result code: $($res.ResultCode)"
if ($res.RebootRequired) { 'A restart is required to finish.' }
if ($res.ResultCode -in 2, 3) { exit 0 } else { exit 1 }
"""


def windows_update_install(ctx) -> Esito:
    esito = ctx.comando(powershell_command(SCRIPT_INSTALL_UPDATES))
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
        esito.nota = "updates installed; a restart may be required"
    return esito
