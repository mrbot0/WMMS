"""Fast event viewer over wevtutil (stdlib only): presets for critical Windows errors, hardware,
applications and services, plus filters by log, level, time, source and event ID.

Every filter is validated before it reaches the XPath query, so no text from the browser is ever
interpreted by wevtutil."""
from __future__ import annotations

import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence, Tuple

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
LOGS: Dict[str, str] = {
    "System": "System",
    "Application": "Application",
    "Setup": "Setup",
    "Security": "Security",
    "Defender": "Microsoft-Windows-Windows Defender/Operational",
    "WindowsUpdate": "Microsoft-Windows-WindowsUpdateClient/Operational",
    "Boot": "Microsoft-Windows-Diagnostics-Performance/Operational",
    "TaskScheduler": "Microsoft-Windows-TaskScheduler/Operational",
    "PowerShell": "Microsoft-Windows-PowerShell/Operational",
}
LEVELS = {1: "critical", 2: "error", 3: "warning", 4: "information", 5: "verbose"}
HARDWARE_PROVIDERS = (
    "Microsoft-Windows-WHEA-Logger", "Microsoft-Windows-Kernel-Power", "disk", "Ntfs", "volmgr", "storahci", "stornvme",
    "Microsoft-Windows-StorPort", "Microsoft-Windows-Disk", "Microsoft-Windows-Ntfs", "nvlddmkm", "amdkmdag", "igfx", "Display",
    "Microsoft-Windows-Kernel-Processor-Power", "Microsoft-Windows-Resource-Exhaustion-Detector", "BTHUSB", "USBHUB3",
    "Microsoft-Windows-Kernel-PnP", "Microsoft-Windows-Kernel-Boot", "EventLog",
)
APPLICATION_PROVIDERS = ("Application Error", "Application Hang", ".NET Runtime", "Windows Error Reporting", "MsiInstaller",
                         "SideBySide", "Microsoft-Windows-RestartManager", "Microsoft-Windows-AppModel-Runtime")
PRESETS: Dict[str, dict] = {
    "critical": {"title": "Critical and errors", "logs": ["System", "Application"], "levels": [1, 2]},
    "hardware": {"title": "Hardware", "logs": ["System"], "levels": [1, 2, 3], "providers": list(HARDWARE_PROVIDERS)},
    "applications": {"title": "Applications", "logs": ["Application"], "levels": [1, 2, 3], "providers": list(APPLICATION_PROVIDERS)},
    "services": {"title": "Services", "logs": ["System"], "levels": [1, 2, 3], "providers": ["Service Control Manager"]},
    "security": {"title": "Security and Defender", "logs": ["Defender", "Security"], "levels": [1, 2, 3]},
    "all": {"title": "Everything", "logs": ["System", "Application"], "levels": [1, 2, 3, 4]},
}
SAFE_PROVIDER = re.compile(r"^[\w .\-/]{1,120}$")
MAX_EVENTS = 2000
CACHE_SECONDS = 8


class EventQueryError(ValueError):
    """A filter is not valid."""


def build_query(levels: Sequence[int], hours: Optional[float], providers: Sequence[str], event_id: Optional[int]) -> str:
    condizioni = []
    if levels:
        livelli = sorted(set(levels) | ({0} if 4 in levels else set()))  # level 0 is "information" for classic sources
        condizioni.append("(" + " or ".join(f"Level={int(n)}" for n in livelli) + ")")
    if hours:
        condizioni.append(f"TimeCreated[timediff(@SystemTime) <= {int(hours * 3600000)}]")
    if providers:
        condizioni.append("Provider[" + " or ".join(f"@Name='{p}'" for p in providers) + "]")
    if event_id is not None:
        condizioni.append(f"(EventID={int(event_id)})")
    return "*[System[" + " and ".join(condizioni) + "]]" if condizioni else "*"


def validate(params: dict) -> dict:
    """Turns query-string values into a checked filter; raises EventQueryError on bad input."""
    preset = PRESETS.get(params.get("preset") or "critical")
    if preset is None:
        raise EventQueryError("Unknown preset.")
    logs = [x for x in (params.get("logs") or ",".join(preset["logs"])).split(",") if x]
    if not logs or any(l not in LOGS for l in logs):
        raise EventQueryError("Unknown log. Known logs: " + ", ".join(LOGS))
    try:
        livelli = [int(x) for x in (params.get("levels") or ",".join(map(str, preset["levels"]))).split(",") if x]
        ore = float(params.get("hours") or 168)
        limite = int(params.get("limit") or 500)
        evento = int(params["id"]) if params.get("id") else None
    except ValueError:
        raise EventQueryError("Levels, hours, limit and event ID must be numbers.") from None
    if any(n not in LEVELS for n in livelli) or not 0 < ore <= 24 * 90 or not 1 <= limite <= MAX_EVENTS or \
            (evento is not None and not 0 <= evento <= 65535):
        raise EventQueryError("Levels 1-5, up to 90 days, 1-2000 events, event ID 0-65535.")
    fonti = [x.strip() for x in (params.get("providers") or ",".join(preset.get("providers", []))).split(",") if x.strip()]
    if any(not SAFE_PROVIDER.match(p) for p in fonti) or len(fonti) > 40:
        raise EventQueryError("A source name contains characters that are not allowed.")
    return {"logs": logs, "levels": livelli, "hours": ore, "limit": limite, "id": evento, "providers": fonti}


