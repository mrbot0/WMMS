"""Search by symptom: "I can't see the other PCs", "Internet lento", "Start non si apre". Each symptom lists the
reports to read first and the fixes to try after, in the order a technician would use them (safest first).
match() scores the symptoms against free text in Italian or English, so the Toolbox can propose them while typing."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class Symptom:
    id: str
    title: str
    title_it: str
    keywords: Tuple[str, ...]  # phrases and words in both languages, accents optional
    steps: Tuple[str, ...]     # action ids: reports first, then fixes from the gentlest to the strongest


SYMPTOMS: Tuple[Symptom, ...] = (
    Symptom("lan_visibility", "I can't see the other PCs on the network", "Non vedo gli altri PC in rete",
            ("non vedo gli altri pc", "altri pc", "rete locale", "condivisione", "cartella condivisa", "cartelle condivise", "nas", "stampante condivisa",
             "network discovery", "other pcs", "shared folder", "file sharing", "lan", "risorse di rete", "network neighborhood"),
            ("network.profiles_report", "security.smb_report", "security.shares_report", "network.profile_private", "network.discovery_on",
             "network.flush_dns")),
    Symptom("slow_internet", "The internet is slow", "Internet lento",
            ("internet lento", "connessione lenta", "rete lenta", "navigazione lenta", "download lenti", "slow internet", "slow connection",
             "slow download", "lag", "ping alto", "high ping", "buffering", "velocita"),
            ("network.speed_test", "network.dns_benchmark", "network.wifi_report", "network.wifi_networks", "network.nic_errors",
             "network.tcp_report", "network.flush_dns", "network.autotuning_normal", "performance.nic_power_off", "performance.network_throttling_off")),
    Symptom("no_internet", "No internet connection", "Nessuna connessione Internet",
            ("nessuna connessione", "no internet", "senza internet", "internet non funziona", "non va internet", "niente internet", "offline",
             "mappamondo", "globo", "connesso senza internet", "no connection", "dns", "cannot connect", "non si connette", "limitata"),
            ("network.connectivity_report", "network.ipconfig_report", "network.proxy_report", "network.flush_dns", "network.renew_ip",
             "network.ncsi_reset", "network.reset_proxy", "network.winsock_reset", "network.reset")),
    Symptom("start_menu", "The Start menu won't open", "Il menu Start non si apre",
            ("start non si apre", "menu start", "start bloccato", "start non funziona", "start menu", "start won't open", "start not working",
             "barra delle applicazioni", "taskbar", "tasto windows"),
            ("integrity.sfc_verify", "startup.reset_start_menu", "performance.restart_explorer", "services.restart_text_input",
             "startup.reregister_apps", "integrity.sfc")),
    Symptom("slow_pc", "The PC is slow", "Il PC è lento",
            ("pc lento", "computer lento", "lentezza", "rallenta", "rallentamenti", "si blocca spesso", "slow pc", "slow computer", "sluggish",
             "freezes", "impallato", "va piano", "lento"),
            ("performance.top_processes", "performance.startup_impact", "performance.cpu_throttling", "performance.disk_latency_report",
             "storage.disk_health", "performance.handle_leaks_report", "startup.optimize", "cleanup.temp", "performance.visual_best")),
    Symptom("slow_boot", "Windows takes long to start", "Windows si avvia lentamente",
            ("avvio lento", "accensione lenta", "ci mette tanto ad avviarsi", "parte lento", "slow boot", "slow startup", "slow start",
             "slow sign-in", "accesso lento"),
            ("startup.boot_time_report", "performance.startup_impact", "startup.run_keys_report", "startup.third_party_services",
             "startup.optimize", "performance.startup_delay_off")),
    Symptom("disk_full", "The disk is full", "Il disco è pieno",
            ("disco pieno", "spazio esaurito", "poco spazio", "spazio insufficiente", "liberare spazio", "c pieno", "disk full", "low disk space",
             "free space", "no space", "memoria piena"),
            ("storage.volume_report", "storage.top_folders", "storage.user_folders", "storage.large_files", "storage.temp_report", "cleanup.temp",
             "cleanup.upgrade_leftovers", "storage.disk_cleanup", "storage.hiberfile_reduced", "storage.delete_windows_old")),
    Symptom("no_sound", "There is no sound", "Non si sente l'audio",
            ("audio", "suono", "non si sente", "nessun suono", "casse", "cuffie", "altoparlanti", "no sound", "speakers", "headphones",
             "microfono", "microphone"),
            ("updates.problem_devices", "services.restart_audio")),
    Symptom("printer", "The printer doesn't print", "La stampante non stampa",
            ("stampante", "non stampa", "stampa bloccata", "coda di stampa", "printer", "not printing", "print queue", "stampa"),
            ("updates.problem_devices", "services.clear_print_queue", "services.restart_spooler", "network.discovery_on")),
    Symptom("windows_update", "Windows Update fails or is stuck", "Windows Update non funziona",
            ("windows update", "aggiornamenti", "aggiornamento bloccato", "aggiornamenti non si installano", "errore aggiornamento", "0x8",
             "update stuck", "update error", "updates fail", "non si aggiorna"),
            ("updates.failures_report", "updates.wu_services_report", "updates.pause_status_report", "updates.pending_reboot",
             "services.restart_wu", "updates.bits_reset", "services.restart_cryptsvc", "updates.remove_wu_policies", "integrity.dism",
             "integrity.reset_wu")),
    Symptom("bsod", "Blue screens or sudden restarts", "Schermate blu o riavvii improvvisi",
            ("schermata blu", "bsod", "blue screen", "si riavvia da solo", "riavvii improvvisi", "crash di sistema", "si spegne da solo",
             "restarts by itself", "stop code", "kernel"),
            ("integrity.bsod_report", "integrity.unexpected_shutdowns", "integrity.whea_report", "updates.old_drivers_report",
             "integrity.verifier_status", "integrity.verifier_off", "integrity.small_memory_dumps", "integrity.memory_diagnostic", "integrity.sfc")),
    Symptom("wifi_drops", "Wi-Fi keeps dropping", "Il Wi-Fi cade o si disconnette",
            ("wifi cade", "wi-fi cade", "wifi si disconnette", "wifi instabile", "segnale debole", "wifi drops", "wifi disconnects", "weak signal",
             "wireless", "wlan", "wifi"),
            ("network.wifi_report", "network.wlan_report", "network.wifi_networks", "network.wifi_watch", "performance.nic_power_report",
             "performance.nic_power_off", "services.restart_wlan", "network.restart_adapters")),
    Symptom("camera", "The camera doesn't work", "La fotocamera non funziona",
            ("fotocamera", "webcam", "videocamera", "camera nera", "camera", "teams video", "zoom video", "in uso da un'altra app"),
            ("updates.problem_devices", "services.restart_camera")),
    Symptom("bluetooth", "Bluetooth devices don't connect", "Il Bluetooth non si connette",
            ("bluetooth", "auricolari", "mouse bluetooth", "cuffie bluetooth", "earbuds", "pairing", "associare"),
            ("updates.problem_devices", "services.restart_bluetooth")),
    Symptom("search", "Search finds nothing", "La ricerca non trova nulla",
            ("ricerca non funziona", "ricerca non trova", "cerca non funziona", "search not working", "search finds nothing", "indicizzazione",
             "indexing", "ricerca"),
            ("services.restart_search", "startup.reset_start_menu", "services.rebuild_search_index")),
    Symptom("malware", "I think the PC has a virus", "Penso di avere un virus",
            ("virus", "malware", "infetto", "infezione", "trojan", "ransomware", "hacker", "popup", "pubblicita", "adware", "spyware",
             "infected", "ads everywhere"),
            ("security.defender_status", "security.browser_extensions", "security.browser_policies", "network.proxy_report", "network.hosts_report",
             "security.suspicious_tasks", "startup.run_keys_report", "security.update_signatures", "security.quick_scan", "security.full_scan",
             "security.offline_scan")),
    Symptom("browser_hijack", "The browser opens strange pages", "Il browser apre pagine strane",
            ("browser", "pagina iniziale cambiata", "motore di ricerca cambiato", "pagine strane", "reindirizza", "homepage", "redirect",
             "search engine changed", "chrome", "edge", "firefox"),
            ("security.browser_extensions", "security.browser_policies", "network.proxy_report", "network.hosts_report", "network.reset_proxy",
             "storage.browser_cache")),
    Symptom("overheating", "The PC gets hot and the fans are loud", "Il PC scalda e le ventole fanno rumore",
            ("scalda", "surriscalda", "caldo", "ventole", "ventola", "rumore", "temperatura", "overheating", "hot", "fan noise", "loud fans"),
            ("performance.thermal_report", "performance.top_processes", "performance.gpu_processes", "performance.cpu_throttling",
             "performance.power_balanced")),
    Symptom("battery", "The battery drains fast", "La batteria dura poco",
            ("batteria", "dura poco", "si scarica", "autonomia", "battery", "drains", "battery life"),
            ("performance.battery_report", "performance.sleep_study", "performance.power_requests", "performance.energy_report",
             "performance.power_balanced", "performance.background_off")),
    Symptom("wakes_up", "The PC wakes up on its own", "Il PC si accende o si risveglia da solo",
            ("si accende da solo", "si risveglia", "si sveglia di notte", "wakes up", "turns on by itself", "risveglio"),
            ("performance.wake_report", "performance.wake_timers_off")),
    Symptom("wont_sleep", "The PC won't go to sleep", "Il PC non va in sospensione",
            ("non va in sospensione", "sospensione", "standby", "non si spegne lo schermo", "won't sleep", "sleep", "schermo resta acceso"),
            ("performance.power_requests", "performance.wake_report", "performance.energy_report")),
    Symptom("app_crash", "Programs crash or freeze", "I programmi si chiudono o si bloccano",
            ("programmi si chiudono", "programma si blocca", "non risponde", "crash", "si chiude da solo", "app crash", "not responding",
             "freeze", "bloccato"),
            ("integrity.app_hangs", "integrity.app_crashes_report", "integrity.reliability_report", "updates.runtimes_report", "integrity.sfc",
             "integrity.dism")),
    Symptom("install_fails", "Programs won't install or uninstall", "Non riesco a installare o disinstallare programmi",
            ("non si installa", "installazione fallita", "disinstallare", "windows installer", "msi", "install fails", "uninstall",
             "can't install", "installare"),
            ("updates.runtimes_report", "integrity.reregister_msi", "integrity.sfc")),
    Symptom("store", "The Microsoft Store doesn't work", "Il Microsoft Store non funziona",
            ("microsoft store", "store", "app store", "download store", "negozio"),
            ("integrity.time_sync", "integrity.store_reset", "updates.bits_reset", "startup.reregister_apps")),
    Symptom("clock", "The clock is wrong", "L'ora è sbagliata",
            ("ora sbagliata", "orologio", "data sbagliata", "orario", "wrong time", "clock", "time zone"),
            ("integrity.time_sync", "services.restart_time")),
    Symptom("icons", "Icons or thumbnails look wrong", "Icone o miniature sbagliate",
            ("icone", "icone bianche", "icone vuote", "miniature", "anteprime", "icons", "thumbnails", "caratteri", "fonts"),
            ("integrity.rebuild_icon_cache", "storage.thumbnails", "cleanup.font_cache")),
    Symptom("flicker", "The screen flickers", "Lo schermo sfarfalla",
            ("sfarfalla", "sfarfallio", "schermo nero", "lampeggia", "flicker", "black flashes", "monitor"),
            ("performance.gpu_report", "updates.problem_devices", "performance.mpo_off")),
    Symptom("games", "Games stutter", "I giochi scattano",
            ("giochi", "gioco scatta", "fps", "stuttering", "lag nei giochi", "games", "gaming", "scatti"),
            ("performance.gpu_report", "performance.cpu_throttling", "performance.thermal_report", "performance.game_mode_on",
             "performance.game_dvr_off", "performance.hags_on", "cleanup.shader_cache")),
    Symptom("notifications", "Notifications don't appear", "Le notifiche non arrivano",
            ("notifiche", "centro notifiche", "notifications", "banner"),
            ("startup.reset_notifications",)),
    Symptom("office", "Word, Excel or Outlook crash", "Word, Excel o Outlook si bloccano",
            ("office", "word", "excel", "outlook", "powerpoint", "microsoft 365"),
            ("updates.office_report", "cleanup.office_cache", "startup.office_quick_repair", "updates.office_update")),
    Symptom("teams", "Teams is slow or misbehaves", "Teams è lento o non funziona",
            ("teams", "microsoft teams", "riunioni"),
            ("cleanup.teams_cache", "services.restart_camera", "services.restart_audio")),
    Symptom("usb", "USB devices disconnect", "I dispositivi USB si scollegano",
            ("usb", "chiavetta", "si scollega", "dock", "hub usb", "usb disconnects", "pendrive", "disco esterno"),
            ("updates.usb_report", "updates.problem_devices", "performance.usb_suspend_off", "storage.rescan_disks")),
    Symptom("typing", "I can't type in Start search or Settings", "Non riesco a scrivere nella ricerca o nelle Impostazioni",
            ("non riesco a scrivere", "tastiera non scrive", "can't type", "typing", "digitare", "emoji"),
            ("services.restart_text_input", "startup.reset_start_menu")),
    Symptom("folders_slow", "Folders open slowly", "Le cartelle si aprono lentamente",
            ("cartelle lente", "esplora risorse lento", "explorer lento", "elaborazione in corso", "folders slow", "file explorer slow",
             "download si apre lento"),
            ("performance.folder_type_off", "performance.folder_views_reset", "performance.restart_explorer")),
    Symptom("security_app", "Windows Security won't open", "Sicurezza di Windows non si apre",
            ("sicurezza di windows", "windows defender non si apre", "defender", "windows security"),
            ("security.defender_status", "security.antivirus_report", "security.security_app_reset")),
    Symptom("windows_hello", "Face or fingerprint sign-in stopped working", "Il riconoscimento del volto o dell'impronta non funziona",
            ("windows hello", "impronta", "riconoscimento facciale", "volto", "fingerprint", "face sign-in", "pin"),
            ("updates.problem_devices", "services.restart_biometrics")),
    Symptom("restore_fails", "Restore points or backups fail", "Punti di ripristino o backup non riescono",
            ("punto di ripristino", "ripristino configurazione", "backup non riesce", "vss", "copia shadow", "restore point", "backup fails"),
            ("integrity.restore_points_report", "storage.shadow_report", "security.enable_restore", "integrity.restart_vss")),
    Symptom("some_sites", "Some websites don't load", "Alcuni siti non si aprono",
            ("alcuni siti", "sito non si apre", "pagina non si carica", "some sites", "website won't load", "ipv6", "err_name"),
            ("network.hosts_report", "network.proxy_report", "network.dns_benchmark", "network.flush_dns", "network.prefer_ipv4")),
    Symptom("disk_errors", "The disk makes noises or reports errors", "Il disco fa rumore o dà errori",
            ("disco", "errori del disco", "settori danneggiati", "disco rumoroso", "ssd", "hard disk", "disk errors", "bad sectors",
             "smart", "chkdsk"),
            ("storage.disk_health", "storage.smart_prediction", "integrity.disk_events", "integrity.chkdsk_result", "integrity.disk_scan")),
    Symptom("exposed", "Is a camera or NAS reachable from the internet?", "Telecamera o NAS raggiungibili da Internet?",
            ("telecamera esposta", "porte aperte", "port forwarding", "upnp", "router", "esposto su internet", "raggiungibile da internet",
             "open ports", "exposed", "camera", "nas", "telecamera", "dvr"),
            ("network.upnp_report", "network.public_ip_report", "network.open_ports", "security.smb_report", "security.rdp_report")),
    Symptom("intruder", "Someone else is on my Wi-Fi", "Qualcuno usa il mio Wi-Fi",
            ("intruso", "qualcuno usa il mio wifi", "dispositivo sconosciuto", "chi e connesso", "rubano il wifi", "someone on my wifi",
             "unknown device", "who is connected", "intruder"),
            ("network.watch", "network.arp_report", "network.wifi_report")),
    Symptom("tracked", "A tracker may be following me", "Un localizzatore potrebbe seguirmi",
            ("airtag", "localizzatore", "tracker", "mi segue", "mi seguono", "tile", "smarttag", "following me", "stalker", "pedinato"),
            ("network.bt_watch",)),
    Symptom("public_network", "The network is marked Public", "La rete risulta Pubblica",
            ("rete pubblica", "profilo pubblico", "public network", "rete privata", "private network"),
            ("network.profiles_report", "network.profile_private")),
)

STOPWORDS = frozenset("""il lo la i gli le un uno una di da del della dei delle al alla ai alle e o ma che con per su in a non mi si ho ha
mio mia miei sono e' piu molto troppo the a an of to is it my i on in and or not no doesn't don't won't can't cannot""".split())


