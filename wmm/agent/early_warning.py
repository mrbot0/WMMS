"""Warnings before a failure (2.8). Disks, memory and power supplies rarely die without signs: hardware errors (WHEA),
disk retries and bad blocks, controller resets, sudden power losses and blue screens start to appear and then grow.
This counts those events in the System log week by week, compares the last 7 days with the 4 weeks before, adds the
disk and battery forecasts of the daily trend, and sends one alert when a signal is growing. Read-only."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ottimizza_pc import Esito, Stato

from . import notify
from .crashes import as_list, parse_time, run_json

# Kind -> (title, Italian title, what it means, Italian meaning)
SIGNALS = {
    "whea": ("Hardware errors (WHEA)", "Errori hardware (WHEA)", "The processor, memory or a bus reported errors: overheating, overclock or failing parts.",
             "Processore, memoria o un bus hanno segnalato errori: surriscaldamento, overclock o componenti che si guastano."),
    "disk": ("Disk errors and retries", "Errori e tentativi del disco", "The disk needed retries or has bad blocks: back up your files and check its health.",
             "Il disco ha dovuto riprovare o ha settori danneggiati: fai una copia dei file e controllane la salute."),
    "storage_reset": ("Disk controller resets", "Reset del controller del disco", "The disk stopped answering and was reset: cable, SSD firmware or a failing disk.",
                      "Il disco ha smesso di rispondere ed è stato reimpostato: cavo, firmware dell'SSD o disco guasto."),
    "filesystem": ("File system damage", "Danni al file system", "NTFS found damage: a disk check is needed.",
                   "NTFS ha trovato danni: serve un controllo del disco."),
    "power_loss": ("Sudden power losses", "Spegnimenti improvvisi", "The PC switched off without shutting down: power supply, battery, overheating or crashes.",
                   "Il PC si è spento senza chiudere Windows: alimentatore, batteria, surriscaldamento o blocchi."),
    "bugcheck": ("Blue screens", "Schermate blu", "Windows stopped with an error: see Blue screens explained.",
                 "Windows si è fermato con un errore: vedi Schermate blu spiegate."),
}

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$since = (Get-Date).AddDays(-35)
$f = @(
  @{ k = 'whea'; h = @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WHEA-Logger'; StartTime = $since } },
  @{ k = 'disk'; h = @{ LogName = 'System'; ProviderName = 'disk'; Id = 7, 11, 51, 153; StartTime = $since } },
  @{ k = 'storage_reset'; h = @{ LogName = 'System'; ProviderName = 'stornvme', 'storahci', 'iaStorAC', 'iaStorA'; Id = 129; StartTime = $since } },
  @{ k = 'filesystem'; h = @{ LogName = 'System'; ProviderName = 'Ntfs', 'Microsoft-Windows-Ntfs'; Id = 55; StartTime = $since } },
  @{ k = 'power_loss'; h = @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Power'; Id = 41; StartTime = $since } },
  @{ k = 'bugcheck'; h = @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting'; Id = 1001; StartTime = $since } }
)
$out = @(foreach ($x in $f) { Get-WinEvent -FilterHashtable $x.h -MaxEvents 500 | ForEach-Object { [ordered]@{ kind = $x.k; at = $_.TimeCreated.ToString('s') } } })
[ordered]@{ events = $out } | ConvertTo-Json -Depth 4 -Compress
"""


def read(runner: Optional[Callable[[], str]] = None) -> List[dict]:
    return [{"kind": str(e.get("kind")), "at": str(e.get("at") or "")} for e in as_list(run_json(SCRIPT, runner).get("events"))
            if isinstance(e, dict) and e.get("kind") in SIGNALS]


