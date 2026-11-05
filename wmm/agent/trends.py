"""Disk and battery over time. The Hardware page shows the state of today; this keeps one reading a day of every
disk (SMART wear, temperature, read and write errors, power-on hours) and of the battery (full charge against design
capacity), and estimates from the trend when a disk will be worn out and when the battery will hold less than 60%.
Read-only; meant to be scheduled (storage.health_trend)."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from ottimizza_pc import Esito, Stato

from . import securestore
from .tools import powershell_command

KEEP_DAYS = 3 * 365
BATTERY_LIMIT = 60.0
WEAR_LIMIT = 100.0

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$disks = @(Get-PhysicalDisk | ForEach-Object {
  $r = $_ | Get-StorageReliabilityCounter
  [ordered]@{ id = "$($_.SerialNumber)".Trim(); name = "$($_.FriendlyName)"; media = "$($_.MediaType)"; health = "$($_.HealthStatus)"
    wear = $r.Wear; temperature = $r.Temperature; read_errors = $r.ReadErrorsTotal; write_errors = $r.WriteErrorsTotal; hours = $r.PowerOnHours }
})
$full = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity)
$static = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData)
$bat = @(for ($i = 0; $i -lt $full.Count; $i++) {
  [ordered]@{ id = "battery$i"; name = "$($static[$i].DeviceName)".Trim(); full = $full[$i].FullChargedCapacity; design = $static[$i].DesignedCapacity }
})
[ordered]@{ disks = $disks; batteries = $bat } | ConvertTo-Json -Depth 4 -Compress
"""