def _text(nodo: Optional[ET.Element]) -> str:
    return (nodo.text or "").strip() if nodo is not None else ""


def parse(xml_text: str, log_key: str) -> List[dict]:
    """Rendered XML from wevtutil (a list of <Event> without a root) into plain dictionaries."""
    if not xml_text.strip():
        return []
    # wevtutil escapes event text, so a DTD can only mean tampered output: never parse it (no XXE, no entity bombs).
    if re.search(r"<!(DOCTYPE|ENTITY)", xml_text, re.IGNORECASE):
        raise ET.ParseError("unexpected DTD in the event log output")
    radice = ET.fromstring("<Events>" + xml_text + "</Events>")
    eventi = []
    for evento in radice.findall("e:Event", NS):
        sistema = evento.find("e:System", NS)
        if sistema is None:
            continue
        resa = evento.find("e:RenderingInfo", NS)
        fornitore = sistema.find("e:Provider", NS)
        tempo = sistema.find("e:TimeCreated", NS)
        esecuzione = sistema.find("e:Execution", NS)
        livello = int(_text(sistema.find("e:Level", NS)) or 0) or 4
        messaggio = _text(resa.find("e:Message", NS)) if resa is not None else ""
        if not messaggio:  # no message template: show the raw event data
            dati = evento.find("e:EventData", NS)
            messaggio = "; ".join(f"{d.get('Name') or 'data'}={(d.text or '').strip()}"
                                  for d in (dati if dati is not None else []) if (d.text or "").strip())
        eventi.append({
            "log": log_key,
            "time": tempo.get("SystemTime", "") if tempo is not None else "",
            "level": livello,
            "level_name": LEVELS.get(livello, "information"),
            "provider": (fornitore.get("EventSourceName") or fornitore.get("Name", "")) if fornitore is not None else "",
            "id": int(_text(sistema.find("e:EventID", NS)) or 0),
            "record": int(_text(sistema.find("e:EventRecordID", NS)) or 0),
            "task": _text(resa.find("e:Task", NS)) if resa is not None else "",
            "computer": _text(sistema.find("e:Computer", NS)),
            "pid": int(esecuzione.get("ProcessID", "0") or 0) if esecuzione is not None else 0,
            "message": messaggio.replace("\r\n", "\n").strip(),
        })
    return eventi


def _query_log(log_key: str, query: str, limit: int) -> Tuple[List[dict], Optional[str]]:
    comando = ["wevtutil", "qe", LOGS[log_key], f"/q:{query}", f"/c:{limit}", "/rd:true", "/f:RenderedXml"]
    try:
        risultato = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as errore:
        return [], f"{log_key}: {errore}"
    if risultato.returncode != 0:
        messaggio = risultato.stderr.decode("mbcs", "replace").strip() or f"exit code {risultato.returncode}"
        if risultato.returncode == 5 or "access" in messaggio.lower():
            messaggio = "administrator rights are needed to read this log"
        return [], f"{log_key}: {messaggio}"
    try:
        # Piped, wevtutil writes in the ANSI code page of the PC ("mbcs"), not UTF-8.
        return parse(risultato.stdout.decode("mbcs", "replace"), log_key), None
    except ET.ParseError as errore:
        return [], f"{log_key}: unreadable output ({errore})"


class EventReader:
    """Queries several logs in parallel and caches identical queries for a few seconds."""

    def __init__(self, runner=_query_log, clock=time.monotonic):
        self._runner = runner
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, dict]] = {}

    def query(self, params: dict, fresh: bool = False) -> dict:
        filtro = validate(params)
        chiave = repr(sorted(filtro.items()))
        with self._lock:
            trovato = self._cache.get(chiave)
            if trovato and not fresh and self._clock() - trovato[0] < CACHE_SECONDS:
                return trovato[1]
        inizio = time.perf_counter()
        xpath = build_query(filtro["levels"], filtro["hours"], filtro["providers"], filtro["id"])
        with ThreadPoolExecutor(max_workers=len(filtro["logs"])) as pool:
            risultati = list(pool.map(lambda log: self._runner(log, xpath, filtro["limit"]), filtro["logs"]))
        eventi = sorted((e for lista, _ in risultati for e in lista), key=lambda e: e["time"], reverse=True)[:filtro["limit"]]
        conteggi = {nome: 0 for nome in LEVELS.values()}
        for e in eventi:
            conteggi[e["level_name"]] += 1
        risposta = {"events": eventi, "counts": conteggi, "filter": filtro, "warnings": [w for _, w in risultati if w],
                    "elapsed_ms": int((time.perf_counter() - inizio) * 1000)}
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if self._clock() - v[0] < CACHE_SECONDS}
            self._cache[chiave] = (self._clock(), risposta)
        return risposta


def meta() -> dict:
    return {"logs": list(LOGS), "levels": LEVELS,
            "presets": {k: {"title": v["title"], "logs": v["logs"], "levels": v["levels"], "providers": v.get("providers", [])}
                        for k, v in PRESETS.items()}}