def evaluate(eventi: List[dict], tendenze: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    """Per kind: events in the last 7 days against the weekly average of the 4 weeks before. A signal is growing when the
    last week has at least 2 events and twice the usual rate (or any, for kinds that should never happen)."""
    adesso = now or datetime.now()
    settimana, mese = adesso - timedelta(days=7), adesso - timedelta(days=35)
    conti: Dict[str, dict] = {k: {"week": 0, "before": 0, "last": None} for k in SIGNALS}
    for e in eventi:
        quando = parse_time(e["at"])
        if quando is None or quando < mese or e["kind"] not in conti:
            continue
        c = conti[e["kind"]]
        if quando >= settimana:
            c["week"] += 1
        else:
            c["before"] += 1
        c["last"] = max(c["last"] or e["at"], e["at"])
    segnali = []
    for kind, c in conti.items():
        media = c["before"] / 4
        rari = kind in ("filesystem", "storage_reset", "bugcheck")
        crescente = c["week"] >= 2 and c["week"] > 2 * media if not rari else c["week"] >= 1 and c["week"] > 2 * media
        titolo, titolo_it, testo, testo_it = SIGNALS[kind]
        segnali.append({"kind": kind, "title": titolo, "title_it": titolo_it, "meaning": testo, "meaning_it": testo_it, "last_7_days": c["week"],
                        "weekly_before": round(media, 1), "last": c["last"], "growing": crescente})
    previsioni = []
    entro = (adesso + timedelta(days=180)).date().isoformat()
    for d in (tendenze or {}).get("disks", []):
        if d.get("worn_out") and d["worn_out"] <= entro:
            previsioni.append({"kind": "disk_wear", "item": d.get("name"), "date": d["worn_out"],
                               "text": f"{d.get('name')} may be worn out around {d['worn_out']}",
                               "text_it": f"{d.get('name')} potrebbe essere consumato verso il {d['worn_out']}"})
        if d.get("new_errors"):
            previsioni.append({"kind": "disk_errors", "item": d.get("name"), "date": None,
                               "text": f"{d.get('name')}: {int(d['new_errors'])} new read errors since the first reading",
                               "text_it": f"{d.get('name')}: {int(d['new_errors'])} nuovi errori di lettura dalla prima rilevazione"})
    for b in (tendenze or {}).get("batteries", []):
        if b.get("below_limit") and b["below_limit"] <= entro:
            previsioni.append({"kind": "battery", "item": b.get("name"), "date": b["below_limit"],
                               "text": f"The battery {b.get('name') or ''} may hold less than 60% around {b['below_limit']}".replace("  ", " "),
                               "text_it": f"La batteria {b.get('name') or ''} potrebbe tenere meno del 60% verso il {b['below_limit']}".replace("  ", " ")})
    crescenti = [s for s in segnali if s["growing"]]
    livello = "warning" if crescenti or previsioni else "ok"
    return {"signals": segnali, "growing": [s["kind"] for s in crescenti], "forecasts": previsioni, "level": livello,
            "checked": adesso.isoformat(timespec="seconds")}


def check(data_dir: Path, runner: Optional[Callable[[], str]] = None, now: Optional[datetime] = None) -> dict:
    from . import trends
    try:
        tendenze = trends.trends(Path(data_dir))
    except Exception:  # noqa: BLE001 - the event signals stand on their own
        tendenze = {}
    return evaluate(read(runner), tendenze, now)


def alert_text(esito: dict) -> str:
    righe = [f"- {s['title']}: {s['last_7_days']} in the last 7 days (usually {s['weekly_before']} a week). {s['meaning']}"
             for s in esito["signals"] if s["growing"]]
    righe += [f"- {p['text']}" for p in esito["forecasts"]]
    return "Signs that a part of this PC may fail soon:\n" + "\n".join(righe) + "\n\nBack up your files and open Health in the console."


def early_warning(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    esito = check(cartella)
    for s in esito["signals"]:
        ctx.scrivi(f"{'GROWING ' if s['growing'] else '        '}{s['title']}: {s['last_7_days']} in 7 days, {s['weekly_before']} a week before")
    for p in esito["forecasts"]:
        ctx.scrivi("FORECAST " + p["text"])
    if esito["level"] == "ok":
        return Esito(Stato.OK, "no growing signal")
    testo = alert_text(esito)
    gruppo = hashlib.sha1(("|".join(esito["growing"]) + "|" + "|".join(p["kind"] + str(p["item"]) for p in esito["forecasts"])).encode("utf-8")).hexdigest()[:12]
    notify.safe_event(cartella, "early_warning", testo, gruppo=gruppo)
    return Esito(Stato.AVVISO, f"{len(esito['growing'])} growing signals, {len(esito['forecasts'])} forecasts")
