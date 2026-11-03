"""Applications page: what is installed, which programs are risky or unused, Store apps,
browser caches and app updates. Reading never changes anything; the API runs the changes."""
from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import wmm  # noqa: F401

from . import inventory
from .collectors import _powershell
from .tools import _files, expand, powershell_command, wipe

UNUSED_DAYS = 120
OLD_INSTALL_DAYS = 3 * 365

# ---------- rules: end of life, known holes, unwanted programs ----------

# The rules live in a data file, so they can be updated without a new version of the program:
# wmm/data/app_rules.json ships with it, "Update the rules" saves a newer copy in the data folder.
BUNDLED_RULES = Path(__file__).resolve().parent.parent / "data" / "app_rules.json"
RULES_URL = "https://raw.githubusercontent.com/mrbot0/WMMS/main/wmm/data/app_rules.json"
RULES_MAX_BYTES = 512 * 1024
RULES_OVERRIDE: Optional[Path] = None  # set by the agent: <data folder>/app_rules.json
RULES_INFO: dict = {}

# (name pattern, end of support, what to tell the user). A product listed here is unsafe after that date.
END_OF_LIFE: List[Tuple[str, str, str]] = []
PYTHON_EOL: Dict[Tuple[int, int], str] = {}
NODE_EOL: Dict[int, str] = {}
# (name pattern, first safe version, the hole fixed there).
MIN_VERSIONS: List[Tuple[str, str, str]] = []
UNWANTED = OPTIMIZERS = REMOTE_ACCESS = STORE_BLOAT = r"(?!)"


def validate_rules(dati) -> dict:
    """Checks a rules file before it is used: types, dates, versions and patterns that compile. ValueError otherwise."""
    if not isinstance(dati, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(dati.get("version") or "")):
        raise ValueError("not a rules file (no version date)")

    def pattern(testo, dove: str) -> str:
        if not isinstance(testo, str) or not testo or len(testo) > 2000:
            raise ValueError(f"{dove}: invalid pattern")
        try:
            re.compile(testo)
        except re.error as errore:
            raise ValueError(f"{dove}: {errore}") from None
        return testo

    def data(testo, dove: str) -> str:
        if not isinstance(testo, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo):
            raise ValueError(f"{dove}: invalid date")
        return testo

    def terne(chiave: str, secondo) -> List[Tuple[str, str, str]]:
        voci = dati.get(chiave)
        if not isinstance(voci, list) or len(voci) > 500:
            raise ValueError(f"{chiave} must be a list")
        uscita = []
        for i, voce in enumerate(voci):
            if not isinstance(voce, list) or len(voce) != 3 or not isinstance(voce[2], str):
                raise ValueError(f"{chiave}[{i}] must be [pattern, value, text]")
            uscita.append((pattern(voce[0], f"{chiave}[{i}]"), secondo(voce[1], f"{chiave}[{i}]"), voce[2][:400]))
        return uscita

    def versione(testo, dove: str) -> str:
        if not isinstance(testo, str) or not re.fullmatch(r"\d+(\.\d+){0,3}", testo):
            raise ValueError(f"{dove}: invalid version")
        return testo

    def date_per(chiave: str, forma: str) -> dict:
        voci = dati.get(chiave)
        if not isinstance(voci, dict):
            raise ValueError(f"{chiave} must be an object")
        uscita = {}
        for k, v in voci.items():
            if not re.fullmatch(forma, str(k)):
                raise ValueError(f"{chiave}: invalid key {k}")
            uscita[tuple(int(x) for x in str(k).split(".")) if "." in str(k) else int(k)] = data(v, f"{chiave}.{k}")
        return uscita

    return {
        "version": dati["version"],
        "end_of_life": terne("end_of_life", data), "min_versions": terne("min_versions", versione),
        "python_eol": date_per("python_eol", r"\d+\.\d+"), "node_eol": date_per("node_eol", r"\d+"),
        "unwanted": pattern(dati.get("unwanted"), "unwanted"), "optimizers": pattern(dati.get("optimizers"), "optimizers"),
        "remote_access": pattern(dati.get("remote_access"), "remote_access"), "store_bloat": pattern(dati.get("store_bloat"), "store_bloat"),
    }


def apply_rules(regole: dict, origine: str) -> None:
    global END_OF_LIFE, PYTHON_EOL, NODE_EOL, MIN_VERSIONS, UNWANTED, OPTIMIZERS, REMOTE_ACCESS, STORE_BLOAT, RULES_INFO
    END_OF_LIFE, MIN_VERSIONS = regole["end_of_life"], regole["min_versions"]
    PYTHON_EOL, NODE_EOL = regole["python_eol"], regole["node_eol"]
    UNWANTED, OPTIMIZERS, REMOTE_ACCESS, STORE_BLOAT = regole["unwanted"], regole["optimizers"], regole["remote_access"], regole["store_bloat"]
    RULES_INFO = {"version": regole["version"], "source": origine, "end_of_life": len(END_OF_LIFE), "min_versions": len(MIN_VERSIONS)}


