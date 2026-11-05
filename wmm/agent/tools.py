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
from ottimizza_pc import Esito, Stato

from . import undo

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
    undo.before_write(root, key, name)
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
    if not ctx.anteprima:
        undo.before_plan()
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


SYSTEM_RESTORE_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore"
RESTORE_FREQUENCY = "SystemRestorePointCreationFrequency"
SCRIPT_LAST_RESTORE_POINT = "(Get-ComputerRestorePoint | Select-Object -Last 1 | ForEach-Object { $_.SequenceNumber })"


def read_dword(root: str, key: str, name: str) -> Optional[int]:
    import winreg
    try:
        with winreg.OpenKey(getattr(winreg, root), key) as handle:
            return int(winreg.QueryValueEx(handle, name)[0])
    except (OSError, ValueError):
        return None


def delete_value(root: str, key: str, name: str) -> None:
    import winreg
    undo.before_write(root, key, name)
    try:
        with winreg.OpenKey(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
            winreg.DeleteValue(handle, name)
    except OSError:
        pass  # already absent


def create_restore_point(ctx, description: str = "Windows Maintenance Manager") -> Esito:
    """Creates a restore point now. Windows normally skips a new point when one is less than
    24 hours old: the limit is lifted for this call only and then put back as it was."""
    if not ctx.modifica(f"Create a restore point ({description})"):
        return Esito(Stato.ANTEPRIMA)
    prima = ctx.powershell(SCRIPT_LAST_RESTORE_POINT)
    precedente = read_dword("HKEY_LOCAL_MACHINE", SYSTEM_RESTORE_KEY, RESTORE_FREQUENCY)
    write_dword("HKEY_LOCAL_MACHINE", SYSTEM_RESTORE_KEY, RESTORE_FREQUENCY, 0)
    try:
        ctx.powershell("Enable-ComputerRestore -Drive 'C:\\'; "
                       f"Checkpoint-Computer -Description '{description}' -RestorePointType MODIFY_SETTINGS", timeout=600)
    finally:
        if precedente is None:
            delete_value("HKEY_LOCAL_MACHINE", SYSTEM_RESTORE_KEY, RESTORE_FREQUENCY)
        else:
            write_dword("HKEY_LOCAL_MACHINE", SYSTEM_RESTORE_KEY, RESTORE_FREQUENCY, precedente)
    dopo = ctx.powershell(SCRIPT_LAST_RESTORE_POINT)
    if not dopo or dopo == prima:
        return Esito(Stato.ERRORE, "Windows did not create the restore point: turn on System Restore for C: and try again")
    ctx.scrivi(f"  Restore point #{dopo} created")
    return Esito(Stato.OK, f"restore point #{dopo} created")


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
    undo.before_write(root, key, name)
    with winreg.CreateKeyEx(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)


def _registry_action(ctx, descrizione: str, scrivi, nota: str) -> Esito:
    if not ctx.modifica(descrizione):
        return Esito(Stato.ANTEPRIMA)
    scrivi()
    return Esito(Stato.OK, nota)


def power_ultimate(ctx) -> Esito:
    if not ctx.anteprima:
        undo.before_plan()
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


def ctx_restart_many(ctx, nomi) -> Esito:
    elenco = ", ".join(f"'{n}'" for n in nomi)
    return ctx.comando(powershell_command(f"Restart-Service -Name {elenco} -Force; Get-Service -Name {elenco} | ForEach-Object {{ \"$($_.Name): $($_.Status)\" }}"))


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


# ---------- extended actions (iteration 5) ----------

def set_transparency(ctx, enabled: bool) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    return _registry_action(ctx, f"Registry HKCU\\{chiave}\\EnableTransparency = {int(enabled)}",
                            lambda: write_dword("HKEY_CURRENT_USER", chiave, "EnableTransparency", int(enabled)),
                            "transparency " + ("on" if enabled else "off"))


def mouse_precision_off(ctx) -> Esito:
    def scrivi():
        for nome in ("MouseSpeed", "MouseThreshold1", "MouseThreshold2"):
            write_string("HKEY_CURRENT_USER", r"Control Panel\Mouse", nome, "0")
    return _registry_action(ctx, "Registry HKCU\\Control Panel\\Mouse: acceleration off", scrivi, "pointer precision off; applies at the next sign-in")


def search_manual(ctx) -> Esito:
    return op.esito_servizi(ctx, *op.imposta_servizi(ctx, ["WSearch"], "demand"))


def delete_oldest_restore_point(ctx) -> Esito:
    return ctx.comando(["vssadmin", "delete", "shadows", "/for=C:", "/oldest", "/quiet"])


def clear_ie_cache(ctx) -> Esito:
    return ctx.comando(["RunDll32.exe", "InetCpl.cpl,ClearMyTracksByProcess", "8"])


DEFAULT_HOSTS = ("# Copyright (c) 1993-2009 Microsoft Corp.\n#\n# This is a sample HOSTS file used by Microsoft TCP/IP for Windows.\n#\n"
                 "# localhost name resolution is handled within DNS itself.\n#\t127.0.0.1       localhost\n#\t::1             localhost\n")


def reset_hosts(ctx) -> Esito:
    import shutil as _shutil
    import time
    percorso = os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts")
    copia = percorso + time.strftime(".wmm-%Y%m%d-%H%M%S")
    if not ctx.modifica(f"Back up the hosts file to {copia} and restore the Windows default"):
        return Esito(Stato.ANTEPRIMA)
    if os.path.exists(percorso):
        _shutil.copy2(percorso, copia)
    with open(percorso, "w", encoding="ascii") as file:
        file.write(DEFAULT_HOSTS)
    return Esito(Stato.OK, f"default hosts file restored; backup {os.path.basename(copia)}")


def purge_netbios(ctx) -> Esito:
    return ctx.comando(["nbtstat", "-R"])


def defender_offline_scan(ctx) -> Esito:
    return ctx.comando(powershell_command("Start-MpWDOScan; 'Offline scan scheduled: the PC restarts now.'"))


def block_smb_guest(ctx) -> Esito:
    chiave = r"SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\AllowInsecureGuestAuth = 0",
                            lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "AllowInsecureGuestAuth", 0), "insecure guest logons blocked")


def lsa_protection(ctx) -> Esito:
    esito = _registry_action(ctx, "Registry HKLM\\SYSTEM\\CurrentControlSet\\Control\\Lsa\\RunAsPPL = 1",
                             lambda: write_dword("HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Lsa", "RunAsPPL", 1),
                             "LSA protection enabled; restart required")
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
    return esito


def disable_llmnr(ctx) -> Esito:
    chiave = r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\EnableMulticast = 0",
                            lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "EnableMulticast", 0), "LLMNR disabled")