def normalize(text: str) -> str:
    senza = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    senza = "".join(c for c in senza if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' -]+", " ", senza)).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[\s'-]+", normalize(text)) if t and t not in STOPWORDS]


def _same(a: str, b: str) -> bool:
    """Same word, or the same stem for longer words ("lento" ~ "lenta", "aggiornamenti" ~ "aggiornamento")."""
    if a == b:
        return True
    return len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]


def score(symptom: Symptom, query: str) -> float:
    testo = " " + normalize(query) + " "
    parole = _tokens(query)
    if not parole:
        return 0.0
    punti = 0.0
    for frase in symptom.keywords:
        f = normalize(frase)
        if " " in f and f" {f} " in testo:
            punti += 3 * len(f.split())  # a whole phrase is worth more than its words
        elif " " not in f and f in parole:
            punti += 1  # a keyword of its own ("stampante") beats the same word inside another phrase
    vocabolario = {t for frase in symptom.keywords + (symptom.title, symptom.title_it) for t in _tokens(frase)}
    trovate = sum(1 for p in parole if any(_same(p, v) for v in vocabolario))
    punti += 2 * trovate
    return punti * (0.5 + 0.5 * trovate / len(parole))


def match(query: str, limit: int = 3) -> List[Tuple[Symptom, float]]:
    """The symptoms that fit the text best, best first."""
    if len(normalize(query)) < 3:
        return []
    voti = sorted(((s, score(s, query)) for s in SYMPTOMS), key=lambda x: -x[1])
    if not voti or voti[0][1] < 2:
        return []
    migliore = voti[0][1]
    return [(s, round(v, 1)) for s, v in voti[:limit] if v >= max(2, migliore * 0.5)]


def as_dict(symptom: Symptom, catalog: dict) -> dict:
    passi = [catalog[a] for a in symptom.steps if a in catalog]
    return {"id": symptom.id, "title": symptom.title, "title_it": symptom.title_it,
            "reports": [a.id for a in passi if a.kind == "report"], "fixes": [a.id for a in passi if a.kind != "report"]}


def search(query: str, catalog: dict, limit: int = 3) -> List[dict]:
    return [dict(as_dict(s, catalog), score=v) for s, v in match(query, limit)]


def all_symptoms(catalog: dict) -> List[dict]:
    return [as_dict(s, catalog) for s in SYMPTOMS]


def check(catalog: dict) -> Sequence[str]:
    """Steps that are not in the catalog (tests keep this empty)."""
    return [f"{s.id}: {a}" for s in SYMPTOMS for a in s.steps if a not in catalog]