def _read_rules(percorso: Path) -> Optional[dict]:
    try:
        return validate_rules(json.loads(percorso.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def load_rules() -> dict:
    """The newest valid rules: the downloaded copy when it is newer than the one shipped with the program."""
    integrate = _read_rules(BUNDLED_RULES)
    scaricate = _read_rules(RULES_OVERRIDE) if RULES_OVERRIDE else None
    if scaricate and (not integrate or scaricate["version"] > integrate["version"]):
        apply_rules(scaricate, "downloaded")
    elif integrate:
        apply_rules(integrate, "built-in")
    return dict(RULES_INFO)


def update_rules(url: str = RULES_URL) -> dict:
    """Downloads the rules from the project repository; they are used only when valid and newer."""
    import urllib.request
    richiesta = urllib.request.Request(url, headers={"User-Agent": "WindowsMaintenanceManager/" + wmm.VERSION})
    with urllib.request.urlopen(richiesta, timeout=20) as risposta:
        testo = risposta.read(RULES_MAX_BYTES + 1)
    if len(testo) > RULES_MAX_BYTES:
        raise ValueError("the rules file is too large")
    regole = validate_rules(json.loads(testo.decode("utf-8")))
    attuale = RULES_INFO.get("version", "")
    if regole["version"] <= attuale:
        return dict(RULES_INFO, updated=False)
    if RULES_OVERRIDE is None:
        raise ValueError("no data folder to save the rules")
    RULES_OVERRIDE.write_bytes(testo)
    apply_rules(regole, "downloaded")
    return dict(RULES_INFO, updated=True)


BROWSERS = r"^(?:google chrome|mozilla firefox|microsoft edge|brave|opera(?: gx)?(?: stable)?|vivaldi|waterfox|librewolf|tor browser|chromium)\b"
ANTIVIRUS = r"avast|avg (?:antivirus|internet)|eset|kaspersky|bitdefender|norton|mcafee|sophos|malwarebytes|trend micro|webroot|panda dome|f-secure|g data|avira|total ?av"
RUNTIMES = r"visual c\+\+|\.net|^java|^python|node\.js|directx|webview2|runtime|redistributable"
# Never suggested for removal: other programs or the hardware depend on them.
SYSTEM = (
    r"windows (?:sdk|driver|app certification)|update health|driver|chipset|realtek|nvidia|amd software|radeon|intel\(r\)|^intel |"
    r"synaptics|elan |bluetooth|audio|firmware|bios|microsoft update|windows pc health|gaming services"
)


def _date(testo: Optional[str]) -> Optional[date]:
    try:
        return datetime.strptime(str(testo)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def version_tuple(testo: str) -> Tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", testo or "")[:4])


def _below(versione: str, minima: str) -> bool:
    attuale = version_tuple(versione)
    return bool(attuale) and attuale < version_tuple(minima)


def category(app: dict) -> str:
    nome = app["name"].lower()
    for chiave, pattern in (("unwanted", UNWANTED), ("optimizer", OPTIMIZERS), ("remote", REMOTE_ACCESS), ("browser", BROWSERS),
                            ("antivirus", ANTIVIRUS), ("runtime", RUNTIMES), ("system", SYSTEM)):
        if re.search(pattern, nome):
            return chiave
    if re.search(r"nvidia|advanced micro devices|realtek", (app.get("publisher") or "").lower()):
        return "system"
    return "app"


def assess(app: dict, oggi: date) -> List[dict]:
    """Problems with one installed program, most serious first: level is "risk", "review" or "info"."""
    nome, versione = app["name"].lower(), app.get("version", "")
    problemi: List[dict] = []
    for pattern, fine, testo in END_OF_LIFE:
        if re.search(pattern, nome):
            scadenza = _date(fine)
            if scadenza <= oggi:
                problemi.append({"level": "risk", "kind": "eol", "text": testo})
            elif scadenza - oggi <= timedelta(days=90):
                problemi.append({"level": "review", "kind": "eol_soon", "text": testo + " Plan the switch to a newer version."})
            break
    trovato = re.match(r"python (\d)\.(\d+)", nome)
    if trovato:
        fine = PYTHON_EOL.get((int(trovato.group(1)), int(trovato.group(2))))
        if fine and _date(fine) <= oggi:
            problemi.append({"level": "risk", "kind": "eol", "text": f"Python {trovato.group(1)}.{trovato.group(2)} gets no security fixes since {fine}."})
    if re.match(r"node\.?js", nome):
        maggiore = version_tuple(versione)[:1]
        fine = NODE_EOL.get(maggiore[0]) if maggiore else None
        if fine and _date(fine) <= oggi:
            problemi.append({"level": "risk", "kind": "eol", "text": f"Node.js {maggiore[0]} gets no security fixes since {fine}."})
    for pattern, minima, testo in MIN_VERSIONS:
        if re.search(pattern, nome) and _below(versione, minima):
            problemi.append({"level": "risk", "kind": "vulnerable", "text": f"{testo} Update to {minima} or later."})
    tipo = app.get("category") or category(app)
    if tipo == "unwanted":
        problemi.append({"level": "risk", "kind": "unwanted", "text": "Known adware or unwanted program: it changes browser settings or shows ads. Remove it."})
    elif tipo == "optimizer":
        problemi.append({"level": "review", "kind": "optimizer",
                         "text": "\"Optimizer\" and driver updater programs often bundle adware and change settings on their own. Windows does not need them."})
    elif tipo == "remote":
        problemi.append({"level": "review", "kind": "remote", "text": "Remote access tool: whoever has its password controls this PC. Remove it if you no longer use it."})
    if not app.get("publisher") and not nome.startswith("microsoft"):
        problemi.append({"level": "review", "kind": "publisher", "text": "No publisher: the program does not say who made it."})
    if app.get("broken"):
        problemi.append({"level": "info", "kind": "broken", "text": "Leftover entry: the uninstaller is gone, so the program is probably already removed."})
    installata = _date(app.get("installed"))
    if installata and (oggi - installata).days > OLD_INSTALL_DAYS and tipo in ("app", "browser") and not problemi:
        problemi.append({"level": "info", "kind": "old", "text": f"Not updated since {installata.year}: check whether a newer version exists."})
    ordine = {"risk": 0, "review": 1, "info": 2}
    return sorted(problemi, key=lambda p: ordine[p["level"]])


def status(problemi: List[dict]) -> str:
    livelli = {p["level"] for p in problemi}
    return "risk" if "risk" in livelli else "review" if "review" in livelli else "ok"


def usage(app: dict, oggi: date, completo: bool = True) -> dict:
    """How recently the program ran: "recent", "unused" (not for UNUSED_DAYS) or "unknown".
    With no recorded run, an old program counts as unused only when `completo` (Prefetch was readable)."""
    ultimo = _date(app.get("last_used"))
    if ultimo:
        giorni = max((oggi - ultimo).days, 0)
        return {"usage": "unused" if giorni >= UNUSED_DAYS else "recent", "days_unused": giorni}
    installata = _date(app.get("installed"))
    if completo and installata and (oggi - installata).days >= UNUSED_DAYS:
        return {"usage": "unused", "days_unused": None}
    return {"usage": "unknown", "days_unused": None}


def removable(app: dict) -> bool:
    return app.get("category") not in ("system", "runtime", "antivirus") and bool(app.get("uninstall")) and not app.get("broken")


def base_name(nome: str) -> str:
    """'Python 3.11.4 (64-bit)' -> 'python': the same product in several versions."""
    testo = re.sub(r"\(.*?\)|\b(x64|x86|64-bit|32-bit|amd64)\b", " ", nome.lower())
    testo = re.sub(r"\b(v?\d+([.\-]\d+)*|update \d+)\b", " ", testo)
    return re.sub(r"[\s\-]+", " ", testo).strip(" -")


def plural(n: int, singolare: str, plurale: str = "") -> str:
    return f"{n} {singolare if n == 1 else plurale or singolare + 's'}"


def megabytes(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def suggestions(apps: List[dict], store: List[dict], browsers: List[dict]) -> List[dict]:
    """Advice on the whole set of programs, most useful first."""
    consigli: List[dict] = []

    def aggiungi(livello: str, titolo: str, testo: str, ids: Iterable[str] = (), azione: str = "") -> None:
        consigli.append({"level": livello, "title": titolo, "text": testo, "apps": list(ids), "action": azione})

    rischio = [a for a in apps if a["status"] == "risk"]
    if rischio:
        aggiungi("risk", plural(len(rischio), "unsafe program"), "End of support, known holes or adware: update or remove them first.",
                 [a["id"] for a in rischio], "filter:risk")
    antivirus = [a for a in apps if a["category"] == "antivirus" and "malwarebytes" not in a["name"].lower()]
    if len(antivirus) > 1:
        aggiungi("risk", "More than one antivirus", "Two real-time antivirus programs slow the PC and can block each other. "
                 "Keep one: Microsoft Defender is enough for most people.", [a["id"] for a in antivirus])
    remoti = [a for a in apps if a["category"] == "remote"]
    if remoti:
        aggiungi("review", "Remote access programs", "Each one is a door into this PC. Keep only the one you use.", [a["id"] for a in remoti])
    inutili = [a for a in apps if a["usage"] == "unused" and a["removable"]]
    if inutili:
        spazio = sum(a.get("size_mb") or 0 for a in inutili)
        aggiungi("info", plural(len(inutili), "program") + " not used for months",
                 (f"Removing them frees about {megabytes(spazio)} and leaves" if spazio else "Removing them leaves") + " fewer programs to keep updated.", [a["id"] for a in inutili], "filter:unused")
    gruppi: Dict[str, List[dict]] = {}
    for app in apps:
        if app["category"] in ("app", "runtime") and not re.search(r"visual c\+\+|\.net|redistributable|sdk|runtime", app["name"].lower()):
            gruppi.setdefault(base_name(app["name"]), []).append(app)
    for nome, gruppo in sorted(gruppi.items()):
        if nome and len(gruppo) > 1 and len({g["version"] for g in gruppo}) > 1:
            aggiungi("info", f"{min((g['name'] for g in gruppo), key=len)}: {len(gruppo)} versions installed",
                     "Older versions are often left behind by updates: remove those no program needs.", [g["id"] for g in gruppo])
    browser = [a for a in apps if a["category"] == "browser" and "edge" not in a["name"].lower()]
    if len(browser) > 1:
        aggiungi("info", f"{len(browser) + 1} browsers", "Every browser needs its own updates and keeps its own cache. Keep the ones you really use.",
                 [a["id"] for a in browser])
    rotti = [a for a in apps if a.get("broken")]
    if rotti:
        aggiungi("info", plural(len(rotti), "leftover entry", "leftover entries"), "The programs are gone but still listed in Settings > Apps. "
                 "You can remove the entries (a backup of each is kept).", [a["id"] for a in rotti], "filter:broken")
    extra = [s for s in store if s.get("bloat")]
    if extra:
        aggiungi("info", plural(len(extra), "preinstalled Store app"), "Games, news and trial apps Windows installs by itself. Remove the ones you never open.",
                 [s["id"] for s in extra], "tab:store")
    cache = sum(b.get("cache_mb") or 0 for b in browsers)
    if cache >= 500:
        aggiungi("info", f"Browser caches: {cache / 1024:.1f} GB", "Clearing the cache frees space and fixes pages that load wrong. "
                 "Logins, passwords and history stay.", [], "tab:browsers")
    return consigli


# ---------- last use: UserAssist and Prefetch ----------

KNOWN_FOLDERS = {
    "{6d809377-6af0-444b-8957-a3773f02200e}": "%ProgramFiles%",
    "{7c5a40ef-a0fb-4bfc-874a-c0f2e0b9fa8e}": "%ProgramFiles(x86)%",
    "{f38bf404-1d43-42f2-9305-67de0b28fc23}": "%SystemRoot%",
    "{1ac14e77-02e7-4e5d-b744-2eb1ae5198b7}": "%SystemRoot%\\System32",
    "{d65231b0-b2f1-4857-a4ce-a8e7c6ea7d27}": "%SystemRoot%\\SysWOW64",
    "{f1b32785-6fba-4fcf-9d55-7b8e7f157091}": "%LOCALAPPDATA%",
    "{3eb685db-65f9-4cf6-a03a-e3ef65729f3d}": "%APPDATA%",
    "{62ab5d82-fdc1-4dc3-a9dd-070d1d495d97}": "%ProgramData%",
    "{374de290-123f-4565-9164-39c4925e467b}": "%USERPROFILE%\\Downloads",
    "{b4bfcc3a-db2c-424c-b029-7fe99a87c641}": "%USERPROFILE%\\Desktop",
}
USERASSIST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"


def filetime_date(valore: int) -> Optional[str]:
    if valore <= 0:
        return None
    try:
        return (datetime(1601, 1, 1) + timedelta(microseconds=valore // 10)).strftime("%Y-%m-%d")
    except OverflowError:
        return None


def parse_userassist(nome: str, dato) -> Optional[Tuple[str, str]]:
    """One UserAssist value (ROT13 name, 72-byte record) -> (program path or Store app id, last run date)."""
    if not isinstance(dato, bytes) or len(dato) < 68:
        return None
    quando = filetime_date(int.from_bytes(dato[60:68], "little"))
    if not quando:
        return None
    percorso = codecs.decode(nome, "rot13")
    trovato = re.match(r"(\{[0-9a-fA-F\-]{36}\})(.*)", percorso)
    if trovato and trovato.group(1).lower() in KNOWN_FOLDERS:
        percorso = os.path.expandvars(KNOWN_FOLDERS[trovato.group(1).lower()]) + trovato.group(2)
    return percorso.lower(), quando


def userassist() -> Dict[str, str]:
    """Programs started from Start, the taskbar or Explorer by this user -> last run date."""
    import winreg
    visti: Dict[str, str] = {}
    try:
        radice = winreg.OpenKey(winreg.HKEY_CURRENT_USER, USERASSIST_KEY)
    except OSError:
        return visti
    with radice:
        indice = 0
        while True:
            try:
                guid = winreg.EnumKey(radice, indice)
            except OSError:
                break
            indice += 1
            for nome, dato in inventory._values("HKCU", USERASSIST_KEY + "\\" + guid + "\\Count").items():
                voce = parse_userassist(nome, dato)
                if voce and voce[1] > visti.get(voce[0], ""):
                    visti[voce[0]] = voce[1]
    return visti


def prefetch() -> Dict[str, str]:
    """Program file name -> last run, from C:\\Windows\\Prefetch (readable by administrators only)."""
    visti: Dict[str, str] = {}
    try:
        voci = list(os.scandir(os.path.expandvars(r"%SystemRoot%\Prefetch")))
    except OSError:
        return visti
    for voce in voci:
        trovato = re.match(r"(.+?)-[0-9A-F]{8}\.pf$", voce.name, re.I)
        if trovato:
            try:
                quando = datetime.fromtimestamp(voce.stat().st_mtime).strftime("%Y-%m-%d")
            except OSError:
                continue
            nome = trovato.group(1).lower()
            if quando > visti.get(nome, ""):
                visti[nome] = quando
    return visti


def _exe(comando: str) -> str:
    """The program of a command line or icon path: '"C:\\a b\\x.exe" /S' or 'C:\\x.exe,0' -> 'C:\\x.exe'."""
    testo = (comando or "").strip()
    if testo.startswith('"'):
        return testo[1:].split('"', 1)[0]
    trovato = re.match(r"(.+?\.exe)\b", testo, re.I)
    return trovato.group(1) if trovato else testo.split(",")[0]


def install_folder(valori: dict) -> str:
    """Where the program lives: InstallLocation, else the folder of its icon or uninstaller (never Windows or installer caches)."""
    for candidato in (valori.get("InstallLocation"), os.path.dirname(_exe(str(valori.get("DisplayIcon") or ""))),
                      os.path.dirname(_exe(str(valori.get("UninstallString") or "")))):
        cartella = str(candidato or "").strip().strip('"').rstrip("\\")
        basso = cartella.lower()
        if cartella and os.path.isabs(cartella) and basso.count("\\") >= 2 \
                and not re.search(r"\\windows(\\|$)|\\installer|package cache|\\temp\\|\{[0-9a-f\-]{36}\}", basso):
            return cartella
    return ""


def _programs_in(cartella: str, limite: int = 300) -> List[str]:
    """Program files in a folder and two levels of subfolders, lower case names."""
    trovati: List[str] = []
    pila = [(cartella, 0)]
    while pila and len(trovati) < limite:
        percorso, livello = pila.pop()
        try:
            voci = list(os.scandir(percorso))
        except OSError:
            continue
        for voce in voci:
            try:
                if voce.is_dir(follow_symlinks=False) and livello < 2:
                    pila.append((voce.path, livello + 1))
                elif voce.name.lower().endswith(".exe"):
                    trovati.append(voce.name.lower())
            except OSError:
                continue
    return trovati


# Shortcut names that start a program with another name.
ALIASES = {"microsoft office": ("word", "excel", "powerpoint", "outlook", "onenote", "access", "publisher")}


def shortcut_names(eseguiti: Dict[str, str]) -> Dict[str, str]:
    """Start menu and taskbar shortcuts the user opened ('steam', 'hue sync') -> last run date."""
    nomi: Dict[str, str] = {}
    for percorso, quando in eseguiti.items():
        if percorso.endswith(".lnk"):
            nome = os.path.basename(percorso)[:-4].strip()
            if len(nome) >= 3 and quando > nomi.get(nome, ""):
                nomi[nome] = quando
    return nomi


def running_paths() -> List[str]:
    """Program paths of the processes running now (the ones this account may query)."""
    import ctypes
    from ctypes import wintypes
    from .processes import image_path
    pid = (wintypes.DWORD * 4096)()
    usati = wintypes.DWORD()
    if not ctypes.windll.psapi.EnumProcesses(ctypes.byref(pid), ctypes.sizeof(pid), ctypes.byref(usati)):
        return []
    percorsi = set()
    for indice in range(usati.value // ctypes.sizeof(wintypes.DWORD)):
        try:
            percorso = image_path(pid[indice])
        except OSError:
            continue
        if percorso:
            percorsi.add(percorso.lower())
    return sorted(percorsi)


def last_used(app: dict, eseguiti: Dict[str, str], pf: Dict[str, str], scorciatoie: Dict[str, str], attivi: List[str], oggi: date) -> Optional[str]:
    """Latest of: running now, a recorded start of a program in its folder, a Start menu shortcut with its name."""
    date_: List[str] = []
    cartella = app.get("folder") or ""
    if cartella:
        prefisso = cartella.lower().rstrip("\\") + "\\"
        if any(p.startswith(prefisso) for p in attivi):
            return oggi.isoformat()
        date_ += [quando for percorso, quando in eseguiti.items() if percorso.startswith(prefisso)]
        if pf:
            date_ += [pf[nome] for nome in _programs_in(cartella) if nome in pf]
    nome = app["name"].lower()
    base = base_name(app["name"])
    alias = next((v for k, v in ALIASES.items() if nome.startswith(k)), ())
    for scorciatoia, quando in scorciatoie.items():
        radice = base_name(scorciatoia)
        if radice and (radice == base or (len(radice) >= 4 and nome.startswith(radice)) or radice in alias):
            date_.append(quando)
    return max(date_) if date_ else None


# ---------- installed programs ----------

def app_id(hive: str, chiave: str) -> str:
    return hashlib.sha1(f"{hive}\\{chiave}".lower().encode("utf-8")).hexdigest()[:16]


def uninstall_command(valori: dict) -> str:
    """The command that removes the program. MSI products get /X (remove) instead of /I (change)."""
    comando = str(valori.get("QuietUninstallString") or valori.get("UninstallString") or "").strip()
    trovato = re.match(r"msiexec(?:\.exe)?\s+/[ix]\s*(\{[0-9A-Fa-f\-]{36}\})", comando, re.I)
    if trovato:
        return f"MsiExec.exe /X{trovato.group(1)}"
    return comando


def is_broken(comando: str) -> bool:
    """True when the uninstaller file no longer exists (MSI and system commands are never broken)."""
    programma = _exe(comando)
    if not programma or not os.path.isabs(programma) or re.match(r"(?i)(msiexec|rundll32|cmd|powershell)(\.exe)?$", os.path.basename(programma)):
        return False
    return not os.path.exists(os.path.expandvars(programma))


def read_installed() -> List[dict]:
    """Programs from the three Uninstall keys, with what the page needs to act on them."""
    import winreg
    programmi: Dict[str, dict] = {}
    for hive, chiave in inventory.UNINSTALL_KEYS:
        try:
            radice = winreg.OpenKey(inventory._hive(hive), chiave, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
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
                valori = inventory._values(hive, chiave + "\\" + sotto)
                voce = inventory.parse_uninstall_entry(valori)
                if not voce:
                    continue
                comando = uninstall_command(valori)
                voce.update({
                    "id": app_id(hive, chiave + "\\" + sotto), "key": f"{hive}\\{chiave}\\{sotto}", "scope": "user" if hive == "HKCU" else "machine",
                    "uninstall": comando, "quiet": bool(valori.get("QuietUninstallString")) or comando.startswith("MsiExec.exe /X"),
                    "folder": install_folder(valori), "broken": bool(comando) and is_broken(comando),
                    "url": str(valori.get("URLInfoAbout") or valori.get("HelpLink") or ""),
                })
                programmi.setdefault(f"{voce['name']}|{voce['version']}", voce)
    return sorted(programmi.values(), key=lambda a: a["name"].lower())


# ---------- Store apps ----------

SCRIPT_STORE = r"""
@(Get-AppxPackage -PackageTypeFilter Main -ErrorAction SilentlyContinue | Where-Object { -not $_.IsFramework -and $_.SignatureKind -eq 'Store' -and -not $_.NonRemovable } | ForEach-Object {
  $name = $_.Name; $pub = ''
  try {
    [xml]$m = Get-Content -LiteralPath (Join-Path $_.InstallLocation 'AppxManifest.xml') -ErrorAction Stop
    $d = "$($m.Package.Properties.DisplayName)"; if ($d -and $d -notlike 'ms-resource*') { $name = $d }
    $p = "$($m.Package.Properties.PublisherDisplayName)"; if ($p -notlike 'ms-resource*') { $pub = $p }
  } catch { }
  $when = try { (Get-Item -LiteralPath $_.InstallLocation -ErrorAction Stop).CreationTime.ToString('yyyy-MM-dd') } catch { $null }
  [ordered]@{ package = $_.PackageFullName; family = $_.PackageFamilyName; id_name = $_.Name; name = $name; publisher = $pub; version = "$($_.Version)"; installed = $when }
}) | ConvertTo-Json -Depth 3 -Compress
"""
# Store apps Windows installs by itself (STORE_BLOAT, in the rules): removing them is safe, the Store can reinstall them.


def store_label(nome: str) -> str:
    """'Microsoft.WindowsCalculator' -> 'Windows Calculator': a readable name when the manifest only has a resource id."""
    if not re.match(r"Microsoft(?:CorporationII)?\.", nome):
        return nome.rsplit(".", 1)[-1] or nome  # 'Clipchamp.Clipchamp' -> 'Clipchamp': other publishers keep their spelling
    testo = nome.split(".", 1)[1].replace(".", " ")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", testo).strip() or nome


def parse_store(raw, eseguiti: Dict[str, str]) -> List[dict]:
    voci = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    app = []
    for voce in voci:
        pacchetto = str(voce.get("package") or "")
        if not re.fullmatch(r"[\w.\-~]{3,200}", pacchetto):
            continue
        famiglia = str(voce.get("family") or "").lower()
        usi = [q for p, q in eseguiti.items() if famiglia and p.startswith(famiglia + "!")]
        nome = str(voce.get("name") or voce.get("id_name") or "")
        if nome == voce.get("id_name"):
            nome = store_label(nome)
        app.append({
            "id": hashlib.sha1(pacchetto.encode("utf-8")).hexdigest()[:16], "package": pacchetto, "name": nome, "publisher": str(voce.get("publisher") or ""),
            "version": str(voce.get("version") or ""), "installed": voce.get("installed"), "last_used": max(usi) if usi else None,
            "bloat": bool(re.search(STORE_BLOAT, f"{voce.get('id_name')} {voce.get('name')}".lower())),
        })
    return sorted(app, key=lambda a: a["name"].lower())


# ---------- browser caches ----------

# (id, name, process, profile folders). Chromium browsers keep the cache inside each profile.
BROWSER_PROFILES = [
    ("chrome", "Google Chrome", "chrome.exe", [r"%LOCALAPPDATA%\Google\Chrome\User Data\*"]),
    ("edge", "Microsoft Edge", "msedge.exe", [r"%LOCALAPPDATA%\Microsoft\Edge\User Data\*"]),
    ("brave", "Brave", "brave.exe", [r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\*"]),
    ("vivaldi", "Vivaldi", "vivaldi.exe", [r"%LOCALAPPDATA%\Vivaldi\User Data\*"]),
    ("opera", "Opera", "opera.exe", [r"%LOCALAPPDATA%\Opera Software\Opera Stable", r"%LOCALAPPDATA%\Opera Software\Opera GX Stable"]),
    ("firefox", "Mozilla Firefox", "firefox.exe", [r"%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*"]),
]
CHROMIUM_CACHE = ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
                  r"Service Worker\CacheStorage", r"Service Worker\ScriptCache")
SHARED_CACHE = ("ShaderCache", "GrShaderCache", "GraphiteDawnCache")


def cache_folders(browser_id: str) -> List[str]:
    """Only cache folders: cookies, passwords, history and settings are never touched."""
    voce = next(b for b in BROWSER_PROFILES if b[0] == browser_id)
    if browser_id == "firefox":
        return expand([p + r"\cache2" for p in voce[3]] + [p + r"\startupCache" for p in voce[3]])
    modelli = [p + "\\" + c for p in voce[3] for c in CHROMIUM_CACHE]
    modelli += [p[:-2] + "\\" + c for p in voce[3] if p.endswith("\\*") for c in SHARED_CACHE]
    return expand(modelli)


def running_programs() -> set:
    try:
        uscita = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {riga.split('","')[0].strip('"').lower() for riga in uscita.splitlines() if riga.startswith('"')}


def browser_caches() -> List[dict]:
    attivi = running_programs()
    elenco = []
    for browser_id, nome, processo, cartelle in BROWSER_PROFILES:
        if not expand(cartelle):
            continue
        totale, file, _ = wipe([(c, None) for c in cache_folders(browser_id)], preview=True)
        elenco.append({"id": browser_id, "name": nome, "cache_mb": round(totale / 1024 ** 2, 1), "files": file, "running": processo in attivi})
    return elenco


def clean_browser(browser_id: str) -> dict:
    if browser_id not in {b[0] for b in BROWSER_PROFILES}:
        raise ValueError("Unknown browser.")
    totale, file, saltati = wipe([(c, None) for c in cache_folders(browser_id)], preview=False)
    return {"freed_mb": round(totale / 1024 ** 2, 1), "files": file, "skipped": saltati}


# ---------- setup files left in Downloads ----------

def leftover_installers(giorni: int = 30) -> dict:
    """Installers downloaded more than a month ago: the program is installed, the file only takes space."""
    cartella = os.path.join(os.path.expanduser("~"), "Downloads")
    limite = time.time() - giorni * 86400
    file = []
    try:
        voci = list(os.scandir(cartella))
    except OSError:
        voci = []
    for voce in voci:
        if re.search(r"\.(exe|msi|msix|msixbundle|appx)$", voce.name, re.I):
            try:
                info = voce.stat()
            except OSError:
                continue
            if info.st_mtime < limite:
                file.append({"name": voce.name, "mb": round(info.st_size / 1024 ** 2, 1),
                             "date": datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d")})
    file.sort(key=lambda f: -f["mb"])
    return {"folder": cartella, "files": file[:50], "count": len(file), "mb": round(sum(f["mb"] for f in file), 1)}


# ---------- scan ----------

def scan(ctx, oggi: Optional[date] = None) -> dict:
    oggi = oggi or date.today()
    errori: List[str] = []
    eseguiti = userassist()
    pf = prefetch()
    try:
        programmi = read_installed()
    except OSError as errore:
        programmi = []
        errori.append(f"Installed programs: {errore}")
    avvio = " ".join(f"{v['name']} {v['command']}".lower() for v in inventory.startup_items() if v["enabled"])
    scorciatoie = shortcut_names(eseguiti)
    attivi = running_paths()
    for app in programmi:
        app["category"] = category(app)
        app["startup"] = bool(app["folder"]) and app["folder"].lower() in avvio
        app["last_used"] = oggi.isoformat() if app["startup"] else last_used(app, eseguiti, pf, scorciatoie, attivi, oggi)
        app["issues"] = assess(app, oggi)
        app["status"] = status(app["issues"])
        app.update(usage(app, oggi, completo=bool(pf) and bool(app["folder"])))
        app["removable"] = removable(app)
    store = parse_store(_powershell(ctx, SCRIPT_STORE, errori, "Store apps", timeout=120), eseguiti)
    for app in store:
        app.update(usage(app, oggi, completo=False))
    browsers = browser_caches()
    return {
        "apps": programmi, "store": store, "browsers": browsers, "installers": leftover_installers(),
        "suggestions": suggestions(programmi, store, browsers), "errors": errori,
        "usage_source": "UserAssist and Prefetch" if pf else "UserAssist only (run as administrator to also read Prefetch)",
        "winget": bool(shutil.which("winget")), "scanned": datetime.now().isoformat(timespec="seconds"),
        "rules": dict(RULES_INFO),
    }


# ---------- changes (the API wraps each one in _logged_change) ----------

# Uninstallers started by this agent, by process id: the page asks whether they are still running.
RUNNING: Dict[int, subprocess.Popen] = {}


def run_uninstaller(app: dict) -> dict:
    """Starts the program's own uninstaller and returns: its window guides the user, the page waits for it to end."""
    comando = app.get("uninstall") or ""
    if not comando:
        raise ValueError("This program has no uninstaller.")
    if comando.startswith("MsiExec.exe /X"):
        processo = subprocess.Popen(["msiexec.exe", "/x", comando[len("MsiExec.exe /X"):], "/qb", "/norestart"])
    else:
        processo = subprocess.Popen(comando)  # a Windows command line: CreateProcess parses it like Settings > Apps does
    RUNNING[processo.pid] = processo
    return {"started": comando, "pid": processo.pid}


def is_running(pid: Optional[int]) -> bool:
    processo = RUNNING.get(pid or 0)
    if processo is None:
        return False
    if processo.poll() is None:
        return True
    RUNNING.pop(pid, None)
    return False


# ---------- leftovers after an uninstall ----------

# Folder and key names shared by many programs: never offered as leftovers of one of them.
SHARED_NAMES = {
    "microsoft", "windows", "google", "intel", "nvidia", "nvidia corporation", "amd", "realtek", "common files", "packages", "temp",
    "programs", "installer", "package cache", "microsoft shared", "classes", "policies", "wow6432node", "apple", "adobe", "mozilla",
    "oracle", "java", "python", "steam", "valve", "default", "public", "users", "system32", "crashdumps", "d3dscache", "connecteddevicesplatform",
}
LEFTOVER_ROOTS = ("%ProgramFiles%", "%ProgramFiles(x86)%", "%ProgramData%", "%APPDATA%", "%LOCALAPPDATA%")


def _names(app: dict) -> List[str]:
    """Folder names that belong to this program only: 'VLC media player 3.0.18' -> ['vlc media player', 'vlc'].
    The first word alone is skipped when it is the publisher ('CPUID CPU-Z': CPUID makes other programs too)."""
    nomi = []
    base = base_name(app.get("name") or "")
    editore = (re.findall(r"\w+", (app.get("publisher") or "").lower()) or [""])[0]
    primo = base.split(" ")[0] if base else ""
    for candidato in (base, "" if primo == editore else primo):
        if len(candidato) >= 3 and candidato not in SHARED_NAMES and candidato not in nomi:
            nomi.append(candidato)
    return nomi


def leftover_folders(app: dict) -> List[str]:
    nomi = _names(app)
    editore = (app.get("publisher") or "").lower().strip()
    trovate: List[str] = []
    cartella = app.get("folder") or ""
    if cartella and os.path.isdir(cartella) and safe_leftover(cartella):
        trovate.append(cartella)
    for radice in (os.path.expandvars(r) for r in LEFTOVER_ROOTS):
        if "%" in radice or not os.path.isdir(radice):
            continue
        try:
            voci = {v.name.lower(): v.path for v in os.scandir(radice) if v.is_dir(follow_symlinks=False)}
        except OSError:
            continue
        for nome in nomi:
            if nome in voci:
                trovate.append(voci[nome])
        # Publisher\Program, e.g. VideoLAN\VLC: only the program folder, never the publisher one.
        if editore and editore in voci and editore not in SHARED_NAMES:
            try:
                sotto = {v.name.lower(): v.path for v in os.scandir(voci[editore]) if v.is_dir(follow_symlinks=False)}
            except OSError:
                sotto = {}
            trovate += [sotto[n] for n in nomi if n in sotto]
    unici: List[str] = []
    for percorso in trovate:
        if percorso.lower() not in (u.lower() for u in unici) and safe_leftover(percorso):
            unici.append(percorso)
    return unici


def safe_leftover(percorso: str) -> bool:
    """Only a folder inside one of the program roots, never a root itself, a link or a Windows folder."""
    pieno = os.path.normcase(os.path.abspath(percorso))
    radici = [os.path.normcase(os.path.abspath(os.path.expandvars(r))) for r in LEFTOVER_ROOTS if "%" not in os.path.expandvars(r)]
    if not any(pieno.startswith(r + os.sep) for r in radici) or os.path.basename(pieno) in SHARED_NAMES:
        return False
    try:
        info = os.lstat(percorso)
    except OSError:
        return False
    return not (getattr(info, "st_file_attributes", 0) & 0x400)  # no junctions or symbolic links


def leftover_keys(app: dict) -> List[str]:
    import winreg
    nomi = _names(app)
    editore = (app.get("publisher") or "").strip()
    trovate = []
    for hive, radice in (("HKCU", "Software"), ("HKLM", "SOFTWARE"), ("HKLM", r"SOFTWARE\WOW6432Node")):
        candidati = [n for n in nomi] + ([editore.lower() + "\\" + n for n in nomi] if editore and editore.lower() not in SHARED_NAMES else [])
        for nome in candidati:
            try:
                with winreg.OpenKey(inventory._hive(hive), radice + "\\" + nome, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                    trovate.append(hive + "\\" + radice + "\\" + nome)
            except OSError:
                continue
    return trovate


def leftovers(app: dict, others: Iterable[dict] = ()) -> List[dict]:
    """What the uninstaller left: folders (sent to the Recycle Bin) and registry keys (deleted with a backup).
    Nothing that another installed program still uses: its folder, a folder holding it, or a name it shares."""
    altri = [o for o in others if o.get("id") != app.get("id")]
    cartelle_altri = [os.path.normcase(o["folder"]).rstrip("\\") + "\\" for o in altri if o.get("folder")]
    nomi_altri = {n for o in altri for n in _names(o)}

    def libera(percorso: str) -> bool:
        pieno = os.path.normcase(percorso).rstrip("\\") + "\\"
        return not any(c.startswith(pieno) or pieno.startswith(c) for c in cartelle_altri)

    elenco = []
    for percorso in [p for p in leftover_folders(app) if libera(p)]:
        elenco.append({"id": hashlib.sha1(percorso.lower().encode("utf-8")).hexdigest()[:12], "kind": "folder", "path": percorso,
                       "size_mb": folder_size(percorso, 5.0)})
    for chiave in leftover_keys(app):
        if chiave.rsplit("\\", 1)[-1] in nomi_altri:
            continue
        elenco.append({"id": hashlib.sha1(chiave.lower().encode("utf-8")).hexdigest()[:12], "kind": "key", "path": chiave, "size_mb": None})
    return elenco


def recycle(percorso: str) -> None:
    """To the Recycle Bin, so a wrong guess can be put back from there."""
    if not safe_leftover(percorso):
        raise ValueError(f"{percorso} is not a program folder that can be removed.")
    testo = percorso.replace("'", "''")
    risultato = subprocess.run(powershell_command(
        "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('" + testo +
        "', 'OnlyErrorDialogs', 'SendToRecycleBin')"), capture_output=True, text=True, timeout=600)
    if risultato.returncode != 0 or os.path.isdir(percorso):
        raise OSError((risultato.stderr or "").strip()[-300:] or f"{percorso} is still there (files in use?)")


def remove_store_app(pacchetto: str) -> dict:
    if not re.fullmatch(r"[\w.\-~]{3,200}", pacchetto):
        raise ValueError("Invalid package name.")
    risultato = subprocess.run(powershell_command(f"Remove-AppxPackage -Package '{pacchetto}' -ErrorAction Stop"),
                               capture_output=True, text=True, timeout=300)
    if risultato.returncode != 0:
        raise OSError((risultato.stderr or risultato.stdout).strip()[-400:] or "Remove-AppxPackage failed")
    return {"removed": pacchetto}


def folder_size(cartella: str, secondi: float = 10.0) -> Optional[float]:
    """Size of an install folder in MB; stops after `secondi` so a huge folder never blocks the page."""
    if not cartella or not os.path.isdir(cartella):
        return None
    inizio, totale = time.monotonic(), 0
    for _, peso in _files(cartella, None):
        totale += peso
        if time.monotonic() - inizio > secondi:
            break
    return round(totale / 1024 ** 2, 1)


def parse_winget_upgrade(testo: str) -> List[dict]:
    """The table of 'winget upgrade' -> [{name, id, version, available}]. Columns come from the header above the
    dashed line, so it works in every language."""
    righe = [r.rstrip() for r in testo.replace("\r", "\n").split("\n")]
    for indice, riga in enumerate(righe):
        if indice > 0 and re.fullmatch(r"-{20,}", riga.strip()):
            intestazione = righe[indice - 1]
            break
    else:
        return []
    inizi = [m.start() for m in re.finditer(r"(?:(?<=\s)|^)\S", intestazione)]
    if len(inizi) < 4:
        return []
    risultato = []
    for riga in righe[indice + 1:]:
        if not riga.strip() or len(riga) < inizi[3]:
            break
        campi = [riga[inizi[i]:inizi[i + 1] if i + 1 < len(inizi) else None].strip() for i in range(len(inizi))]
        if re.fullmatch(r"[\w.\-+]{2,128}", campi[1]):
            risultato.append({"name": campi[0].rstrip("\u2026").strip(), "id": campi[1], "version": campi[2], "available": campi[3]})
    return risultato


def winget_updates(timeout: int = 120) -> List[dict]:
    winget = shutil.which("winget")
    if not winget:
        raise OSError("winget is not available: install App Installer from the Microsoft Store.")
    uscita = subprocess.run([winget, "upgrade", "--accept-source-agreements", "--disable-interactivity"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout).stdout
    return parse_winget_upgrade(uscita)


def winget_upgrade(package_id: str, timeout: int = 1800) -> dict:
    if not re.fullmatch(r"[\w.\-+]{2,128}", package_id):
        raise ValueError("Invalid winget package id.")
    winget = shutil.which("winget")
    if not winget:
        raise OSError("winget is not available.")
    risultato = subprocess.run([winget, "upgrade", "--id", package_id, "-e", "--silent", "--accept-source-agreements",
                                "--accept-package-agreements", "--disable-interactivity"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    uscita = (risultato.stdout or "") + (risultato.stderr or "")
    if risultato.returncode != 0:
        raise OSError(f"winget ended with code {risultato.returncode}: " + uscita.strip()[-400:])
    return {"output": uscita[-2000:]}


load_rules()