def clear_recent_items(ctx) -> Esito:
    return _wipe_action(ctx, "Delete the recent items list", [(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent"), "*.lnk")])


def reduce_telemetry(ctx) -> Esito:
    chiave = r"SOFTWARE\Policies\Microsoft\Windows\DataCollection"
    return _registry_action(ctx, f"Registry HKLM\\{chiave}\\AllowTelemetry = 1",
                            lambda: write_dword("HKEY_LOCAL_MACHINE", chiave, "AllowTelemetry", 1), "diagnostic data set to required only")


def disable_advertising_id(ctx) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo"
    return _registry_action(ctx, f"Registry HKCU\\{chiave}\\Enabled = 0",
                            lambda: write_dword("HKEY_CURRENT_USER", chiave, "Enabled", 0), "advertising ID off")


def driver_scan(ctx) -> Esito:
    return ctx.comando(["pnputil", "/scan-devices"])


def office_update(ctx) -> Esito:
    from .inventory import OFFICE_C2R
    if not os.path.isfile(OFFICE_C2R):
        return Esito(Stato.ERRORE, "Microsoft 365 / Office Click-to-Run is not installed")
    return ctx.comando([OFFICE_C2R, "/update", "user", "displaylevel=false", "forceappshutdown=false"])


def chkdsk_all(ctx) -> Esito:
    return ctx.comando(powershell_command(
        "Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } | ForEach-Object { \"== $($_.DriveLetter): ==\"; chkdsk \"$($_.DriveLetter):\" /scan }"))


def repair_wmi(ctx) -> Esito:
    return ctx.comando(["winmgmt", "/salvagerepository"])


def sfc_verify(ctx) -> Esito:
    esito = ctx.comando(["sfc", "/verifyonly"])
    if esito.stato is Stato.AVVISO:
        esito.nota = "problems found: run Repair system files (SFC)"
    return esito


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


# ---------- disk management (iteration 6) ----------

FIXED_VOLUMES = "Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } | Sort-Object DriveLetter"
# Volumes on SSDs or on hard disks: PhysicalDisk.DeviceId is the disk number of Get-Partition.
VOLUMES_ON = ("$disks = @(Get-PhysicalDisk | Where-Object MediaType -eq '{media}' | ForEach-Object {{ [string]$_.DeviceId }}); "
              "$parts = @(Get-Partition | Where-Object {{ $_.DriveLetter -and ($disks -contains [string]$_.DiskNumber) }}); "
              "if (-not $parts) {{ 'No {label} volume found.' }}; ")

SCRIPT_DISK_HEALTH = r"""
Get-PhysicalDisk | Sort-Object { [int]$_.DeviceId } | ForEach-Object {
  $r = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
  "== Disk $($_.DeviceId): $($_.FriendlyName) ($($_.MediaType), $($_.BusType), $([math]::Round($_.Size / 1GB)) GB) =="
  "Health: $($_.HealthStatus) - status: $($_.OperationalStatus)"
  if ($r) {
    "Temperature: $($r.Temperature) C (highest $($r.TemperatureMax) C)"
    "Wear: $($r.Wear) %  - power-on hours: $($r.PowerOnHours)"
    "Read errors: $($r.ReadErrorsTotal)  - write errors: $($r.WriteErrorsTotal)"
  } else { 'Reliability counters are not available for this disk.' }
  if ($_.HealthStatus -ne 'Healthy') { $script:bad = $true }
}
if ($script:bad) { exit 1 }
"""

SCRIPT_SMART = r"""
$p = @(Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue)
if (-not $p) { 'SMART failure prediction is not exposed by this controller (NVMe or RAID): use the disk health report.'; exit 0 }
$p | ForEach-Object { "$($_.InstanceName): " + $(if ($_.PredictFailure) { 'FAILURE PREDICTED' } else { 'OK' }) }
if ($p | Where-Object PredictFailure) { exit 1 }
"""

SCRIPT_VOLUMES = r"""
Get-Volume | Where-Object { ($_.DriveType -eq 'Fixed' -or $_.DriveType -eq 'Removable') -and $_.Size } | Sort-Object DriveLetter | ForEach-Object {
  '{0}  {1,-18} {2,-6} {3,9:N1} GB free of {4,9:N1} GB  ({5:N0} %)  {6}' -f $(if ($_.DriveLetter) { "$($_.DriveLetter):" } else { '--' }),
    $_.FileSystemLabel, $_.FileSystem, ($_.SizeRemaining / 1GB), ($_.Size / 1GB), (100 * $_.SizeRemaining / $_.Size), $_.HealthStatus
}
"""

SCRIPT_PARTITIONS = r"""
Get-Disk | Sort-Object Number | ForEach-Object {
  "== Disk $($_.Number): $($_.FriendlyName) - $($_.PartitionStyle) - $($_.BusType) - $([math]::Round($_.Size / 1GB)) GB - $($_.OperationalStatus) =="
  Get-Partition -DiskNumber $_.Number -ErrorAction SilentlyContinue | ForEach-Object {
    '  #{0}  {1,-12} {2,9:N1} GB  {3}' -f $_.PartitionNumber, $(if ($_.DriveLetter) { "$($_.DriveLetter):" } else { "$($_.Type)" }), ($_.Size / 1GB),
      $(if ($_.IsBoot) { 'boot' } elseif ($_.IsSystem) { 'system (EFI)' } else { '' })
  }
}
"""

SCRIPT_DISKS_ONLINE = r"""
$d = @(Get-Disk | Where-Object { $_.IsOffline -or $_.IsReadOnly })
if (-not $d) { 'All disks are online and writable.' }
foreach ($x in $d) {
  if ($x.IsOffline) { Set-Disk -Number $x.Number -IsOffline $false; "Disk $($x.Number) ($($x.FriendlyName)) is online" }
  if ($x.IsReadOnly) { Set-Disk -Number $x.Number -IsReadOnly $false; "Disk $($x.Number) ($($x.FriendlyName)) is writable" }
}
"""

SCRIPT_RESCAN = "Update-HostStorageCache; 'Disks rescanned:'; Get-Disk | Sort-Object Number | ForEach-Object { \"  Disk $($_.Number): $($_.FriendlyName) - $($_.OperationalStatus)\" }"


def _note_on_warning(esito: Esito, nota: str) -> Esito:
    if esito.stato is Stato.AVVISO:
        esito.nota = nota
    return esito


def disk_health_report(ctx) -> Esito:
    return _note_on_warning(ctx.comando(powershell_command(SCRIPT_DISK_HEALTH)), "a disk is not healthy: back up its data")


def smart_prediction(ctx) -> Esito:
    return _note_on_warning(ctx.comando(powershell_command(SCRIPT_SMART)), "a disk predicts a failure: back up its data now")


def volume_report(ctx) -> Esito:
    return ctx.comando(powershell_command(SCRIPT_VOLUMES))


def partition_report(ctx) -> Esito:
    return ctx.comando(powershell_command(SCRIPT_PARTITIONS))


def dirty_check(ctx) -> Esito:
    return ctx.comando(powershell_command(f"{FIXED_VOLUMES} | ForEach-Object {{ fsutil dirty query \"$($_.DriveLetter):\" }}"))


def disk_speed(ctx) -> Esito:
    return ctx.comando(["winsat", "disk", "-drive", "c"])


def shadow_storage_report(ctx) -> Esito:
    return ctx.comando(["vssadmin", "list", "shadowstorage"])


def folder_size(root: str) -> int:
    return sum(peso for _, peso in _files(root, None))


def top_folders(ctx, root: str = "C:\\", limit: int = 15) -> Esito:
    """Read-only: the largest top-level folders of a drive (links and junctions are not followed)."""
    ctx.scrivi(f"Measuring the folders of {root} (a few minutes on large drives)...")
    pesi = []
    try:
        voci = list(os.scandir(root))
    except OSError as errore:
        return Esito(Stato.ERRORE, str(errore))
    for voce in voci:
        try:
            info = voce.stat(follow_symlinks=False)
        except OSError:
            continue
        if voce.is_symlink() or getattr(info, "st_file_attributes", 0) & REPARSE_POINT or not stat.S_ISDIR(info.st_mode):
            continue
        pesi.append((folder_size(voce.path), voce.name))
    pesi.sort(reverse=True)
    for peso, nome in pesi[:limit]:
        ctx.scrivi(f"  {op.dimensione(peso):>10}  {nome}")
    if not pesi:
        return Esito(Stato.OK, "no folders")
    return Esito(Stato.OK, f"largest: {pesi[0][1]} ({op.dimensione(pesi[0][0])})")


def rescan_disks(ctx) -> Esito:
    return ctx.comando(powershell_command(SCRIPT_RESCAN))


def trim_ssd_volumes(ctx) -> Esito:
    return ctx.comando(powershell_command(VOLUMES_ON.format(media="SSD", label="SSD") +
                                          "$parts | ForEach-Object { \"== $($_.DriveLetter): ==\"; Optimize-Volume -DriveLetter $_.DriveLetter -ReTrim -Verbose 4>&1 }"))


def defrag_hdd_volumes(ctx) -> Esito:
    return ctx.comando(powershell_command(VOLUMES_ON.format(media="HDD", label="hard disk") +
                                          "$parts | ForEach-Object { \"== $($_.DriveLetter): ==\"; Optimize-Volume -DriveLetter $_.DriveLetter -Defrag -Verbose 4>&1 }"))


def disks_online(ctx) -> Esito:
    return ctx.comando(powershell_command(SCRIPT_DISKS_ONLINE))


def limit_shadow_storage(ctx) -> Esito:
    esito = ctx.comando(["vssadmin", "resize", "shadowstorage", "/for=C:", "/on=C:", "/maxsize=8%"])
    if esito.stato is Stato.OK:
        esito.nota = "restore points limited to 8% of C:"
    return esito


def set_reserved_storage(ctx, enabled: bool) -> Esito:
    return ctx.comando(["DISM", "/Online", "/Set-ReservedStorageState", "/State:" + ("Enabled" if enabled else "Disabled")])


def reduce_hiberfile(ctx) -> Esito:
    return ctx.comando(["powercfg", "/hibernate", "/type", "reduced"])


def pagefile_automatic(ctx) -> Esito:
    esito = ctx.comando(powershell_command(
        "$cs = Get-CimInstance Win32_ComputerSystem; Set-CimInstance -InputObject $cs -Property @{ AutomaticManagedPagefile = $true }; "
        "'The page file is managed by Windows.'"))
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
        esito.nota = "page file managed by Windows; restart to apply"
    return esito


def last_access_off(ctx) -> Esito:
    return ctx.comando(["fsutil", "behavior", "set", "disablelastaccess", "1"])


def disk_cleanup_tool(ctx) -> Esito:
    return ctx.comando(["cleanmgr", "/verylowdisk", "/d", "C"])


def delete_windows_old(ctx) -> Esito:
    """rd /s /q removes junctions without following them (PowerShell 5 Remove-Item may)."""
    percorso = os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "Windows.old")
    if not os.path.isdir(percorso):
        return Esito(Stato.OK, "there is no Windows.old folder")
    for comando in (["icacls", percorso, "/setowner", "*S-1-5-32-544", "/T", "/C", "/L", "/Q"],
                    ["icacls", percorso, "/grant", "*S-1-5-32-544:F", "/T", "/C", "/L", "/Q"]):
        esito = ctx.comando(comando, validi=(0, 1, 2, 5))
        if esito.stato is Stato.ANTEPRIMA:
            break
    esito = ctx.comando(["cmd.exe", "/d", "/c", "rd", "/s", "/q", percorso])
    if esito.stato is Stato.ANTEPRIMA:
        return esito
    if os.path.isdir(percorso):
        return Esito(Stato.AVVISO, "some files in Windows.old could not be deleted")
    return Esito(Stato.OK, "Windows.old deleted")


# ---------- toolbox (iteration 7) ----------

def report(ctx, script: str, nota_avviso: str = "") -> Esito:
    """Read-only PowerShell report; a non-zero exit is a warning with a clear note."""
    esito = ctx.comando(powershell_command(script))
    return _note_on_warning(esito, nota_avviso) if nota_avviso else esito


def measured(ctx, titolo: str, cartelle: Sequence[str]) -> Esito:
    """Read-only: size of each folder (works in preview too)."""
    totale = 0
    for cartella in expand(cartelle):
        peso = folder_size(cartella)
        totale += peso
        ctx.scrivi(f"  {op.dimensione(peso):>10}  {cartella}")
    return Esito(Stato.OK, f"{titolo}: {op.dimensione(totale)}")


# cleanup
SHADER_CACHES = [r"%LOCALAPPDATA%\D3DSCache", r"%LOCALAPPDATA%\NVIDIA\DXCache", r"%LOCALAPPDATA%\NVIDIA\GLCache",
                 r"%LOCALAPPDATA%\AMD\DxCache", r"%LOCALAPPDATA%\AMD\DxcCache", r"%LOCALAPPDATA%\Intel\ShaderCache"]
TEAMS_CACHES = [rf"%APPDATA%\Microsoft\Teams\{c}" for c in ("Cache", "Code Cache", "GPUCache", "blob_storage", "databases", "IndexedDB", "Local Storage", "tmp")] + \
               [r"%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams"]
USER_CRASH_DUMPS = [r"%LOCALAPPDATA%\CrashDumps"]
OFFICE_CACHES = [r"%LOCALAPPDATA%\Microsoft\Office\16.0\OfficeFileCache", r"%LOCALAPPDATA%\Microsoft\Office\16.0\Wef"]
DEV_CACHES = [r"%LOCALAPPDATA%\pip\Cache", r"%LOCALAPPDATA%\npm-cache", r"%APPDATA%\npm-cache", r"%LOCALAPPDATA%\Yarn\Cache",
              r"%LOCALAPPDATA%\NuGet\v3-cache", r"%LOCALAPPDATA%\go-build"]
TEMP_FOLDERS = [r"%TEMP%", r"%SystemRoot%\Temp", r"%SystemRoot%\SoftwareDistribution\Download"]


def clean_folders(ctx, descrizione: str, cartelle: Sequence[str]) -> Esito:
    return _wipe_action(ctx, descrizione, [(p, None) for p in expand(cartelle)])


# integrity
SCRIPT_RELIABILITY = r"""
$r = @(Get-CimInstance Win32_ReliabilityRecords -ErrorAction SilentlyContinue | Where-Object { $_.TimeGenerated -gt (Get-Date).AddDays(-30) } |
  Sort-Object TimeGenerated -Descending | Select-Object -First 25)
if (-not $r) { 'No reliability events in the last 30 days.'; exit 0 }
$r | ForEach-Object { '{0:yyyy-MM-dd HH:mm}  {1,-28} {2}' -f $_.TimeGenerated, $_.SourceName, (($_.Message -split "`n")[0]) }
"""

SCRIPT_BSOD = r"""
$e = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 1001; ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting' } -MaxEvents 10 -ErrorAction SilentlyContinue)
$d = @(Get-ChildItem "$env:SystemRoot\Minidump" -Filter *.dmp -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
"Blue screens recorded: $($e.Count) - minidumps on disk: $($d.Count)"
$e | ForEach-Object { '{0:yyyy-MM-dd HH:mm}  {1}' -f $_.TimeCreated, (($_.Message -split "`n")[0]) }
$d | Select-Object -First 10 | ForEach-Object { '  {0}  {1:yyyy-MM-dd HH:mm}  {2:N0} KB' -f $_.Name, $_.LastWriteTime, ($_.Length / 1KB) }
if ($e.Count) { exit 1 }
"""

SCRIPT_UNSIGNED = r"""
$u = @(driverquery /si /fo csv | ConvertFrom-Csv | Where-Object { $_.IsSigned -eq 'FALSE' })
if (-not $u) { 'Every loaded driver is signed.'; exit 0 }
$u | ForEach-Object { "Unsigned: $($_.DeviceName) ($($_.InfName))" }
exit 1
"""


# services
SCRIPT_STOPPED_AUTO = r"""
$s = @(Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.State -ne 'Running' -and $_.Name -notmatch '^(sppsvc|RemoteRegistry|gupdate|edgeupdate|MapsBroker|wuauserv|TrustedInstaller|BITS|gpsvc)$' })
if (-not $s) { 'Every automatic service is running.'; exit 0 }
$s | Sort-Object Name | ForEach-Object { '{0,-32} {1,-10} {2}' -f $_.Name, $_.State, $_.DisplayName }
exit 1
"""


# performance
SCRIPT_TOP_PROCESSES = r"""
'== Memory (working set) =='
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 | ForEach-Object { '{0,10:N0} MB  {1}' -f ($_.WorkingSet64 / 1MB), $_.ProcessName }
'== CPU time since start =='
Get-Process | Where-Object CPU | Sort-Object CPU -Descending | Select-Object -First 12 | ForEach-Object { '{0,10:N0} s   {1}' -f $_.CPU, $_.ProcessName }
"""
USB_SUSPEND = ("2a737441-1930-4402-8d77-b2bebba308a3", "48e6b7a6-50f5-4782-a5d4-53bb8f07e226")


def battery_report(ctx) -> Esito:
    percorso = os.path.join(os.path.expandvars("%PUBLIC%"), "Documents", "wmm-battery-report.html")
    esito = ctx.comando(["powercfg", "/batteryreport", "/output", percorso])
    if esito.stato is Stato.OK:
        esito.nota = f"report saved to {percorso}"
    elif esito.stato is not Stato.ANTEPRIMA:
        esito.nota = "no battery found (desktop PC) or the report failed"
    return esito


def usb_suspend_off(ctx) -> Esito:
    sottogruppo, impostazione = USB_SUSPEND
    if not ctx.anteprima:
        undo.before_power(sottogruppo, impostazione)
    return op.comandi_in_serie(ctx, (["powercfg", "/setacvalueindex", "SCHEME_CURRENT", sottogruppo, impostazione, "0"],
                                     ["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", sottogruppo, impostazione, "0"],
                                     ["powercfg", "/setactive", "SCHEME_CURRENT"]))


def menu_delay(ctx) -> Esito:
    return _registry_action(ctx, "Registry HKCU\\Control Panel\\Desktop\\MenuShowDelay = 100",
                            lambda: write_string("HKEY_CURRENT_USER", r"Control Panel\Desktop", "MenuShowDelay", "100"),
                            "menus open faster; applies at the next sign-in")


def startup_delay_off(ctx) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize"
    return _registry_action(ctx, f"Registry HKCU\\{chiave}\\StartupDelayInMSec = 0",
                            lambda: write_dword("HKEY_CURRENT_USER", chiave, "StartupDelayInMSec", 0), "startup programs no longer wait after sign-in")


def game_mode_on(ctx) -> Esito:
    chiave = r"Software\Microsoft\GameBar"
    return _registry_action(ctx, f"Registry HKCU\\{chiave}\\AutoGameModeEnabled = 1",
                            lambda: write_dword("HKEY_CURRENT_USER", chiave, "AutoGameModeEnabled", 1), "Game Mode on")


# storage
SYSTEM_FILES = ("pagefile.sys", "swapfile.sys", "hiberfil.sys")


def system_files_report(ctx) -> Esito:
    radice = os.environ.get("SystemDrive", "C:") + "\\"
    totale = 0
    for nome in SYSTEM_FILES:
        try:
            peso = os.stat(os.path.join(radice, nome)).st_size
        except OSError:
            ctx.scrivi(f"  {'absent':>10}  {nome}")
            continue
        totale += peso
        ctx.scrivi(f"  {op.dimensione(peso):>10}  {nome}")
    return Esito(Stato.OK, f"page, swap and hibernation files: {op.dimensione(totale)}")


def downloads_report(ctx, giorni: int = 90, cartella: Optional[str] = None) -> Esito:
    """Read-only: size of Downloads and the largest files nobody touched for `giorni` days."""
    import time
    cartella = cartella or os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(cartella):
        return Esito(Stato.OK, "there is no Downloads folder")
    limite = time.time() - giorni * 86400
    tutti = list(_files(cartella, None))
    vecchi = list(_files(cartella, None, limite))
    for percorso, peso in sorted(vecchi, key=lambda x: -x[1])[:20]:
        ctx.scrivi(f"  {op.dimensione(peso):>10}  {os.path.relpath(percorso, cartella)}")
    return Esito(Stato.OK, f"{op.dimensione(sum(p for _, p in tutti))} in Downloads, "
                           f"{op.dimensione(sum(p for _, p in vecchi))} older than {giorni} days")


def recycle_report(ctx) -> Esito:
    return report(ctx, "$b = (New-Object -ComObject Shell.Application).Namespace(10); $n = @($b.Items()).Count; "
                       "$t = ($b.Items() | Measure-Object -Property Size -Sum).Sum; '{0} items, {1:N1} MB in the Recycle Bin' -f $n, ($t / 1MB)")


# network
SCRIPT_CONNECTIVITY = r"""
$bad = 0
foreach ($t in @(@('1.1.1.1', 53), @('8.8.8.8', 53), @('www.microsoft.com', 443), @('login.microsoftonline.com', 443))) {
  $r = Test-NetConnection -ComputerName $t[0] -Port $t[1] -WarningAction SilentlyContinue
  if (-not $r.TcpTestSucceeded) { $bad++ }
  '{0,-28} port {1,-4} {2}' -f $t[0], $t[1], $(if ($r.TcpTestSucceeded) { 'OK' } else { 'FAILED' })
}
if ($bad) { exit 1 }
"""

SCRIPT_OPEN_PORTS = r"""
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Sort-Object LocalPort -Unique | ForEach-Object {
  $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  '{0,-6} {1,-16} {2}' -f $_.LocalPort, $_.LocalAddress, $(if ($p) { $p.ProcessName } else { "pid $($_.OwningProcess)" })
}
"""


def wlan_report(ctx) -> Esito:
    esito = ctx.comando(["netsh", "wlan", "show", "wlanreport"])
    if esito.stato is Stato.OK:
        esito.nota = r"report saved to C:\ProgramData\Microsoft\Windows\WlanReport\wlan-report-latest.html"
    return esito


# startup
SCRIPT_SCHEDULED_TASKS = r"""
Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and $_.TaskPath -notlike '\Microsoft\*' } | Sort-Object TaskName | ForEach-Object {
  '{0,-44} {1,-8} {2}' -f $_.TaskName, $_.State, (($_.Actions | Select-Object -First 1).Execute)
}
"""

SCRIPT_BOOT_TIME = r"""
$e = @(Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-Diagnostics-Performance/Operational'; Id = 100 } -MaxEvents 10 -ErrorAction SilentlyContinue)
if (-not $e) { 'Boot performance events are not available (run as administrator).'; exit 0 }
$e | ForEach-Object { $x = [xml]$_.ToXml(); $ms = ($x.Event.EventData.Data | Where-Object Name -eq 'BootTime').'#text'
  '{0:yyyy-MM-dd HH:mm}  boot {1,6:N1} s' -f $_.TimeCreated, ([double]$ms / 1000) }
"""

SCRIPT_THIRD_PARTY_SERVICES = r"""
Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName -and $_.PathName -notmatch '\\Windows\\' } |
  Sort-Object DisplayName | ForEach-Object { '{0,-40} {1,-8} {2}' -f $_.DisplayName, $_.State, $_.PathName }
"""

SCRIPT_INSTALLED_APPS = r"""
$k = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
     'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
$a = @(Get-ItemProperty $k -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -and -not $_.SystemComponent } | Sort-Object DisplayName -Unique)
"$($a.Count) applications installed"
$a | ForEach-Object { '{0,-56} {1,-18} {2}' -f $_.DisplayName, $_.DisplayVersion, $_.InstallDate }
"""


def edge_boost_off(ctx) -> Esito:
    chiave = r"SOFTWARE\Policies\Microsoft\Edge"

    def scrivi():
        write_dword("HKEY_LOCAL_MACHINE", chiave, "StartupBoostEnabled", 0)
        write_dword("HKEY_LOCAL_MACHINE", chiave, "BackgroundModeEnabled", 0)
    return _registry_action(ctx, f"Registry HKLM\\{chiave}: StartupBoostEnabled = 0, BackgroundModeEnabled = 0", scrivi,
                            "Edge no longer preloads at sign-in or runs after it is closed")


# security
SCRIPT_TPM = r"""
$t = Get-Tpm -ErrorAction SilentlyContinue
if (-not $t) { 'TPM state is not readable (run as administrator).'; exit 0 }
"Present: $($t.TpmPresent)  Ready: $($t.TpmReady)  Enabled: $($t.TpmEnabled)  Activated: $($t.TpmActivated)"
$v = (Get-CimInstance -Namespace root\cimv2\security\microsofttpm -ClassName Win32_Tpm -ErrorAction SilentlyContinue).SpecVersion
if ($v) { "Specification: $v" }
if (-not $t.TpmPresent -or -not $t.TpmReady) { exit 1 }
"""

SCRIPT_SECURE_BOOT = r"""
try { $s = Confirm-SecureBootUEFI -ErrorAction Stop } catch { 'Secure Boot is not supported (legacy BIOS) or not readable.'; exit 1 }
if ($s) { 'Secure Boot is on.' } else { 'Secure Boot is OFF.'; exit 1 }
"""

SCRIPT_LOCAL_ADMINS = r"""
$m = @(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction SilentlyContinue)
"$($m.Count) member(s) of the local Administrators group:"
$m | ForEach-Object { '  {0,-40} {1,-8} {2}' -f $_.Name, $_.ObjectClass, $_.PrincipalSource }
"""

SCRIPT_DEFENDER_STATUS = r"""
$s = Get-MpComputerStatus -ErrorAction SilentlyContinue
if (-not $s) { 'Microsoft Defender is not active (another antivirus may be installed).'; exit 1 }
"Real-time protection: $($s.RealTimeProtectionEnabled)"
"Tamper protection:    $($s.IsTamperProtected)"
"Signatures:           $($s.AntivirusSignatureVersion) ($($s.AntivirusSignatureAge) days old)"
"Engine / platform:    $($s.AMEngineVersion) / $($s.AMProductVersion)"
"Last quick scan:      $($s.QuickScanEndTime)"
"Last full scan:       $($s.FullScanEndTime)"
if (-not $s.RealTimeProtectionEnabled -or $s.AntivirusSignatureAge -gt 7) { exit 1 }
"""


# updates
SCRIPT_UPDATE_HISTORY = r"""
Get-HotFix | Sort-Object { $_.InstalledOn -as [datetime] } -Descending | Select-Object -First 20 | ForEach-Object {
  '{0,-11} {1,-16} {2}' -f $_.HotFixID, $_.Description, $(if ($_.InstalledOn) { ([datetime]$_.InstalledOn).ToString('yyyy-MM-dd') } else { '' })
}
"""

SCRIPT_PROBLEM_DEVICES = r"""
$d = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.Status -ne 'OK' -and $_.Status -ne 'Unknown' })
if (-not $d) { 'Every device works.'; exit 0 }
$d | ForEach-Object { '{0,-8} {1,-14} {2}' -f $_.Status, $_.Class, $_.FriendlyName }
exit 1
"""

REBOOT_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending", "Windows servicing"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired", "Windows Update"),
)


