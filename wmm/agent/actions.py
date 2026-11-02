"""Catalog of the maintenance actions, grouped by area and risk."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

import wmm  # noqa: F401
import ottimizza_pc as op

from . import tools

AREAS = ("cleanup", "integrity", "services", "performance", "storage", "network", "startup", "security", "updates")
RISKS = ("safe", "moderate", "high")
AREA_TITLES = {"cleanup": "Cleanup", "integrity": "System Integrity", "services": "Services", "performance": "Performance",
               "storage": "Storage", "network": "Network", "startup": "Startup & Apps", "security": "Security", "updates": "Updates & Drivers"}


@dataclass(frozen=True)
class Action:
    id: str
    area: str
    title: str
    description: str
    risk: str
    minutes: float
    run: Callable = field(repr=False, compare=False)
    warning: str = ""

    def as_dict(self) -> dict:
        data = asdict(self)
        del data["run"]
        return data


_ACTIONS = (
    Action("cleanup.temp", "cleanup", "Temporary files and caches",
           "Removes temporary files older than 3 days, shader caches, Windows Update download cache and Delivery Optimization cache.",
           "safe", 3, tools.clean_temp),
    Action("cleanup.components", "cleanup", "Obsolete Windows components",
           "Runs DISM /StartComponentCleanup to remove superseded component versions.",
           "moderate", 10, op.pulizia_componenti,
           "Installed updates can no longer be uninstalled after the cleanup."),
    Action("cleanup.recycle_bin", "cleanup", "Empty the Recycle Bin",
           "Permanently deletes the content of the Recycle Bin for all drives.",
           "moderate", 0.5, op.svuota_cestino,
           "The content of the Recycle Bin is deleted permanently."),
    Action("cleanup.dumps", "cleanup", "Delete crash dumps",
           "Deletes MEMORY.DMP, minidumps and LiveKernelReports.",
           "moderate", 0.5, op.elimina_dump,
           "Crash dumps are needed to analyze system crashes and GPU failures."),
    Action("integrity.disk_scan", "integrity", "Online disk check (C:)",
           "Runs CHKDSK C: /scan, an online check that needs no reboot.",
           "safe", 5, op.verifica_disco),
    Action("integrity.trim", "integrity", "SSD TRIM (C:)",
           "Sends TRIM to the SSD to keep write performance stable.",
           "safe", 2, op.trim),
    Action("integrity.dism", "integrity", "Repair Windows image (DISM)",
           "Runs DISM /RestoreHealth to repair the component store.",
           "moderate", 15, op.ripara_immagine,
           "Takes up to 15 minutes and may download files from Windows Update."),
    Action("integrity.sfc", "integrity", "Repair system files (SFC)",
           "Runs SFC /scannow to verify and repair protected system files.",
           "moderate", 15, op.ripara_file,
           "Takes up to 15 minutes and replaces corrupted system files."),
    Action("integrity.wmi_verify", "integrity", "Verify the WMI repository",
           "Checks the consistency of the WMI database used by management tools and inventory.", "safe", 1, tools.wmi_verify),
    Action("integrity.reset_wu", "integrity", "Reset Windows Update components",
           "Stops the update services, renames SoftwareDistribution and catroot2, and restarts them.", "high", 2, tools.reset_windows_update,
           "Update history shown in Settings is cleared and the next update check downloads everything again."),
    Action("integrity.disk_repair", "integrity", "Disk repair at next reboot (C:)",
           "Marks C: for a full CHKDSK at the next boot.",
           "high", 0.5, op.ripara_disco,
           "The next boot will take longer while the disk is repaired."),
    Action("services.safe", "services", "Disable unnecessary services",
           "Disables telemetry, maps, retail demo, fax and other services not needed on business PCs. The original state is backed up.",
           "moderate", 1, op.servizi_sicuri,
           "Selected services are stopped and disabled. They can be restored from the backup."),
    Action("services.xbox", "services", "Disable Xbox and Game Pass services",
           "Disables Xbox Live and Gaming Services.",
           "high", 1, op.servizi_xbox,
           "Game Pass and Microsoft Store games stop working."),
    Action("services.print", "services", "Disable printing and scanning",
           "Disables the Print Spooler and Windows Image Acquisition.",
           "high", 0.5, op.servizi_stampa,
           "Printing stops working, including Microsoft Print to PDF."),
    Action("services.restore", "services", "Restore modified services",
           "Restores the start type and state saved in the backup.",
           "moderate", 1, op.ripristina_servizi,
           "Every service changed by this suite returns to its original configuration."),
    # ---------- performance ----------
    Action("performance.power_high", "performance", "High performance power plan",
           "Activates the High performance power plan: the CPU stays at full clock.", "moderate", 0.2,
           lambda ctx: tools.set_power_plan(ctx, "high"), "Higher power consumption; on laptops the battery drains faster."),
    Action("performance.power_balanced", "performance", "Balanced power plan",
           "Activates the Balanced power plan recommended by Microsoft.", "moderate", 0.2,
           lambda ctx: tools.set_power_plan(ctx, "balanced"), "The CPU slows down when idle."),
    Action("performance.visual_best", "performance", "Visual effects: best performance",
           "Turns off animations, shadows and transparency for the current user.", "moderate", 0.2,
           lambda ctx: tools.set_visual_effects(ctx, True), "Windows looks plainer. Applies at the next sign-in."),
    Action("performance.visual_default", "performance", "Visual effects: Windows default",
           "Lets Windows choose the visual effects again.", "moderate", 0.2,
           lambda ctx: tools.set_visual_effects(ctx, False), "Applies at the next sign-in."),
    Action("performance.fast_startup_off", "performance", "Turn off Fast Startup",
           "Makes every shutdown a full shutdown, so drivers and updates start clean.", "moderate", 0.2,
           lambda ctx: op.imposta_avvio_rapido(ctx, False), "Cold boot takes a few seconds longer."),
    Action("performance.fast_startup_on", "performance", "Turn on Fast Startup",
           "Restores the Windows default hybrid shutdown.", "moderate", 0.2,
           lambda ctx: op.imposta_avvio_rapido(ctx, True), "Shutdown keeps the kernel session in hibernation."),
    Action("performance.game_dvr_off", "performance", "Turn off background game recording",
           "Disables Game DVR and background capture.", "moderate", 0.2,
           lambda ctx: op.imposta_game_dvr(ctx, False), "Xbox Game Bar can no longer record clips."),
    Action("performance.game_dvr_on", "performance", "Turn on background game recording",
           "Re-enables Game DVR and background capture.", "moderate", 0.2,
           lambda ctx: op.imposta_game_dvr(ctx, True), "Background recording uses GPU and disk."),
    Action("performance.free_memory", "performance", "Free standby memory",
           "Empties the standby list of cached file pages, like RAMMap. Useful before heavy workloads.", "safe", 0.2, tools.free_standby_memory),
    Action("performance.restart_explorer", "performance", "Restart Windows Explorer",
           "Restarts the taskbar, Start menu and desktop when they hang or misbehave.", "moderate", 0.2, tools.restart_explorer,
           "Open File Explorer windows close; unsaved work in other programs is not affected."),
    # ---------- storage ----------
    Action("storage.delivery_optimization", "storage", "Clear Delivery Optimization cache",
           "Deletes update files Windows keeps to share with other PCs.", "safe", 0.5, tools.clean_delivery_optimization),
    Action("storage.optimize_all", "storage", "Optimize all drives",
           "Runs TRIM on SSDs and defragmentation on hard disks for every volume.", "safe", 5, tools.optimize_volumes),
    Action("storage.browser_cache", "storage", "Clear browser caches",
           "Deletes the cache of Edge, Chrome, Brave and Firefox. History, passwords and sign-ins are kept.", "moderate", 1,
           tools.clean_browser_caches, "Close the browsers first; files in use are skipped and pages load slower once."),
    Action("storage.wer", "storage", "Delete error reports",
           "Deletes queued and archived Windows Error Reporting files.", "safe", 0.5, tools.clean_error_reports),
    Action("storage.thumbnails", "storage", "Reset the thumbnail cache",
           "Deletes the Explorer thumbnail cache; Windows rebuilds it when needed.", "safe", 0.5, tools.clean_thumbnails),
    Action("storage.storage_sense", "storage", "Turn on Storage Sense",
           "Lets Windows clean temporary files and the Recycle Bin automatically.", "moderate", 0.2,
           tools.enable_storage_sense, "Windows may delete Recycle Bin items older than its retention setting."),
    # ---------- network ----------
    Action("network.flush_dns", "network", "Flush DNS and ARP caches",
           "Clears cached name lookups and the ARP table.", "safe", 0.2, tools.flush_network_caches),
    Action("network.optimize", "network", "Optimize TCP settings",
           "Flushes caches and restores TCP auto-tuning and RSS to the recommended defaults.", "moderate", 0.5,
           op.ottimizza_rete, "Custom TCP tuning made by other tools is replaced."),
    Action("network.dns_cloudflare", "network", "Use Cloudflare DNS",
           "Sets 1.1.1.1 and 1.0.0.1 on the connected adapters.", "moderate", 0.2,
           lambda ctx: op.imposta_dns(ctx, ("1.1.1.1", "1.0.0.1")), "Company DNS servers are replaced: internal names may stop resolving."),
    Action("network.dns_google", "network", "Use Google DNS",
           "Sets 8.8.8.8 and 8.8.4.4 on the connected adapters.", "moderate", 0.2,
           lambda ctx: op.imposta_dns(ctx, ("8.8.8.8", "8.8.4.4")), "Company DNS servers are replaced: internal names may stop resolving."),
    Action("network.dns_auto", "network", "Automatic DNS (DHCP)",
           "Returns the connected adapters to the DNS servers provided by the network.", "moderate", 0.2,
           lambda ctx: op.imposta_dns(ctx, None), "Manually configured DNS servers are removed."),
    Action("network.renew_ip", "network", "Renew IP address",
           "Releases and renews the DHCP address of every adapter, then flushes DNS.", "moderate", 0.5, tools.renew_ip,
           "The connection drops for a few seconds; remote sessions may disconnect."),
    Action("network.reset", "network", "Full network reset",
           "Resets Winsock and the TCP/IP stack.", "high", 0.5, op.ripara_rete,
           "Static IP settings and VPN adapters may need to be configured again. A restart is required."),
    # ---------- startup ----------
    Action("startup.optimize", "startup", "Optimize startup",
           "Turns off every program that starts with Windows except essential ones (security, drivers, VPN, management, backup, passwords).",
           "moderate", 0.5, tools.optimize_startup,
           "Programs such as chat, music, game launchers and cloud sync no longer start automatically. Each can be turned back on from Startup & Apps."),
    # ---------- security ----------
    Action("security.quick_scan", "security", "Microsoft Defender quick scan",
           "Scans the places where malware usually hides.", "safe", 10, tools.defender_quick_scan),
    Action("security.full_scan", "security", "Microsoft Defender full scan",
           "Scans every file on every drive. Takes from 30 minutes to a few hours.", "safe", 60, tools.defender_full_scan),
    Action("security.firewall_on", "security", "Turn on the firewall",
           "Enables Windows Firewall on the Domain, Private and Public profiles.", "moderate", 0.2, tools.firewall_on,
           "Applications that relied on the firewall being off may need an inbound rule."),
    Action("security.update_signatures", "security", "Update antivirus signatures",
           "Downloads the latest Microsoft Defender definitions.", "safe", 2, tools.defender_update_signatures),
    Action("security.restore_point", "security", "Create a restore point",
           "Creates a System Restore checkpoint (Windows allows one every 24 hours).", "safe", 2, tools.create_restore_point),
    Action("security.disable_smb1", "security", "Disable SMBv1",
           "Turns off the obsolete SMBv1 file sharing protocol on this PC.", "high", 0.5, tools.disable_smb1,
           "Very old NAS devices, printers or Windows XP machines may no longer reach this PC's shares."),
    # ---------- updates ----------
    Action("updates.scan", "updates", "Check for updates",
           "Asks Windows Update to look for new updates in the background.", "safe", 1, tools.windows_update_scan),
    Action("updates.store_apps", "updates", "Update Microsoft Store apps",
           "Asks the Microsoft Store to check and install app updates in the background.", "safe", 1, tools.store_apps_update),
    Action("updates.install", "updates", "Install pending updates",
           "Downloads and installs all pending software updates.", "moderate", 30, tools.windows_update_install,
           "Can take a long time and may require a restart."),
)

PLAYBOOKS = (
    {"id": "quick", "title": "Quick tune-up", "description": "Safe cleanup and optimization with no restart. Ideal at every visit.",
     "actions": ["cleanup.temp", "storage.wer", "storage.thumbnails", "storage.delivery_optimization", "integrity.trim", "network.flush_dns",
                 "security.update_signatures", "performance.free_memory"]},
    {"id": "full", "title": "Full maintenance", "description": "Deep cleanup, Windows repair, security and drive optimization. Takes 45-60 minutes.",
     "actions": ["cleanup.temp", "cleanup.components", "storage.wer", "storage.thumbnails", "storage.browser_cache", "integrity.dism",
                 "integrity.sfc", "integrity.disk_scan", "storage.optimize_all", "services.safe", "security.update_signatures", "security.quick_scan"]},
    {"id": "repair", "title": "Repair Windows", "description": "Fixes a damaged Windows image, system files and the network stack.",
     "actions": ["integrity.dism", "integrity.sfc", "integrity.disk_scan", "integrity.wmi_verify", "network.flush_dns", "network.optimize"]},
    {"id": "security", "title": "Security hardening", "description": "Signatures, scan, restore point and removal of SMBv1.",
     "actions": ["security.update_signatures", "security.quick_scan", "security.restore_point", "security.disable_smb1"]},
    {"id": "performance", "title": "Performance boost", "description": "Power plan, visual effects, Game DVR and drive optimization.",
     "actions": ["performance.power_high", "performance.game_dvr_off", "performance.visual_best", "storage.optimize_all", "cleanup.temp"]},
)

CATALOG: Dict[str, Action] = {action.id: action for action in _ACTIONS}


def by_area(area: str) -> List[Action]:
    return [action for action in CATALOG.values() if action.area == area]


def safe(area: Optional[str] = None) -> List[Action]:
    return [action for action in CATALOG.values() if action.risk == "safe" and (area is None or action.area == area)]
