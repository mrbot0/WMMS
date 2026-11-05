"""Compliance baselines (2.10). A baseline is a list of checks of the catalog (the same read-only checks the fixes use
before and after they run): each says whether this PC is as it should be. The result is a percentage and, for each
check that fails, the fix that brings it back, which can run from here (with the usual confirmations) or from the
central server. Built in: "Security baseline" and "Business workstation"; your own baselines from any checks."""
from __future__ import annotations

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from . import verify

BUILTIN = {
    "security": {"name": "Security baseline", "description": "Defender, firewall, SmartScreen, UAC, SMBv1, Remote Desktop and protections.",
                 "keywords": ("security.",)},
    "workstation": {"name": "Business workstation", "description": "Security plus updates, services and network as a company PC needs them.",
                    "keywords": ("security.", "updates.", "network.", "services.")},
}


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "baselines.json"


def _load(data_dir: Path) -> dict:
    try:
        d = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data_dir: Path, d: dict) -> None:
    _path(data_dir).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def available_checks() -> List[dict]:
    """The checks that say right or wrong by themselves (those with a healthy value)."""
    from . import actions
    return [{"id": k, "label": c.label, "title": actions.CATALOG[k].title if k in actions.CATALOG else k, "area": k.split(".")[0]}
            for k, c in verify.CHECKS.items() if c.ok is not None and k in actions.CATALOG]


def builtin_checks(chiave: str) -> List[str]:
    parole = BUILTIN[chiave]["keywords"]
    return [c["id"] for c in available_checks() if c["id"].startswith(parole)]


def baselines(data_dir: Path) -> List[dict]:
    d = _load(data_dir)
    elenco = [{"id": k, "name": v["name"], "description": v["description"], "checks": builtin_checks(k), "builtin": True} for k, v in BUILTIN.items()]
    elenco += [dict(v, id=k, builtin=False) for k, v in d.get("custom", {}).items()]
    for b in elenco:
        b["last"] = d.get("results", {}).get(b["id"])
    return elenco


def save(data_dir: Path, dati: dict, ident: Optional[str] = None) -> dict:
    nome = str(dati.get("name", "")).strip()
    if not 2 <= len(nome) <= 60:
        raise ValueError("Baseline name: 2 to 60 characters.")
    noti = {c["id"] for c in available_checks()}
    controlli = dati.get("checks")
    if not isinstance(controlli, list) or not controlli or any(c not in noti for c in controlli):
        raise ValueError("Choose at least one check of the list.")
    if ident in BUILTIN:
        raise ValueError("Built-in baselines cannot be changed: copy them.")
    d = _load(data_dir)
    ident = ident or "b" + secrets.token_hex(5)
    d.setdefault("custom", {})[ident] = {"name": nome, "description": str(dati.get("description", ""))[:200], "checks": sorted(set(controlli))}
    _write(data_dir, d)
    return next(b for b in baselines(data_dir) if b["id"] == ident)


def delete(data_dir: Path, ident: str) -> None:
    d = _load(data_dir)
    if ident not in d.get("custom", {}):
        raise KeyError(ident)
    del d["custom"][ident]
    d.get("results", {}).pop(ident, None)
    _write(data_dir, d)


def evaluate(controlli: List[str], runner: Optional[Callable[[str], str]] = None) -> dict:
    """Reads every check (in parallel) and says which comply."""
    def uno(ident: str) -> dict:
        c = verify.CHECKS[ident]
        valore = verify.read(c, runner)
        ok = None if valore is None or c.ok is None else bool(c.ok(valore))  # no rule: only shown
        return {"id": ident, "label": c.label, "value": valore, "ok": ok}
    with ThreadPoolExecutor(max_workers=8) as pool:
        righe = list(pool.map(uno, [c for c in controlli if c in verify.CHECKS]))
    letti = [r for r in righe if r["ok"] is not None]
    percento = round(100 * sum(r["ok"] for r in letti) / len(letti), 1) if letti else None
    return {"percent": percento, "checks": righe, "failing": [r["id"] for r in righe if r["ok"] is False],
            "unreadable": [r["id"] for r in righe if r["ok"] is None], "checked": datetime.now().isoformat(timespec="seconds")}


def run(data_dir: Path, ident: str, runner=None) -> dict:
    b = next((x for x in baselines(data_dir) if x["id"] == ident), None)
    if b is None:
        raise KeyError(ident)
    esito = dict(evaluate(b["checks"], runner), baseline=b["name"], id=ident)
    d = _load(data_dir)
    d.setdefault("results", {})[ident] = {k: esito[k] for k in ("percent", "failing", "unreadable", "checked")}
    _write(data_dir, d)
    return esito


def last_summary(data_dir: Path) -> dict:
    """What the central server shows: the lowest compliance of the baselines checked on this PC."""
    risultati = [r for r in _load(data_dir).get("results", {}).values() if r.get("percent") is not None]
    if not risultati:
        return {}
    peggiore = min(risultati, key=lambda r: r["percent"])
    return {"percent": peggiore["percent"], "failing": peggiore["failing"], "checked": peggiore["checked"]}


def compliance_report(ctx, data_dir: Optional[Path] = None):
    from ottimizza_pc import Esito, Stato
    from .watch import DATA_DIR
    cartella = Path(data_dir) if data_dir else DATA_DIR
    esito = run(cartella, "workstation")
    for r in esito["checks"]:
        ctx.scrivi(f"{'OK  ' if r['ok'] else '??  ' if r['ok'] is None else 'FAIL'} {r['label']}: {r['value']}")
    if esito["failing"]:
        return Esito(Stato.AVVISO, f"{esito['percent']}% compliant, {len(esito['failing'])} checks to fix")
    return Esito(Stato.OK, f"{esito['percent']}% compliant")