def key_exists(root: str, key: str) -> bool:
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(getattr(winreg, root), key))
        return True
    except OSError:
        return False


def pending_file_renames() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager") as handle:
            return bool(winreg.QueryValueEx(handle, "PendingFileRenameOperations")[0])
    except OSError:
        return False


def pending_reboot(ctx) -> Esito:
    """Read-only: the places where Windows records a restart it is waiting for."""
    motivi = [nome for radice, chiave, nome in REBOOT_KEYS if key_exists(radice, chiave)]
    if pending_file_renames():
        motivi.append("file rename operations")
    for motivo in motivi:
        ctx.scrivi(f"  Pending: {motivo}")
    if motivi:
        return Esito(Stato.AVVISO, "a restart is pending: " + ", ".join(motivi))
    return Esito(Stato.OK, "no restart pending")


# ---------- performance pack (iteration 8) ----------

HKLM, HKCU = "HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER"
MULTIMEDIA = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
CONTENT_DELIVERY = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
PREFETCH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters"


def power_settings(ctx, impostazioni: Sequence[Tuple[str, str, int]], dc: bool = True) -> Esito:
    """Sets power plan values on the active plan (AC, and battery unless dc=False), then reapplies the plan."""
    comandi = []
    for sottogruppo, impostazione, valore in impostazioni:
        if not ctx.anteprima:
            undo.before_power(sottogruppo, impostazione)  # the precise undo puts back the AC and DC values of the plan
        comandi.append(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", sottogruppo, impostazione, str(valore)])
        if dc:
            comandi.append(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", sottogruppo, impostazione, str(valore)])
    comandi.append(["powercfg", "/setactive", "SCHEME_CURRENT"])
    return op.comandi_in_serie(ctx, comandi)


def registry_values(ctx, scritture: Sequence[Tuple[str, str, str, object]], nota: str) -> Esito:
    """Writes several registry values as one change; integers are DWORDs, text is REG_SZ."""
    descrizione = "; ".join(f"{'HKLM' if r == HKLM else 'HKCU'}\\{k}\\{n} = {v}" for r, k, n, v in scritture)
    if not ctx.modifica("Registry " + descrizione):
        return Esito(Stato.ANTEPRIMA)
    for radice, chiave, nome, valore in scritture:
        if isinstance(valore, int):
            write_dword(radice, chiave, nome, valore)
        else:
            write_string(radice, chiave, nome, str(valore))
    return Esito(Stato.OK, nota)


def with_restart(ctx, esito: Esito) -> Esito:
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
    return esito


SCRIPT_CPU = r"""
Get-CimInstance Win32_Processor | ForEach-Object {
  "$($_.Name.Trim())"
  "Cores: $($_.NumberOfCores) - logical processors: $($_.NumberOfLogicalProcessors)"
  "Base clock: $($_.MaxClockSpeed) MHz - current: $($_.CurrentClockSpeed) MHz - load: $($_.LoadPercentage) %"
  "L2: $($_.L2CacheSize) KB - L3: $($_.L3CacheSize) KB - virtualization in firmware: $($_.VirtualizationFirmwareEnabled)"
}
$c = Get-Counter '\Processor(*)\% Processor Time' -SampleInterval 1 -MaxSamples 2 -ErrorAction SilentlyContinue
if ($c) { '== Load per logical processor =='; $last = $c.CounterSamples | Select-Object -Last 1
  $c.CounterSamples | Where-Object Timestamp -eq $last.Timestamp | Sort-Object InstanceName | ForEach-Object { '{0,-8} {1,6:N1} %' -f $_.InstanceName, $_.CookedValue } }
"""

SCRIPT_MEMORY = r"""
$os = Get-CimInstance Win32_OperatingSystem
'Installed: {0:N1} GB - free: {1:N1} GB - committed: {2:N1} of {3:N1} GB' -f ($os.TotalVisibleMemorySize / 1MB), ($os.FreePhysicalMemory / 1MB),
  (($os.TotalVirtualMemorySize - $os.FreeVirtualMemory) / 1MB), ($os.TotalVirtualMemorySize / 1MB)
'== Modules =='
Get-CimInstance Win32_PhysicalMemory | ForEach-Object { '{0,-14} {1,6:N0} GB  {2,5} MT/s (configured {3})  {4} {5}' -f $_.DeviceLocator, ($_.Capacity / 1GB),
  $_.Speed, $_.ConfiguredClockSpeed, $_.Manufacturer, "$($_.PartNumber)".Trim() }
$a = Get-CimInstance Win32_PhysicalMemoryArray
"Slots: $(@(Get-CimInstance Win32_PhysicalMemory).Count) used of $($a.MemoryDevices) - maximum $([math]::Round($a.MaxCapacityEx / 1MB)) GB"
"""

SCRIPT_GPU = r"""
Get-CimInstance Win32_VideoController | ForEach-Object {
  "== $($_.Name) =="
  "Driver: $($_.DriverVersion) ($(if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') }))"
  "Resolution: $($_.CurrentHorizontalResolution) x $($_.CurrentVerticalResolution) at $($_.CurrentRefreshRate) Hz"
  "Status: $($_.Status)"
}
$hags = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -ErrorAction SilentlyContinue).HwSchMode
"Hardware-accelerated GPU scheduling: $(switch ($hags) { 2 { 'on' } 1 { 'off' } default { 'Windows default' } })"
"""

SCRIPT_THERMAL = r"""
$t = @(Get-CimInstance -Namespace root\wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue)
if (-not $t) { 'The firmware does not expose thermal zones (common on desktops): use the disk health report for disk temperatures.'; exit 0 }
$hot = $false
$t | ForEach-Object { $c = [math]::Round($_.CurrentTemperature / 10 - 273.15, 1); if ($c -ge 90) { $hot = $true }; '{0,-40} {1,6} C' -f $_.InstanceName, $c }
if ($hot) { exit 1 }
"""

SCRIPT_DISK_LATENCY = r"""
$s = (Get-Counter '\PhysicalDisk(*)\Avg. Disk sec/Read','\PhysicalDisk(*)\Avg. Disk sec/Write','\PhysicalDisk(*)\Current Disk Queue Length','\PhysicalDisk(*)\% Idle Time' -SampleInterval 2 -MaxSamples 3 -ErrorAction SilentlyContinue).CounterSamples
$slow = $false
$s | Where-Object InstanceName -ne '_total' | Group-Object InstanceName | ForEach-Object {
  $v = @{}; $_.Group | Group-Object { ($_.Path -split '\\')[-1] } | ForEach-Object { $v[$_.Name] = ($_.Group | Measure-Object CookedValue -Average).Average }
  $r = 1000 * $v['avg. disk sec/read']; $w = 1000 * $v['avg. disk sec/write']; if ($r -gt 50 -or $w -gt 50) { $slow = $true }
  'Disk {0,-10} read {1,6:N1} ms  write {2,6:N1} ms  queue {3,4:N1}  busy {4,5:N1} %' -f $_.Name, $r, $w, $v['current disk queue length'], (100 - $v['% idle time'])
}
if ($slow) { exit 1 }
"""

SCRIPT_HANDLES = r"""
'== Most handles (possible leaks) =='
Get-Process | Sort-Object HandleCount -Descending | Select-Object -First 12 | ForEach-Object { '{0,8:N0} handles  {1,6:N0} threads  {2}' -f $_.HandleCount, $_.Threads.Count, $_.ProcessName }
'== Most private memory =='
Get-Process | Sort-Object PrivateMemorySize64 -Descending | Select-Object -First 12 | ForEach-Object { '{0,8:N0} MB  {1}' -f ($_.PrivateMemorySize64 / 1MB), $_.ProcessName }
"""

SCRIPT_WINSAT = r"""
$w = Get-CimInstance Win32_WinSAT -ErrorAction SilentlyContinue
if (-not $w -or $w.WinSATAssessmentState -ne 1) { 'No valid assessment: run Measure the speed of C: first, or winsat formal.'; exit 0 }
"Processor:  $($w.CPUScore)"; "Memory:     $($w.MemoryScore)"; "Graphics:   $($w.GraphicsScore)"; "Gaming:     $($w.D3DScore)"; "Disk:       $($w.DiskScore)"
"Lowest (base) score: $($w.WinSPRLevel)"
"""

SCRIPT_PAGEFILE = r"""
$u = @(Get-CimInstance Win32_PageFileUsage)
"Managed by Windows: $((Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile)"
if (-not $u) { 'No page file in use.' }
$u | ForEach-Object { '{0}  allocated {1:N0} MB  in use {2:N0} MB  peak {3:N0} MB' -f $_.Name, $_.AllocatedBaseSize, $_.CurrentUsage, $_.PeakUsage }
"""

SCRIPT_NIC_POWER = r"""
Get-NetAdapter -Physical | ForEach-Object {
  $p = Get-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue
  '{0,-28} {1,-6} {2,-12} turn off to save power: {3}' -f $_.Name, $_.Status, $_.LinkSpeed, $(if ($p) { $p.AllowComputerToTurnOffDevice } else { 'n/a' })
}
"""

SCRIPT_NIC_POWER_OFF = r"""
$n = 0
Get-NetAdapter -Physical | ForEach-Object {
  $p = Get-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue
  if ($p -and "$($p.AllowComputerToTurnOffDevice)" -ne 'Disabled') { $p.AllowComputerToTurnOffDevice = 'Disabled'; $p | Set-NetAdapterPowerManagement; "$($_.Name): power saving off"; $n++ }
}
"$n adapter(s) changed."
"""


def power_plans_report(ctx) -> Esito:
    return op.comandi_in_serie(ctx, (["powercfg", "/list"], ["powercfg", "/query", "SCHEME_CURRENT", "SUB_PROCESSOR"]))


def ntfs_memory_usage(ctx) -> Esito:
    esito = with_restart(ctx, ctx.comando(["fsutil", "behavior", "set", "memoryusage", "2"]))
    if esito.stato is Stato.OK:
        esito.nota = "larger NTFS cache; restart to apply"
    return esito


# ---------- forty more tools (iteration 9) ----------

# cleanup
JAVA_CACHES = [r"%USERPROFILE%\AppData\LocalLow\Sun\Java\Deployment\cache"]
CHAT_MUSIC_CACHES = [rf"%APPDATA%\{app}\{c}" for app in ("discord", "Slack", "WhatsApp") for c in ("Cache", "Code Cache", "GPUCache")] + \
                    [r"%LOCALAPPDATA%\Spotify\Data", r"%LOCALAPPDATA%\Spotify\Browser\Cache"]
GAME_LAUNCHER_CACHES = [r"%LOCALAPPDATA%\EpicGamesLauncher\Saved\webcache*", r"%ProgramFiles(x86)%\Steam\appcache\httpcache",
                        r"%LOCALAPPDATA%\Steam\htmlcache", r"%LOCALAPPDATA%\Battle.net\BrowserCaches", r"%LOCALAPPDATA%\Ubisoft Game Launcher\cache"]
EDITOR_CACHES = [rf"%APPDATA%\{app}\{c}" for app in ("Code", "Cursor") for c in ("Cache", "CachedData", "CachedExtensionVSIXs", "Code Cache", "GPUCache", "logs")]

SCRIPT_FONT_CACHE = r"""
Stop-Service FontCache -Force -ErrorAction SilentlyContinue
$n = 0
Get-ChildItem "$env:WinDir\ServiceProfiles\LocalService\AppData\Local\FontCache" -Filter *.dat -ErrorAction SilentlyContinue | ForEach-Object {
  Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue; if (-not (Test-Path $_.FullName)) { $n++ } }
Remove-Item "$env:WinDir\System32\FNTCACHE.DAT" -Force -ErrorAction SilentlyContinue
Start-Service FontCache -ErrorAction SilentlyContinue
"$n font cache file(s) removed; Windows rebuilds the cache, and fonts are fully re-indexed at the next restart."
"""

# startup
SCRIPT_RUN_KEYS = r"""
$keys = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
foreach ($k in $keys) {
  $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
  "== $k =="
  $v = @(if ($p) { $p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } })
  if (-not $v) { '  (empty)' }
  $v | ForEach-Object { '  {0,-34} {1}' -f $_.Name, $_.Value }
}
"""

SCRIPT_STARTUP_FOLDERS = r"""
foreach ($f in [Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup')) {
  "== $f =="
  $i = @(Get-ChildItem $f -File -ErrorAction SilentlyContinue | Where-Object Name -ne 'desktop.ini')
  if (-not $i) { '  (empty)' }
  $i | ForEach-Object { '  {0,-40} {1:yyyy-MM-dd}' -f $_.Name, $_.LastWriteTime }
}
"""

SCRIPT_WINLOGON = r"""
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
"Shell:    $($w.Shell)"
"Userinit: $($w.Userinit)"
$bad = ($w.Shell -notmatch '^explorer\.exe$') -or ($w.Userinit -notmatch '^[a-z]:\\windows\\system32\\userinit\.exe,?$')
$u = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue
if ($u -and $u.Shell) { "Shell override for this user: $($u.Shell)"; $bad = $true }
if ($bad) { 'Non-default values: check them, they are a common place for malware to start with Windows.'; exit 1 }
'Default shell and user initialization.'
"""

SCRIPT_WMI_PERSISTENCE = r"""
$f = @(Get-CimInstance -Namespace root\subscription -ClassName __EventFilter -ErrorAction SilentlyContinue)
$c = @(Get-CimInstance -Namespace root\subscription -ClassName CommandLineEventConsumer -ErrorAction SilentlyContinue) +
     @(Get-CimInstance -Namespace root\subscription -ClassName ActiveScriptEventConsumer -ErrorAction SilentlyContinue)
"Event filters: $($f.Count) - command and script consumers: $($c.Count)"
$f | ForEach-Object { "  Filter:   $($_.Name) - $($_.Query)" }
$c | ForEach-Object { "  Consumer: $($_.Name) - $($_.CommandLineTemplate)$($_.ScriptText)" }
if ($c.Count) { 'Programs started by WMI events: legitimate for some management tools, a known malware technique otherwise.'; exit 1 }
"""

SCRIPT_IFEO = r"""
$r = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options'
$hits = @(Get-ChildItem $r -ErrorAction SilentlyContinue | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
  if ($p.Debugger) { '{0,-32} Debugger = {1}' -f $_.PSChildName, $p.Debugger } })
if (-not $hits) { 'No program is redirected to another one (no IFEO debugger).'; exit 0 }
$hits
'These programs start something else instead: check every entry.'
exit 1
"""

# updates
SCRIPT_WU_SERVICES = r"""
'wuauserv', 'bits', 'UsoSvc', 'cryptsvc', 'TrustedInstaller', 'WaaSMedicSvc' | ForEach-Object {
  $s = Get-Service $_ -ErrorAction SilentlyContinue
  if ($s) { '{0,-18} {1,-8} {2}' -f $s.Name, $s.Status, $s.StartType }
}
if (@(Get-Service wuauserv, bits, cryptsvc -ErrorAction SilentlyContinue | Where-Object StartType -eq 'Disabled').Count) { 'A service Windows Update needs is disabled.'; exit 1 }
"""

UPDATE_UX = r"HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
SCRIPT_PAUSE_STATUS = r"""
$s = Get-ItemProperty '%s' -ErrorAction SilentlyContinue
$paused = $s -and $s.PauseUpdatesExpiryTime
if ($paused) { "Updates are paused until $($s.PauseUpdatesExpiryTime)" } else { 'Updates are not paused.' }
$p = Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate', 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -ErrorAction SilentlyContinue
if ($p) { '== Update policies =='; $p | ForEach-Object { $_.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { "  $($_.Name) = $($_.Value)" } } }
if ($paused) { exit 1 }
""" % UPDATE_UX

SCRIPT_RESUME_UPDATES = r"""
$names = 'PauseUpdatesExpiryTime', 'PauseUpdatesStartTime', 'PauseFeatureUpdatesStartTime', 'PauseFeatureUpdatesEndTime',
         'PauseQualityUpdatesStartTime', 'PauseQualityUpdatesEndTime'
Remove-ItemProperty -Path '%s' -Name $names -ErrorAction SilentlyContinue
'Windows Update is no longer paused.'
""" % UPDATE_UX

SCRIPT_WINDOWS_VERSION = r"""
$v = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$os = Get-CimInstance Win32_OperatingSystem
"Edition:   $($os.Caption) ($($v.EditionID))"
"Version:   $($v.DisplayVersion)"
"Build:     $($v.CurrentBuild).$($v.UBR)"
"Installed: $(([datetime]'1970-01-01').AddSeconds($v.InstallDate).ToLocalTime().ToString('yyyy-MM-dd'))"
"Last boot: $($os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm'))"
"Architecture: $($os.OSArchitecture) - language: $($os.MUILanguages -join ', ')"
"""

# services
SCRIPT_PRINT_QUEUE = r"""
$ErrorActionPreference = 'Stop'
Stop-Service Spooler -Force
$f = @(Get-ChildItem "$env:SystemRoot\System32\spool\PRINTERS" -File -ErrorAction SilentlyContinue)
$f | Remove-Item -Force -ErrorAction SilentlyContinue
Start-Service Spooler
"$($f.Count) stuck print job file(s) removed; the print spooler is running again."
"""

SCRIPT_DISABLED_SERVICES = r"""
$s = @(Get-CimInstance Win32_Service | Where-Object StartMode -eq 'Disabled' | Sort-Object DisplayName)
"$($s.Count) disabled services"
$s | ForEach-Object { '  {0,-44} {1}' -f $_.DisplayName, $_.Name }
"""

SCRIPT_DELAYED_SERVICES = r"""
$d = @(Get-ChildItem HKLM:\SYSTEM\CurrentControlSet\Services -ErrorAction SilentlyContinue | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
  if ($p.Start -eq 2 -and $p.DelayedAutostart -eq 1) { $_.PSChildName } } | Sort-Object)
"$($d.Count) services start automatically with a delay (after sign-in, to speed up the boot)"
$d | ForEach-Object { $s = Get-Service $_ -ErrorAction SilentlyContinue; '  {0,-32} {1}' -f $_, $(if ($s) { $s.Status }) }
"""

# network
SCRIPT_DNS_CACHE = r"""
$c = @(Get-DnsClientCache -ErrorAction SilentlyContinue)
"$($c.Count) records in the DNS cache"
$c | Group-Object Entry | Sort-Object Count -Descending | Select-Object -First 40 | ForEach-Object { '  ' + $_.Name }
"""

# integrity
SCRIPT_RESTORE_POINTS = r"""
$p = @(Get-ComputerRestorePoint -ErrorAction SilentlyContinue)
if (-not $p) { 'No restore points: System Restore may be off on C:.'; exit 1 }
$p | ForEach-Object { '#{0,-5} {1}  {2}' -f $_.SequenceNumber, $_.ConvertToDateTime($_.CreationTime).ToString('yyyy-MM-dd HH:mm'), $_.Description }
"""

SCRIPT_CRASH_SETTINGS = r"""
$c = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl'
$t = @{ 0 = 'None'; 1 = 'Complete'; 2 = 'Kernel'; 3 = 'Small (minidump)'; 7 = 'Automatic' }[[int]$c.CrashDumpEnabled]
"Dump written on a blue screen: $t"
"Dump file: $($c.DumpFile)"
"Minidump folder: $($c.MinidumpDir)"
"Restart automatically: $(if ($c.AutoReboot) { 'yes' } else { 'no' })"
"Write to the system log: $(if ($c.LogEvent) { 'yes' } else { 'no' })"
"""

SCRIPT_APP_CRASHES = r"""
$e = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Id = 1000; StartTime = (Get-Date).AddDays(-30) } -ErrorAction SilentlyContinue)
"$($e.Count) application crashes in the last 30 days"
$e | ForEach-Object { $_.Properties[0].Value } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { '{0,5}  {1}' -f $_.Count, $_.Name }
if ($e.Count -gt 20) { exit 1 }
"""

# security
SCRIPT_FIREWALL_RULES = r"""
$r = @(Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True -ErrorAction SilentlyContinue | Where-Object { "$($_.Profile)" -match 'Public|Any' })
"$($r.Count) inbound allow rules are active on public networks"
$r | Sort-Object DisplayName | Select-Object -First 80 | ForEach-Object { '  {0,-60} {1}' -f $_.DisplayName, $_.Profile }
"""

SCRIPT_SHARES = r"""
$s = @(Get-SmbShare -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '^([A-Z]|ADMIN|IPC|print)\$$' })
if (-not $s) { 'No folder is shared from this PC.'; exit 0 }
$open = $false
$s | ForEach-Object {
  $a = @(Get-SmbShareAccess -Name $_.Name -ErrorAction SilentlyContinue | ForEach-Object { "$($_.AccountName): $($_.AccessRight)" })
  if ($a -match '^Everyone: Full') { $open = $true }
  '{0,-20} {1}  [{2}]' -f $_.Name, $_.Path, ($a -join ', ')
}
if ($open) { 'A share gives Everyone full control: restrict it.'; exit 1 }
"""

SCRIPT_AUTOLOGON = r"""
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ("$($w.AutoAdminLogon)" -eq '1') {
  "Automatic sign-in is ON for $($w.DefaultDomainName)\$($w.DefaultUserName)."
  if ($w.DefaultPassword) { 'Its password is stored in the registry in plain text: anyone with access to this PC can read it.' }
  exit 1
}
'Automatic sign-in is off.'
"""


def read_string(root: str, key: str, name: str) -> Optional[str]:
    import winreg
    try:
        with winreg.OpenKey(getattr(winreg, root), key) as handle:
            return str(winreg.QueryValueEx(handle, name)[0])
    except OSError:
        return None


def onedrive_autostart_off(ctx) -> Esito:
    chiave = r"Software\Microsoft\Windows\CurrentVersion\Run"
    if read_string(HKCU, chiave, "OneDrive") is None:
        return Esito(Stato.OK, "OneDrive does not start with Windows for this user")
    if not ctx.modifica(f"Delete HKCU\\{chiave}\\OneDrive"):
        return Esito(Stato.ANTEPRIMA)
    delete_value(HKCU, chiave, "OneDrive")
    return Esito(Stato.OK, "OneDrive no longer starts with Windows; turn it back on in OneDrive › Settings")


def memory_diagnostic(ctx) -> Esito:
    esito = with_restart(ctx, ctx.comando(["bcdedit", "/bootsequence", "{memdiag}"]))
    if esito.stato is Stato.OK:
        esito.nota = "the memory test runs at the next restart (10-20 minutes); the result appears after sign-in"
    return esito
