"""Periodic report (2.8). A summary of the period since the last report, sent by e-mail or Telegram with the channels
of Settings › Notifications: the scores of the areas and how they moved, the fixes run with their checks, failures,
alerts, connection outages, suspicious changes, blue screens, growing failure signs and the disk and battery forecasts.
Schedule integrity.periodic_report every week or month; "Send now" sends it at once. In Italian or English."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from ottimizza_pc import Esito, Stato

from . import securestore
from . import notify

MAX_DAYS = 31
AREA_NAMES = {
    "it": {"cleanup": "Pulizia", "integrity": "Integrità del sistema", "services": "Servizi", "performance": "Prestazioni", "storage": "Archiviazione",
           "network": "Rete", "startup": "Avvio e app", "security": "Sicurezza", "updates": "Aggiornamenti e driver"},
    "en": {"cleanup": "Cleanup", "integrity": "System Integrity", "services": "Services", "performance": "Performance", "storage": "Storage",
           "network": "Network", "startup": "Startup & Apps", "security": "Security", "updates": "Updates & Drivers"},
}
TEXT = {
    "it": {"title": "Rapporto del PC {host}: {start} – {end}", "scores": "Punteggi", "overall": "Complessivo", "runs": "Interventi",
           "no_runs": "Nessun intervento nel periodo.", "ok": "riusciti", "warning": "con avvisi", "error": "falliti", "checked": "verificati",
           "fixed": "risolti", "not_fixed": "non risolti", "failed_list": "Falliti", "outages": "Cadute della connessione",
           "no_outages": "nessuna", "drift": "Modifiche sospette", "bsod": "Schermate blu", "signals": "Segni di guasto in crescita",
           "forecasts": "Previsioni", "alerts": "Avvisi inviati", "none": "nessuno", "free": "Spazio libero su C:", "footer":
           "Apri la console per i dettagli."},
    "en": {"title": "Report of PC {host}: {start} – {end}", "scores": "Scores", "overall": "Overall", "runs": "Fixes and reports",
           "no_runs": "Nothing ran in the period.", "ok": "ok", "warning": "with warnings", "error": "failed", "checked": "checked",
           "fixed": "fixed", "not_fixed": "not fixed", "failed_list": "Failed", "outages": "Connection outages", "no_outages": "none",
           "drift": "Suspicious changes", "bsod": "Blue screens", "signals": "Growing failure signs", "forecasts": "Forecasts",
           "alerts": "Alerts sent", "none": "none", "free": "Free space on C:", "footer": "Open the console for the details."},
}


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "digest.json"


def settings(data_dir: Path) -> dict:
    try:
        dati = json.loads(securestore.read_text(_path(data_dir)))
    except (OSError, ValueError):
        dati = {}
    return {"lang": dati.get("lang") if dati.get("lang") in TEXT else "it", "last_sent": dati.get("last_sent")}


def save_settings(data_dir: Path, lang) -> dict:
    if lang not in TEXT:
        raise ValueError("Language: it or en.")
    dati = settings(data_dir)
    dati["lang"] = lang
    securestore.write_text(_path(data_dir), json.dumps(dati), encoding="utf-8")
    return dati


def _since(dati: dict, adesso: datetime) -> datetime:
    try:
        inizio = datetime.fromisoformat(dati["last_sent"])
    except (KeyError, TypeError, ValueError):
        inizio = adesso - timedelta(days=7)
    return max(inizio, adesso - timedelta(days=MAX_DAYS))


def collect(data_dir: Path, store=None, machine_id: Optional[str] = None, now: Optional[datetime] = None, events=None) -> dict:
    """Everything the report says, as data (the page shows the same preview the message carries)."""
    from . import actions, advisor, crashes, drift, trends, watch
    adesso = now or datetime.now()
    inizio = _since(settings(data_dir), adesso)
    da = inizio.isoformat(timespec="seconds")
    punteggi, variazioni, liberi = {}, {}, None
    corse: List[dict] = []
    if store is not None and machine_id:
        for area in actions.AREAS:
            serie = store.trend(machine_id, area, limit=200)
            if serie:
                punteggi[area] = serie[-1]["score"]
                prima = [s for s in serie if s["created"] < da]
                variazioni[area] = serie[-1]["score"] - prima[-1]["score"] if prima else None
        sistema = store.last_scan(machine_id, "system")
        volumi = ((sistema or {}).get("data") or {}).get("volumes") or []
        c = next((v for v in volumi if v.get("letter") == "C"), None)
        liberi = c.get("free_gb") if c else None
        corse = [r for r in store.runs(machine_id, limit=2000) if (r.get("started") or "") >= da]
    verifiche = [r.get("verify") for r in corse if isinstance(r.get("verify"), dict)]
    conn = watch.connection_history(data_dir)
    cadute = [o for o in conn["outages"] if o["from"] >= da]
    cambi = [h for h in drift.last(data_dir)["history"] if (h.get("at") or "") >= da]
    blu = [c for g in crashes.analyze().get("groups", []) for c in g["crashes"] if c["at"] >= da] if events is None else events.get("bsod", [])
    try:
        from . import early_warning
        segni = early_warning.check(data_dir) if events is None else events.get("warning", {"signals": [], "forecasts": []})
    except Exception:  # noqa: BLE001 - the report goes out without this part
        segni = {"signals": [], "forecasts": []}
    try:
        notifiche = json.loads((Path(data_dir) / "notifications.json").read_text(encoding="utf-8")).get("sent", {})
    except (OSError, ValueError):
        notifiche = {}
    avvisi = sorted({k.split(":", 1)[0] for k, t in notifiche.items() if isinstance(t, (int, float)) and t >= inizio.timestamp()})
    try:
        tendenze = trends.trends(data_dir)
    except Exception:  # noqa: BLE001
        tendenze = {"disks": [], "batteries": []}
    return {
        "start": da, "end": adesso.isoformat(timespec="seconds"), "scores": punteggi, "changes": variazioni,
        "overall": advisor.overall_score(punteggi) if punteggi else None, "c_free_gb": liberi,
        "runs": {"total": len(corse), "ok": sum(1 for r in corse if r["status"] == "ok"), "warning": sum(1 for r in corse if r["status"] == "warning"),
                 "error": sum(1 for r in corse if r["status"] == "error"), "checked": len(verifiche),
                 "fixed": sum(1 for v in verifiche if v.get("verdict") in ("fixed", "applied", "freed")),
                 "not_fixed": sum(1 for v in verifiche if v.get("verdict") in ("not_fixed", "worse", "nothing_freed")),
                 "failed": [{"action_id": r["action_id"], "note": (r.get("note") or "")[:120]} for r in corse if r["status"] == "error"][:10]},
        "outages": [{"from": o["from"], "until": o["until"], "cause": o["cause"]} for o in cadute][:20],
        "drift": sum(h.get("total", 0) for h in cambi), "bsod": len(blu),
        "signals": [s for s in segni.get("signals", []) if s.get("growing")], "forecasts": segni.get("forecasts", []),
        "alerts": avvisi, "disks": [{"name": d.get("name"), "wear": d.get("wear"), "worn_out": d.get("worn_out")} for d in tendenze.get("disks", [])],
    }


def render(dati: dict, lang: str, host: str, titles=None) -> tuple:
    t, nomi = TEXT[lang], AREA_NAMES[lang]
    giorno = lambda iso: iso[:10]  # noqa: E731
    righe = []
    if dati["scores"]:
        righe.append(f"{t['scores']} — {t['overall']}: {dati['overall']}/100")
        for area, punti in dati["scores"].items():
            delta = dati["changes"].get(area)
            righe.append(f"  {nomi.get(area, area)}: {punti}" + (f" ({delta:+d})" if delta else ""))
    if dati["c_free_gb"] is not None:
        righe.append(f"{t['free']} {dati['c_free_gb']} GB")
    r = dati["runs"]
    righe.append("")
    if r["total"]:
        righe.append(f"{t['runs']}: {r['total']} — {r['ok']} {t['ok']}, {r['warning']} {t['warning']}, {r['error']} {t['error']}; "
                     f"{r['checked']} {t['checked']}: {r['fixed']} {t['fixed']}, {r['not_fixed']} {t['not_fixed']}")
        for f in r["failed"]:
            nome = (titles or {}).get(f["action_id"], f["action_id"])
            righe.append(f"  {t['failed_list']}: {nome}" + (f" — {f['note']}" if f["note"] else ""))
    else:
        righe.append(t["no_runs"])
    righe.append(f"{t['outages']}: " + (str(len(dati["outages"])) if dati["outages"] else t["no_outages"]))
    righe.append(f"{t['drift']}: {dati['drift']}")
    righe.append(f"{t['bsod']}: {dati['bsod']}")
    if dati["signals"]:
        righe.append(f"{t['signals']}: " + ", ".join(s["title_it" if lang == "it" else "title"] for s in dati["signals"]))
    for p in dati["forecasts"]:
        righe.append(f"{t['forecasts']}: " + p["text_it" if lang == "it" else "text"])
    righe.append(f"{t['alerts']}: " + (", ".join(dati["alerts"]) if dati["alerts"] else t["none"]))
    righe += ["", t["footer"]]
    return t["title"].format(host=host, start=giorno(dati["start"]), end=giorno(dati["end"])), "\n".join(righe)


def send(data_dir: Path, store=None, machine_id: Optional[str] = None, host: str = "", sender=None, now: Optional[datetime] = None) -> dict:
    """Builds and sends the report; the start of the next period moves only when at least one channel accepted it."""
    from . import actions
    import socket
    impostazioni = settings(data_dir)
    dati = collect(data_dir, store, machine_id, now)
    titolo, testo = render(dati, impostazioni["lang"], host or socket.gethostname(), {a: x.title for a, x in actions.CATALOG.items()})
    notificatore = notify.for_data_dir(data_dir)
    esiti = (sender or notificatore.send)(titolo, testo)
    if any(v == "ok" for v in esiti.values()):
        impostazioni["last_sent"] = dati["end"]
        securestore.write_text(_path(data_dir), json.dumps(impostazioni), encoding="utf-8")
    return {"title": titolo, "text": testo, "channels": esiti, "sent": any(v == "ok" for v in esiti.values())}


def preview(data_dir: Path, store=None, machine_id: Optional[str] = None, host: str = "") -> dict:
    from . import actions
    import socket
    impostazioni = settings(data_dir)
    dati = collect(data_dir, store, machine_id)
    titolo, testo = render(dati, impostazioni["lang"], host or socket.gethostname(), {a: x.title for a, x in actions.CATALOG.items()})
    return dict(impostazioni, title=titolo, text=testo, data=dati,
                channels=notify.Notifier.channels(notify.for_data_dir(data_dir)._read()))


def periodic_report(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .store import Store
    from .core import machine_id
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    if getattr(ctx, "anteprima", False):
        esito = preview(cartella, Store(cartella / "wmm.db"), machine_id())
        ctx.scrivi(esito["text"])
        return Esito(Stato.ANTEPRIMA, "preview: nothing was sent")
    esito = send(cartella, Store(cartella / "wmm.db"), machine_id())
    for riga in esito["text"].splitlines():
        ctx.scrivi(riga)
    if not esito["channels"]:
        return Esito(Stato.AVVISO, "no channel set: Settings › Notifications")
    if not esito["sent"]:
        return Esito(Stato.ERRORE, "; ".join(f"{k}: {v}" for k, v in esito["channels"].items()))
    return Esito(Stato.OK, "sent by " + ", ".join(k for k, v in esito["channels"].items() if v == "ok"))