def _numero(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def read(runner: Optional[Callable[[], str]] = None) -> dict:
    if runner is None:
        finito = subprocess.run(powershell_command(SCRIPT), capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        testo = finito.stdout
    else:
        testo = runner()
    righe = (testo or "").strip().splitlines()
    try:
        dati = json.loads(righe[-1]) if righe else {}
    except ValueError:
        dati = {}

    def elenco(v):
        return v if isinstance(v, list) else [v] if isinstance(v, dict) else []
    dischi = [{"id": str(d.get("id") or d.get("name") or "disk")[:80], "name": str(d.get("name") or "")[:80], "media": str(d.get("media") or ""),
               "health": str(d.get("health") or ""), **{k: _numero(d.get(k)) for k in ("wear", "temperature", "read_errors", "write_errors", "hours")}}
              for d in elenco(dati.get("disks")) if isinstance(d, dict)]
    batterie = []
    for b in elenco(dati.get("batteries")):
        if not isinstance(b, dict):
            continue
        piena, progetto = _numero(b.get("full")), _numero(b.get("design"))
        if piena and progetto:
            batterie.append({"id": str(b.get("id")), "name": str(b.get("name") or "Battery")[:80], "full": piena, "design": progetto,
                             "capacity_pct": round(100 * piena / progetto, 1)})
    return {"disks": dischi, "batteries": batterie}


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "health_history.json"


def history(data_dir: Path) -> List[dict]:
    try:
        return json.loads(securestore.read_text(_path(data_dir))).get("samples", [])
    except (OSError, ValueError):
        return []


def record(data_dir: Path, lettura: Optional[dict] = None, quando: Optional[datetime] = None) -> dict:
    """Adds today's reading (one a day: a second one the same day replaces the first)."""
    istante = (quando or datetime.now()).replace(microsecond=0)
    campione = dict(lettura if lettura is not None else read(), t=istante.isoformat())
    campioni = [c for c in history(data_dir) if not str(c.get("t", "")).startswith(istante.date().isoformat())]
    limite = (istante - timedelta(days=KEEP_DAYS)).isoformat()
    campioni = sorted([c for c in campioni if str(c.get("t", "")) >= limite] + [campione], key=lambda c: c["t"])
    percorso = _path(data_dir)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(percorso, json.dumps({"samples": campioni}), encoding="utf-8")
    return campione


def _slope(punti: List[tuple]) -> Optional[float]:
    """Least squares: change per day."""
    if len(punti) < 2:
        return None
    n = len(punti)
    mx, my = sum(p[0] for p in punti) / n, sum(p[1] for p in punti) / n
    den = sum((p[0] - mx) ** 2 for p in punti)
    return sum((p[0] - mx) * (p[1] - my) for p in punti) / den if den else None


def _series(campioni: List[dict], gruppo: str, chiave: str, campo: str) -> List[tuple]:
    punti = []
    for c in campioni:
        try:
            giorno = datetime.fromisoformat(c["t"]).timestamp() / 86400
        except (KeyError, TypeError, ValueError):
            continue
        for voce in c.get(gruppo, []):
            if voce.get("id") == chiave and isinstance(voce.get(campo), (int, float)):
                punti.append((giorno, float(voce[campo])))
    return punti


def _forecast(punti: List[tuple], limite: float, crescente: bool) -> Optional[str]:
    """The date the trend reaches the limit, when it moves towards it and the readings span at least a week."""
    pendenza = _slope(punti)
    if pendenza is None or punti[-1][0] - punti[0][0] < 7:
        return None
    if (crescente and pendenza <= 0) or (not crescente and pendenza >= 0):
        return None
    giorni = (limite - punti[-1][1]) / pendenza
    if giorni < 0 or giorni > 365 * 30:
        return None
    return (datetime.fromtimestamp(punti[-1][0] * 86400) + timedelta(days=giorni)).date().isoformat()


def _per_month(punti: List[tuple], segno: int = 1) -> Optional[float]:
    pendenza = _slope(punti)
    return round(segno * pendenza * 30, 2) if pendenza is not None else None


def trends(data_dir: Path) -> dict:
    campioni = history(data_dir)
    ultimo = campioni[-1] if campioni else {"disks": [], "batteries": []}
    dischi = []
    for d in ultimo.get("disks", []):
        usura = _series(campioni, "disks", d["id"], "wear")
        errori = _series(campioni, "disks", d["id"], "read_errors")
        dischi.append(dict(d, wear_per_month=_per_month(usura), worn_out=_forecast(usura, WEAR_LIMIT, True),
                           new_errors=(errori[-1][1] - errori[0][1]) if len(errori) >= 2 else 0,
                           series=[{"t": datetime.fromtimestamp(x * 86400).date().isoformat(), "value": y} for x, y in usura[-120:]]))
    batterie = []
    for b in ultimo.get("batteries", []):
        capacita = _series(campioni, "batteries", b["id"], "capacity_pct")
        batterie.append(dict(b, loss_per_month=_per_month(capacita, -1), below_limit=_forecast(capacita, BATTERY_LIMIT, False),
                             series=[{"t": datetime.fromtimestamp(x * 86400).date().isoformat(), "value": y} for x, y in capacita[-120:]]))
    return {"samples": len(campioni), "first": campioni[0]["t"] if campioni else None, "last": ultimo.get("t"),
            "disks": dischi, "batteries": batterie, "battery_limit": BATTERY_LIMIT}


def health_trend(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    record(cartella)
    dati = trends(cartella)
    avvisi = []
    entro_un_anno = (datetime.now() + timedelta(days=365)).date().isoformat()
    for d in dati["disks"]:
        ctx.scrivi(f"{d['name']}: wear {d['wear'] if d['wear'] is not None else '?'}%, {d['temperature'] or '?'} °C, "
                   f"{int(d['hours']) if d['hours'] else '?'} hours, health {d['health']}"
                   + (f", worn out around {d['worn_out']}" if d["worn_out"] else ""))
        if d["new_errors"]:
            avvisi.append(f"{d['name']}: {int(d['new_errors'])} new read errors")
        if d["worn_out"] and d["worn_out"] < entro_un_anno:
            avvisi.append(f"{d['name']} may be worn out by {d['worn_out']}")
    for b in dati["batteries"]:
        ctx.scrivi(f"{b['name']}: {b['capacity_pct']}% of its design capacity"
                   + (f", below {BATTERY_LIMIT:.0f}% around {b['below_limit']}" if b["below_limit"] else ""))
    ctx.scrivi(f"{dati['samples']} daily readings since {dati['first']}: the estimates need at least a week of readings.")
    if avvisi:
        return Esito(Stato.AVVISO, "; ".join(avvisi))
    return Esito(Stato.OK, f"reading {dati['samples']} recorded")
