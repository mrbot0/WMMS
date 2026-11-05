"""Who slows the startup (2.8). Windows times every boot and names the programs, drivers and services that made it
slower (Diagnostics-Performance log: event 100 for the boot, 101 for programs, 102 for drivers, 103 for services). This
reads them, shows the boot time over time and ranks the culprits by the seconds they cost. The startup programs among
them can be turned off from the page (and on again: the toggle of Startup & Apps, recorded in History). Read-only."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from ottimizza_pc import Esito, Stato

from .crashes import as_list, parse_time, run_json

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @(Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-Diagnostics-Performance/Operational'; Id = 100, 101, 102, 103 } -MaxEvents 600 |
  ForEach-Object {
    $d = @{}
    foreach ($x in ([xml]$_.ToXml()).Event.EventData.Data) { $d[$x.Name] = "$($x.'#text')" }
    [ordered]@{ id = $_.Id; at = $_.TimeCreated.ToString('s'); data = $d }
  })
[ordered]@{ events = $out } | ConvertTo-Json -Depth 5 -Compress
"""
KINDS = {101: "program", 102: "driver", 103: "service"}


def _ms(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def read(runner: Optional[Callable[[], str]] = None) -> dict:
    avvii, colpevoli = [], []
    for e in as_list(run_json(SCRIPT, runner).get("events")):
        if not isinstance(e, dict) or not isinstance(e.get("data"), dict):
            continue
        d, quando = e["data"], str(e.get("at") or "")
        if e.get("id") == 100:
            totale = _ms(d.get("BootTime"))
            if totale:
                avvii.append({"at": quando, "total_ms": totale, "main_ms": _ms(d.get("MainPathBootTime")), "post_ms": _ms(d.get("BootPostBootTime"))})
        elif e.get("id") in KINDS:
            nome = str(d.get("Name") or d.get("FileName") or "")[:200]
            if not nome:
                continue
            colpevoli.append({"at": quando, "kind": KINDS[e["id"]], "name": nome, "friendly": str(d.get("FriendlyName") or "")[:120],
                              "total_ms": _ms(d.get("TotalTime")) or 0, "degradation_ms": _ms(d.get("DegradationTime")) or 0})
    avvii.sort(key=lambda a: a["at"])
    return {"boots": avvii, "culprits": colpevoli}


def _key(nome: str) -> str:
    return os.path.basename(nome.replace("/", "\\")).lower()


def analyze(dati: dict, startup: Optional[List[dict]] = None, now: Optional[datetime] = None, days: int = 90) -> dict:
    """Boot time trend and the culprits of the last `days` days, with the startup entry that starts each program."""
    adesso = now or datetime.now()
    limite = adesso - timedelta(days=days)
    avvii = [a for a in dati["boots"] if (parse_time(a["at"]) or limite) >= limite]
    secondi = [a["total_ms"] / 1000 for a in avvii]
    meta = len(secondi) // 2
    prima = sum(secondi[:meta]) / meta if meta else None
    dopo = sum(secondi[meta:]) / (len(secondi) - meta) if len(secondi) - meta > 0 else None
    gruppi: Dict[str, dict] = {}
    for c in dati["culprits"]:
        if (parse_time(c["at"]) or limite) < limite:
            continue
        g = gruppi.setdefault(f"{c['kind']}:{_key(c['name'])}", {"kind": c["kind"], "name": c["name"], "friendly": c["friendly"],
                                                                 "times": 0, "lost_seconds": 0.0, "last": c["at"]})
        g["times"] += 1
        g["lost_seconds"] += c["degradation_ms"] / 1000
        g["last"] = max(g["last"], c["at"])
        g["friendly"] = g["friendly"] or c["friendly"]
    voci = startup or []
    for g in gruppi.values():
        g["lost_seconds"] = round(g["lost_seconds"], 1)
        g["average_seconds"] = round(g["lost_seconds"] / g["times"], 1) if g["times"] else 0
        chiave = _key(g["name"])
        trovata = next((v for v in voci if g["kind"] == "program" and chiave and chiave in str(v.get("command", "")).lower()), None)
        g["startup"] = {"id": trovata["id"], "name": trovata["name"], "enabled": trovata["enabled"], "location": trovata["location"]} if trovata else None
    elenco = sorted(gruppi.values(), key=lambda g: g["lost_seconds"], reverse=True)[:30]
    return {
        "boots": [{"at": a["at"], "seconds": round(a["total_ms"] / 1000, 1),
                   "main_seconds": round(a["main_ms"] / 1000, 1) if a["main_ms"] else None} for a in avvii][-60:],
        "count": len(avvii), "last_seconds": round(secondi[-1], 1) if secondi else None,
        "average_seconds": round(sum(secondi) / len(secondi), 1) if secondi else None,
        "earlier_average": round(prima, 1) if prima else None, "recent_average": round(dopo, 1) if dopo else None,
        "slower": bool(prima and dopo and dopo > prima * 1.25 and dopo - prima > 5), "culprits": elenco, "days": days,
    }


def startup_entries() -> List[dict]:
    try:
        from .inventory import startup_items
        return startup_items()
    except Exception:  # noqa: BLE001 - the ranking is useful without the startup match
        return []


def slow_boot(ctx) -> Esito:
    dati = analyze(read(), startup_entries())
    if not dati["count"]:
        ctx.scrivi("No boot timing found: the Diagnostics-Performance log is empty or needs administrator rights.")
        return Esito(Stato.AVVISO, "no boot timing available")
    ctx.scrivi(f"{dati['count']} boots in {dati['days']} days, average {dati['average_seconds']} s, last {dati['last_seconds']} s")
    if dati["slower"]:
        ctx.scrivi(f"The startup got slower: from {dati['earlier_average']} s to {dati['recent_average']} s on average.")
    for g in dati["culprits"][:12]:
        ctx.scrivi(f"  {g['lost_seconds']:>6} s lost  {g['kind']:<8} {g['friendly'] or g['name']}  ({g['times']} times)"
                   + ("  [startup entry: " + g["startup"]["name"] + "]" if g["startup"] else ""))
    nota = f"average boot {dati['average_seconds']} s"
    return Esito(Stato.AVVISO if dati["slower"] else Stato.OK, nota + (", getting slower" if dati["slower"] else ""))
