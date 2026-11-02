"""Scores (0-100) and recommended improvements for each area. Pure functions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import wmm  # noqa: F401
from ottimizza_pc import SOGLIA_SPAZIO_LIBERO

MB = 1024 ** 2
GB = 1024 ** 3
IMPACT_PRIORITY = {"high": 1, "medium": 2, "low": 3}
RISK_ORDER = {"safe": 0, "moderate": 1, "high": 2}
WEIGHTS = {"cleanup": 0.12, "integrity": 0.18, "services": 0.08, "performance": 0.14, "storage": 0.10,
           "network": 0.08, "startup": 0.08, "security": 0.16, "updates": 0.06}


@dataclass
class Recommendation:
    id: str
    area: str
    title: str
    reason: str
    impact: str
    risk: str
    action_id: Optional[str]
    priority: int = 0

    def __post_init__(self):
        self.priority = IMPACT_PRIORITY[self.impact]

    def as_dict(self) -> dict:
        return asdict(self)


Assessment = Tuple[int, List[Recommendation]]


def _finish(punteggio: float, raccomandazioni: List[Recommendation]) -> Assessment:
    raccomandazioni.sort(key=lambda r: (r.priority, RISK_ORDER.get(r.risk, 3)))
    return max(0, min(100, int(round(punteggio)))), raccomandazioni


def _gb(byte: float) -> str:
    return f"{byte / GB:.1f} GB" if byte >= GB else f"{byte / MB:.0f} MB"


def _category_bytes(data: dict, *ids: str) -> int:
    return sum(c.get("bytes") or 0 for c in data.get("categories") or [] if c.get("id") in ids)


def _free_percent(volume: dict) -> Optional[float]:
    totale = volume.get("total_gb") or 0
    return 100 * (volume.get("free_gb") or 0) / totale if totale else None


def assess_cleanup(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    recuperabile = data.get("recoverable_bytes") or 0
    punteggio -= min(40, int(recuperabile // (500 * MB)))
    c_libero: Optional[float] = None
    for volume in data.get("volumes") or []:
        libero = _free_percent(volume)
        if libero is None:
            continue
        lettera = volume.get("letter")
        if lettera == "C":
            c_libero = libero
        if libero < SOGLIA_SPAZIO_LIBERO:
            punteggio -= 25
            racc.append(Recommendation(f"cleanup.volume_{lettera}", "cleanup", f"Free up space on drive {lettera}:",
                                       f"Only {libero:.0f}% free ({volume.get('free_gb')} GB of {volume.get('total_gb')} GB).",
                                       "high", "safe", "cleanup.temp"))
        elif libero < 25:
            punteggio -= 10
            racc.append(Recommendation(f"cleanup.volume_{lettera}", "cleanup", f"Drive {lettera}: is getting full",
                                       f"{libero:.0f}% free ({volume.get('free_gb')} GB).", "medium", "safe", "cleanup.temp"))
    temp = _category_bytes(data, "user_temp", "windows_temp", "update_cache", "shader_cache", "crash_dumps")
    if temp >= 200 * MB:
        racc.append(Recommendation("cleanup.temp", "cleanup", "Remove temporary files and caches",
                                   f"{_gb(temp)} of temporary files and caches can be recovered.",
                                   "high" if temp >= 2 * GB else "medium", "safe", "cleanup.temp"))
    cestino = _category_bytes(data, "recycle_bin")
    if cestino >= 500 * MB:
        racc.append(Recommendation("cleanup.recycle_bin", "cleanup", "Empty the Recycle Bin",
                                   f"The Recycle Bin holds {_gb(cestino)}.", "medium", "moderate", "cleanup.recycle_bin"))
    dump = _category_bytes(data, "system_dumps")
    if dump >= GB:
        racc.append(Recommendation("cleanup.dumps", "cleanup", "Delete old crash dumps",
                                   f"Crash dumps use {_gb(dump)}. Keep them only if a crash is being investigated.",
                                   "medium", "moderate", "cleanup.dumps"))
    if c_libero is not None and c_libero < 25:
        racc.append(Recommendation("cleanup.components", "cleanup", "Clean up obsolete Windows components",
                                   f"Drive C: has {c_libero:.0f}% free: the component store can usually shrink by several GB.",
                                   "medium", "moderate", "cleanup.components"))
    return _finish(punteggio, racc)


def _check_is_recent_ok(check: Optional[dict], giorni: int = 30) -> bool:
    if not check or check.get("status") != "ok":
        return False
    try:
        quando = datetime.fromisoformat(check.get("finished") or check.get("started") or "")
    except ValueError:
        return False
    return datetime.now() - quando <= timedelta(days=giorni)


def assess_integrity(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    ssd = False
    for disco in data.get("disks") or []:
        nome = disco.get("name") or "disk"
        ssd = ssd or disco.get("media") == "SSD"
        if disco.get("health") not in (None, "", "Healthy"):
            punteggio -= 40
            racc.append(Recommendation("integrity.disk_health", "integrity", f"Replace or back up {nome}",
                                       f"Disk health is reported as {disco.get('health')}.", "high", "safe", None))
        if (disco.get("wear") or 0) >= 80:
            punteggio -= 25
            racc.append(Recommendation("integrity.disk_wear", "integrity", f"Plan the replacement of {nome}",
                                       f"SSD wear is at {disco.get('wear')}%.", "high", "safe", None))
        if (disco.get("read_errors") or 0) > 0:
            punteggio -= 20
            racc.append(Recommendation("integrity.read_errors", "integrity", f"Check {nome} for bad sectors",
                                       f"{disco.get('read_errors')} uncorrected read errors.", "high", "safe", "integrity.disk_scan"))
    stabilita = data.get("stability") or {}
    spegnimenti = stabilita.get("unexpected_shutdowns") or 0
    whea = stabilita.get("whea") or 0
    errori_disco = stabilita.get("disk_errors") or 0
    punteggio -= min(15, 3 * spegnimenti) + min(20, 5 * whea) + min(15, 3 * errori_disco)
    if whea:
        racc.append(Recommendation("integrity.whea", "integrity", "Investigate hardware errors",
                                   f"{whea} WHEA hardware errors in the last 30 days (CPU, RAM or PCIe).", "high", "safe", None))
    if data.get("reboot_pending"):
        punteggio -= 5
        racc.append(Recommendation("integrity.reboot", "integrity", "Restart the PC",
                                   "A restart is pending to complete updates or repairs.", "medium", "safe", None))
    if (data.get("bios_age_days") or 0) > 730:
        punteggio -= 5
        racc.append(Recommendation("integrity.bios", "integrity", "Consider a BIOS/UEFI update",
                                   f"The firmware is {data['bios_age_days'] // 365} years old.", "low", "high", None))
    sicurezza = data.get("security") or {}
    if sicurezza.get("defender") is False:
        punteggio -= 20
        racc.append(Recommendation("integrity.defender", "integrity", "Turn on real-time protection",
                                   "Microsoft Defender real-time protection is off.", "high", "safe", None))
    if sicurezza.get("firewall_off"):
        punteggio -= 15
        racc.append(Recommendation("integrity.firewall", "integrity", "Turn on the firewall",
                                   "The firewall is off on at least one profile.", "high", "safe", None))
    if (sicurezza.get("signature_age_days") or 0) > 7:
        punteggio -= 5
        racc.append(Recommendation("integrity.signatures", "integrity", "Update antivirus signatures",
                                   f"Signatures are {sicurezza.get('signature_age_days')} days old.", "medium", "safe", None))
    if (data.get("time_service") or {}).get("running") is False:
        punteggio -= 5
        racc.append(Recommendation("integrity.time", "integrity", "Synchronize the clock",
                                   "The Windows Time service is stopped: certificates, Kerberos and logs need an accurate clock.",
                                   "medium", "safe", "integrity.time_sync"))
    registro = data.get("events") or {}
    if (registro.get("total") or 0) > 50:
        punteggio -= 5
        fonte = (registro.get("top") or [{}])[0]
        racc.append(Recommendation("integrity.events", "integrity", "Review recurring errors in the event log",
                                   f"{registro['total']} errors in 7 days; most from {fonte.get('source', '?')} ({fonte.get('count', 0)}).",
                                   "low", "safe", None))
    controlli = data.get("checks") or {}
    eventi = spegnimenti + whea + errori_disco
    sfc_ok = _check_is_recent_ok(controlli.get("integrity.sfc"))
    if eventi or (controlli.get("integrity.sfc") or {}).get("status") not in (None, "ok"):
        motivo = f"{eventi} stability events in the last 30 days." if eventi else "The last SFC check found problems."
        racc.append(Recommendation("integrity.dism", "integrity", "Repair the Windows image",
                                   motivo, "medium", "moderate", "integrity.dism"))
    if eventi or not sfc_ok:
        motivo = f"{eventi} stability events in the last 30 days." if eventi else "No successful SFC check in the last 30 days."
        racc.append(Recommendation("integrity.sfc", "integrity", "Verify system files",
                                   motivo, "medium", "moderate", "integrity.sfc"))
    if ssd and not _check_is_recent_ok(controlli.get("integrity.trim"), 7):
        racc.append(Recommendation("integrity.trim", "integrity", "Run SSD TRIM",
                                   "No TRIM run by this suite in the last 7 days.", "low", "safe", "integrity.trim"))
    return _finish(punteggio, racc)


def assess_services(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    attivi = [s["name"] for s in data.get("managed") or [] if s.get("group") == "safe" and s.get("start") not in ("disabled", None)]
    if attivi:
        punteggio -= min(30, 3 * len(attivi))
        racc.append(Recommendation("services.safe", "services", "Disable unnecessary services",
                                   f"{len(attivi)} non-essential services are enabled: {', '.join(attivi[:5])}{'...' if len(attivi) > 5 else ''}.",
                                   "medium", "moderate", "services.safe"))
    avvio = len(data.get("startup") or [])
    if avvio > 15:
        punteggio -= 20 if avvio > 25 else 10
        racc.append(Recommendation("services.startup", "services", "Reduce startup programs",
                                   f"{avvio} programs start with Windows. Disable unneeded ones in Task Manager > Startup apps.",
                                   "high" if avvio > 25 else "medium", "safe", None))
    return _finish(punteggio, racc)


def assess_performance(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    memoria = data.get("memory") or {}
    carico = memoria.get("load_pct") or 0
    if carico >= 90:
        punteggio -= 20
        racc.append(Recommendation("performance.memory", "performance", "Memory is almost full",
                                   f"{carico}% of {memoria.get('total_gb')} GB in use. Close heavy applications or add RAM.", "high", "safe", None))
    elif carico >= 80:
        punteggio -= 10
        racc.append(Recommendation("performance.memory", "performance", "High memory usage",
                                   f"{carico}% of {memoria.get('total_gb')} GB in use.", "medium", "safe", None))
    if (memoria.get("commit_pct") or 0) >= 90:
        punteggio -= 10
        racc.append(Recommendation("performance.commit", "performance", "Virtual memory nearly exhausted",
                                   f"Commit charge at {memoria['commit_pct']}% of the limit. Enlarge the page file or close applications.", "high", "safe", None))
    piano = (data.get("power") or {}).get("plan")
    if piano == "saver":
        punteggio -= 15
        racc.append(Recommendation("performance.power", "performance", "Leave the power saver plan",
                                   "The power saver plan throttles the CPU.", "medium", "moderate", "performance.power_balanced"))
    elif piano == "balanced" and not data.get("battery"):
        racc.append(Recommendation("performance.power", "performance", "Use the High performance power plan",
                                   "This desktop PC runs the Balanced plan; High performance keeps the CPU at full clock.", "low", "moderate", "performance.power_high"))
    pagefile = data.get("pagefile") or {}
    if not pagefile.get("automatic") and not pagefile.get("files"):
        punteggio -= 15
        racc.append(Recommendation("performance.pagefile", "performance", "Enable a page file",
                                   "No page file is configured: applications can crash when memory runs out.", "high", "safe", None))
    if (data.get("uptime_hours") or 0) >= 168:
        punteggio -= 10
        racc.append(Recommendation("performance.uptime", "performance", "Restart the PC",
                                   f"Running for {int(data['uptime_hours'] // 24)} days without a restart.", "medium", "safe", None))
    if data.get("fast_startup") is True:
        punteggio -= 5
        racc.append(Recommendation("performance.fast_startup", "performance", "Turn off Fast Startup",
                                   "Fast Startup keeps drivers and the kernel across shutdowns and can hide problems.", "low", "moderate", "performance.fast_startup_off"))
    if data.get("game_dvr") is True:
        punteggio -= 5
        racc.append(Recommendation("performance.game_dvr", "performance", "Turn off background game recording",
                                   "Game DVR records in the background and costs GPU and disk time.", "low", "moderate", "performance.game_dvr_off"))
    ibernazione = data.get("hibernation") or {}
    if ibernazione.get("enabled") and (ibernazione.get("size_gb") or 0) >= 4 and not data.get("battery"):
        racc.append(Recommendation("performance.hibernation", "performance", "Turn off hibernation",
                                   f"hiberfil.sys uses {ibernazione['size_gb']} GB on this desktop PC.", "low", "moderate", "performance.hibernation_off"))
    if data.get("transparency") is True and (memoria.get("total_gb") or 99) < 8:
        racc.append(Recommendation("performance.transparency", "performance", "Turn off transparency effects",
                                   f"Only {memoria.get('total_gb')} GB of RAM: transparency costs GPU and memory.", "low", "moderate", "performance.transparency_off"))
    if data.get("background_apps") is True:
        racc.append(Recommendation("performance.background", "performance", "Stop apps running in the background",
                                   "Store apps can run in the background and use CPU, memory and network.", "low", "moderate", "performance.background_off"))
    salute = (data.get("battery_info") or {}).get("health_pct")
    if data.get("battery") and salute is not None and salute < 70:
        punteggio -= 5
        racc.append(Recommendation("performance.battery", "performance", "Replace the battery",
                                   f"The battery holds {salute}% of its design capacity.", "medium", "safe", None))
    if data.get("visual_effects") in (None, 0, 1) and (memoria.get("total_gb") or 99) < 8:
        punteggio -= 5
        racc.append(Recommendation("performance.visual", "performance", "Optimize visual effects for performance",
                                   f"Only {memoria.get('total_gb')} GB of RAM: animations and shadows cost responsiveness.", "low", "moderate", "performance.visual_best"))
    return _finish(punteggio, racc)


def assess_storage(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    browser = _category_bytes(data, "browser_cache")
    if browser >= 500 * MB:
        punteggio -= 5
        racc.append(Recommendation("storage.browser_cache", "storage", "Clear browser caches",
                                   f"Browser caches use {_gb(browser)}.", "medium", "moderate", "storage.browser_cache"))
    wer = _category_bytes(data, "wer")
    if wer >= 100 * MB:
        punteggio -= 5
        racc.append(Recommendation("storage.wer", "storage", "Delete error reports",
                                   f"Windows Error Reporting keeps {_gb(wer)} of reports.", "medium", "safe", "storage.wer"))
    miniature = _category_bytes(data, "thumbnails")
    if miniature >= 200 * MB:
        punteggio -= 3
        racc.append(Recommendation("storage.thumbnails", "storage", "Reset the thumbnail cache",
                                   f"The thumbnail cache uses {_gb(miniature)}.", "low", "safe", "storage.thumbnails"))
    vecchio = data.get("windows_old_bytes") or 0
    if vecchio > 0:
        punteggio -= 10
        racc.append(Recommendation("storage.windows_old", "storage", "Remove the previous Windows installation",
                                   f"Windows.old uses {_gb(vecchio)}. Remove it with Disk Cleanup › Clean up system files once the upgrade is confirmed.",
                                   "medium", "moderate", None))
    if data.get("storage_sense") is False:
        punteggio -= 5
        racc.append(Recommendation("storage.storage_sense", "storage", "Turn on Storage Sense",
                                   "Windows can clear temporary files and the Recycle Bin automatically.", "low", "moderate", "storage.storage_sense"))
    for ombra in data.get("shadow") or []:
        if (ombra.get("used_gb") or 0) >= 20:
            racc.append(Recommendation(f"storage.shadow_{ombra.get('volume')}", "storage", "Review restore point storage",
                                       f"Restore points use {ombra['used_gb']} GB on {ombra.get('volume')}:.", "low", "moderate", None))
    for volume in data.get("volumes") or []:
        libero = _free_percent(volume)
        if libero is not None and libero < SOGLIA_SPAZIO_LIBERO:
            punteggio -= 15
            racc.append(Recommendation(f"storage.full_{volume.get('letter')}", "storage", f"Drive {volume.get('letter')}: is almost full",
                                       f"{libero:.0f}% free. Review the largest folders and files below.", "high", "safe", None))
    if not _check_is_recent_ok((data.get("checks") or {}).get("storage.optimize_all"), 30):
        racc.append(Recommendation("storage.optimize", "storage", "Optimize all drives",
                                   "No drive optimization by this suite in the last 30 days.", "low", "safe", "storage.optimize_all"))
    return _finish(punteggio, racc)


def assess_network(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    schede = data.get("adapters") or []
    attive = [s for s in schede if s.get("status") == "Up"]
    if not attive:
        punteggio -= 60
        racc.append(Recommendation("network.offline", "network", "No network adapter is connected",
                                   "Check the cable or Wi-Fi connection.", "high", "safe", None))
    perdite = 0
    for destinazione in data.get("targets") or []:
        if destinazione.get("lost"):
            perdite += 1
            racc.append(Recommendation(f"network.loss_{destinazione['name'].lower()}", "network", f"Packet loss towards {destinazione['name']}",
                                       f"{destinazione['lost']} of {destinazione.get('sent')} packets lost"
                                       + (": the problem is on the local network (cable, Wi-Fi, router)." if destinazione["name"] == "Router" else "."),
                                       "high", "safe", None))
    punteggio -= min(30, 10 * perdite)
    internet = [d for d in data.get("targets") or [] if d.get("name") != "Router" and d.get("lost", 0) < d.get("sent", 1)]
    if internet:
        migliore = min(internet, key=lambda d: d.get("avg") or 0)
        if (migliore.get("avg") or 0) > 80:
            punteggio -= 10
            racc.append(Recommendation("network.latency", "network", "High internet latency",
                                       f"Average {migliore['avg']} ms towards {migliore['name']}.", "medium", "safe", None))
        if (migliore.get("jitter") or 0) > 20:
            punteggio -= 10
            racc.append(Recommendation("network.jitter", "network", "Unstable connection",
                                       f"Jitter of {migliore['jitter']} ms: calls and games will stutter.", "medium", "safe", None))
    if attive and not data.get("dns_ok", True):
        punteggio -= 20
        racc.append(Recommendation("network.dns_fail", "network", "Name resolution fails",
                                   "DNS lookups do not work. Flush the DNS cache or switch DNS server.", "high", "safe", "network.flush_dns"))
    elif (data.get("dns_ms") or 0) > 150:
        punteggio -= 10
        racc.append(Recommendation("network.dns_slow", "network", "Use a faster DNS server",
                                   f"DNS lookups take {data['dns_ms']} ms.", "medium", "moderate", "network.dns_cloudflare"))
    proxy = data.get("proxy") or {}
    if proxy.get("enabled"):
        racc.append(Recommendation("network.proxy", "network", "A proxy server is configured",
                                   f"Traffic goes through {proxy.get('server') or 'a proxy'}. Check it is expected (malware often sets one).", "low", "safe", None))
    if data.get("hosts_entries"):
        racc.append(Recommendation("network.hosts", "network", "Review the hosts file",
                                   f"{len(data['hosts_entries'])} custom entries, e.g. {data['hosts_entries'][0]}.", "low", "safe", None))
    for scheda in attive:
        velocita = scheda.get("speed_mbps")
        if velocita is not None and velocita < 100:
            racc.append(Recommendation(f"network.speed_{scheda.get('name')}", "network", f"Slow link on {scheda.get('name')}",
                                       f"The adapter links at {scheda.get('speed')}.", "low", "safe", None))
    return _finish(punteggio, racc)


def assess_startup(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    attive = [v for v in data.get("items") or [] if v.get("enabled")]
    if len(attive) > 8:
        punteggio -= min(30, 3 * (len(attive) - 8))
        racc.append(Recommendation("startup.items", "startup", "Disable unneeded startup programs",
                                   f"{len(attive)} programs start with Windows. Optimize startup turns off the non-essential ones.",
                                   "medium" if len(attive) < 15 else "high", "moderate", "startup.optimize"))
    if len(data.get("tasks") or []) > 30:
        racc.append(Recommendation("startup.tasks", "startup", "Review third-party scheduled tasks",
                                   f"{len(data['tasks'])} non-Microsoft scheduled tasks are registered.", "low", "safe", None))
    return _finish(punteggio, racc)


def assess_security(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    difesa = data.get("defender") or {}

    def regola(condizione: bool, penalita: int, ident: str, titolo: str, motivo: str, impatto: str, rischio: str = "safe", azione: Optional[str] = None):
        nonlocal punteggio
        if condizione:
            punteggio -= penalita
            racc.append(Recommendation(ident, "security", titolo, motivo, impatto, rischio, azione))

    regola(difesa.get("realtime") is False, 25, "security.realtime", "Turn on real-time protection",
           "Microsoft Defender real-time protection is off.", "high")
    regola((difesa.get("signature_age_days") or 0) > 3, 10, "security.signatures", "Update antivirus signatures",
           f"Signatures are {difesa.get('signature_age_days')} days old.", "medium", "safe", "security.update_signatures")
    eta_scansione = difesa.get("quick_scan_age_days")
    regola(bool(difesa) and (eta_scansione is None or eta_scansione > 7), 5, "security.scan", "Run a quick antivirus scan",
           f"Last quick scan {eta_scansione} days ago." if eta_scansione is not None else "No quick scan recorded.", "low", "safe", "security.quick_scan")
    spenti = [f["name"] for f in data.get("firewall") or [] if not f.get("enabled")]
    regola(bool(spenti), 15, "security.firewall", "Turn on the firewall", f"Firewall off on: {', '.join(spenti)}.", "high",
           "moderate", "security.firewall_on")
    regola((data.get("uac") or {}).get("enabled") is False, 25, "security.uac", "Turn on User Account Control",
           "UAC is disabled: every program runs with full rights.", "high", "high", "security.uac_on")
    regola(data.get("smartscreen") == "Off", 10, "security.smartscreen", "Turn on SmartScreen",
           "SmartScreen does not check downloaded applications.", "medium", "moderate", "security.smartscreen_on")
    regola(data.get("secure_boot") is False, 10, "security.secure_boot", "Enable Secure Boot",
           "Secure Boot is off in the firmware settings.", "medium", "high")
    regola((data.get("tpm") or {}).get("present") is False, 5, "security.tpm", "No TPM detected",
           "Enable the TPM (fTPM/PTT) in the firmware settings.", "low", "high")
    c_volume = [b for b in data.get("bitlocker") or [] if str(b.get("mount", "")).upper().startswith("C")]
    regola(bool(c_volume) and c_volume[0].get("protection") != "On", 5, "security.bitlocker", "Encrypt the system drive",
           "BitLocker protection is off on C:. A lost or stolen disk can be read.", "low", "moderate")
    regola(data.get("rdp_enabled") is True, 5, "security.rdp", "Remote Desktop is enabled",
           "Disable it if it is not used, or restrict it to the VPN.", "low", "moderate", "security.rdp_off")
    regola(data.get("smb1") is True, 15, "security.smb1", "Disable SMBv1",
           "The obsolete SMBv1 protocol is enabled (WannaCry attack vector).", "high", "high", "security.disable_smb1")
    regola(len(data.get("admins") or []) > 2, 5, "security.admins", "Too many administrators",
           f"{len(data['admins'])} accounts are local administrators: {', '.join(data['admins'][:5])}.", "medium")
    regola(data.get("guest_enabled") is True, 10, "security.guest", "Disable the Guest account",
           "The built-in Guest account is enabled.", "medium", "moderate", "security.disable_guest")
    regola(data.get("autorun_disabled") is False, 5, "security.autorun", "Disable AutoRun",
           "Removable drives and discs can start programs automatically.", "low", "moderate", "security.disable_autorun")
    regola(data.get("pua_protection") is False, 5, "security.pua", "Block potentially unwanted apps",
           "Defender does not block adware, bundlers and other unwanted applications.", "low", "moderate", "security.pua_protection")
    regola(data.get("smb_insecure_guest") is True, 10, "security.smb_guest", "Block insecure guest file sharing",
           "Windows connects to SMB shares without authentication (guest logons).", "high", "moderate", "security.block_smb_guest")
    regola(data.get("llmnr_disabled") is False, 3, "security.llmnr", "Disable LLMNR",
           "Multicast name resolution can be abused to capture network credentials.", "low", "moderate", "security.disable_llmnr")

    def consiglio(condizione: bool, ident: str, titolo: str, motivo: str, rischio: str, azione: str):
        if condizione:
            racc.append(Recommendation(ident, "security", titolo, motivo, "low", rischio, azione))

    consiglio(data.get("lsa_protection") is False, "security.lsa", "Protect LSA credentials",
              "LSA protection (RunAsPPL) keeps credential-stealing tools out of the LSASS process.", "high", "security.lsa_protection")
    consiglio("telemetry_level" in data and (data["telemetry_level"] is None or data["telemetry_level"] >= 3), "security.telemetry",
              "Reduce diagnostic data", "Windows sends optional diagnostic data to Microsoft.", "moderate", "security.reduce_telemetry")
    consiglio(data.get("advertising_id") is True, "security.advertising", "Turn off the advertising ID",
              "Apps can use the advertising ID to profile the user.", "moderate", "security.disable_advertising_id")
    consiglio((data.get("recent_items") or 0) > 500, "security.recent", "Clear the recent items list",
              f"{data.get('recent_items')} shortcuts to recently opened files are stored.", "safe", "security.clear_recent_items")
    regola(data.get("restore_enabled") is False, 10, "security.restore_off", "Turn on System Restore",
           "System Restore is off on the system drive: no restore point can be created.", "high", "safe", "security.enable_restore")
    punti = data.get("restore_points") or []
    recente = punti[0].get("created") if punti else None
    try:
        vecchio = recente is None or datetime.now() - datetime.fromisoformat(recente) > timedelta(days=30)
    except ValueError:
        vecchio = True
    regola(vecchio, 10, "security.restore_point", "Create a restore point",
           "No restore point in the last 30 days." if punti else "No restore point exists.", "medium", "safe", "security.restore_point")
    return _finish(punteggio, racc)


SEVERE_UPDATES = ("Critical", "Important")


def assess_updates(data: dict) -> Assessment:
    punteggio = 100.0
    racc: List[Recommendation] = []
    in_attesa = data.get("pending") or []
    gravi = [u for u in in_attesa if u.get("severity") in SEVERE_UPDATES]
    altri = [u for u in in_attesa if u.get("severity") not in SEVERE_UPDATES]
    punteggio -= min(40, 10 * len(gravi)) + min(15, 3 * len(altri))
    if in_attesa:
        racc.append(Recommendation("updates.pending", "updates", "Install pending updates",
                                   f"{len(in_attesa)} updates are waiting" + (f", {len(gravi)} critical or important." if gravi else "."),
                                   "high" if gravi else "medium", "moderate", "updates.install"))
    if data.get("reboot_required"):
        punteggio -= 10
        racc.append(Recommendation("updates.reboot", "updates", "Restart to finish updates",
                                   "Windows is waiting for a restart.", "medium", "safe", None))
    dispositivi = data.get("problem_devices") or []
    punteggio -= min(30, 10 * len(dispositivi))
    if dispositivi:
        racc.append(Recommendation("updates.devices", "updates", "Fix devices with errors",
                                   f"{len(dispositivi)} devices report an error: {', '.join(d.get('name') or '?' for d in dispositivi[:3])}. Check Device Manager.",
                                   "high", "safe", None))
    if data.get("office_c2r"):
        racc.append(Recommendation("updates.office", "updates", "Update Microsoft Office",
                                   "Microsoft 365 / Office Click-to-Run is installed: it updates separately from Windows Update.", "low", "moderate", "updates.office_update"))
    if data.get("winget"):
        racc.append(Recommendation("updates.winget", "updates", "Update installed applications",
                                   "winget is available: it can update most installed desktop apps in one run.", "low", "moderate", "updates.winget_upgrade"))
    vecchi = [d for d in data.get("drivers") or [] if (d.get("age_days") or 0) > 3 * 365]
    if vecchi:
        racc.append(Recommendation("updates.drivers", "updates", "Review old drivers",
                                   f"{len(vecchi)} third-party drivers are older than 3 years (e.g. {vecchi[0].get('name')}).", "low", "moderate", None))
    return _finish(punteggio, racc)


ASSESSORS: Dict[str, Callable[[dict], Assessment]] = {
    "cleanup": assess_cleanup,
    "integrity": assess_integrity,
    "services": assess_services,
    "performance": assess_performance,
    "storage": assess_storage,
    "network": assess_network,
    "startup": assess_startup,
    "security": assess_security,
    "updates": assess_updates,
}


INCOMPLETE_CAP = 50


def assess(area: str, data: dict) -> Assessment:
    """Assess an area; a collection that failed must never look healthy."""
    punteggio, raccomandazioni = ASSESSORS[area](data)
    errori = data.get("errors") or []
    if errori:
        punteggio = min(punteggio, INCOMPLETE_CAP)
        motivo = "Some data could not be read: " + "; ".join(errori)
        raccomandazioni.insert(0, Recommendation(
            f"{area}.incomplete", area, "Scan incomplete: run it again as administrator",
            motivo[:300], "high", "safe", None))
    return punteggio, raccomandazioni


def overall_score(scores: Dict[str, int]) -> int:
    pesi = {area: peso for area, peso in WEIGHTS.items() if scores.get(area) is not None}
    if not pesi:
        return 0
    return int(round(sum(scores[area] * peso for area, peso in pesi.items()) / sum(pesi.values())))
