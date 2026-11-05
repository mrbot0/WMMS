"""Incidents (2.10): every alert that goes out becomes an incident to take charge of. Someone takes it ("I'm on it"),
then closes it with a note. If nobody takes it within the chosen minutes, it is escalated: sent again, marked as an
escalation, to the escalation channels and to the users of the escalation roles. When ticketing is on for that alert,
the incident opens a ticket and keeps its number."""
from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from . import governance, securestore

_LOCK = threading.Lock()
KEEP = 500


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "incidents.json"


def _load(data_dir: Path) -> List[dict]:
    try:
        d = json.loads(securestore.read_text(_path(data_dir)))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(data_dir: Path, voci: List[dict]) -> None:
    securestore.write_text(_path(data_dir), json.dumps(voci[-KEEP:], ensure_ascii=False))


def settings(data_dir: Path) -> dict:
    s = governance.load_settings(data_dir).get("escalation") or {}
    return {"minutes": int(s.get("minutes") or 0), "channels": s.get("channels", []), "roles": s.get("roles", [])}


def save_settings(data_dir: Path, valori: dict, ruoli: List[str]) -> dict:
    minuti = valori.get("minutes", 0)
    if isinstance(minuti, bool) or not isinstance(minuti, int) or not (minuti == 0 or 5 <= minuti <= 1440):
        raise ValueError("Escalate after 5 to 1440 minutes (0 = never).")
    canali = valori.get("channels", [])
    if not isinstance(canali, list) or any(c not in ("email", "telegram", "webhook") for c in canali):
        raise ValueError("Escalation channels: email, telegram, webhook.")
    r = valori.get("roles", [])
    if not isinstance(r, list) or any(x not in ruoli for x in r):
        raise ValueError("Unknown role.")
    governance.save_settings(data_dir, "escalation", {"minutes": minuti, "channels": canali, "roles": r})
    return settings(data_dir)


def open_incident(data_dir: Path, evento: str, titolo: str, testo: str, esiti: dict, ticket_creator=None) -> dict:
    voce = {"id": secrets.token_hex(6), "at": datetime.now().isoformat(timespec="seconds"), "event": evento, "title": titolo[:200], "text": testo[:4000],
            "channels": esiti, "status": "open", "by": "", "ack_at": "", "closed_at": "", "note": "", "escalated_at": "", "ticket": ""}
    from . import tickets
    if tickets.for_event(data_dir, evento):
        esito = (ticket_creator or tickets.create)(data_dir, titolo, testo)
        voce["ticket"] = esito.get("id", "") if esito.get("ok") else "error: " + esito.get("error", "")
    with _LOCK:
        voci = _load(data_dir)
        voci.append(voce)
        _save(data_dir, voci)
    return voce


def listing(data_dir: Path, status: str = "") -> List[dict]:
    voci = list(reversed(_load(data_dir)))
    return [v for v in voci if not status or v["status"] == status][:300]


def update(data_dir: Path, ident: str, azione: str, utente: str, nota: str = "") -> dict:
    with _LOCK:
        voci = _load(data_dir)
        voce = next((v for v in voci if v["id"] == ident), None)
        if voce is None:
            raise KeyError(ident)
        adesso = datetime.now().isoformat(timespec="seconds")
        if azione == "ack":
            if voce["status"] != "open":
                raise ValueError("This incident is already taken.")
            voce.update(status="acknowledged", by=utente, ack_at=adesso)
        elif azione == "close":
            if voce["status"] == "closed":
                raise ValueError("Already closed.")
            voce.update(status="closed", closed_at=adesso, note=str(nota)[:500], by=voce["by"] or utente)
        elif azione == "reopen":
            voce.update(status="open", closed_at="", ack_at="", by="")
        else:
            raise ValueError("Unknown action.")
        _save(data_dir, voci)
        return voce


def escalate_due(data_dir: Path, sender=None, now: Optional[datetime] = None) -> int:
    """Sends again, as an escalation, the incidents nobody took within the minutes set. Called every minute."""
    s = settings(data_dir)
    if not s["minutes"]:
        return 0
    adesso = now or datetime.now()
    limite = (adesso - timedelta(minutes=s["minutes"])).isoformat(timespec="seconds")
    with _LOCK:
        voci = _load(data_dir)
        dovuti = [v for v in voci if v["status"] == "open" and not v["escalated_at"] and v["at"] <= limite]
        for v in dovuti:
            v["escalated_at"] = adesso.isoformat(timespec="seconds")
        if dovuti:
            _save(data_dir, voci)
    for v in dovuti:
        testo = f"Nobody has taken this alert in {s['minutes']} minutes.\n\n{v['text']}"
        if sender is not None:
            sender(v, testo, s)
        else:
            _send_escalation(data_dir, v, testo, s)
    return len(dovuti)


def _send_escalation(data_dir: Path, voce: dict, testo: str, s: dict) -> None:
    from . import notify
    n = notify.for_data_dir(data_dir)
    canali = s["channels"] or None
    try:
        n.send("ESCALATION: " + voce["title"], testo, solo=canali, evento="escalation")
    except Exception:  # noqa: BLE001 - escalation is best effort like every alert
        pass
    if s["roles"] and (Path(data_dir) / "accounts.db").exists():
        from .accounts import for_data_dir
        try:
            utenti = [u for u in for_data_dir(data_dir).users() if u["role_id"] in s["roles"] and u["status"] == "active"]
        except Exception:  # noqa: BLE001
            utenti = []
        dati = n._read()
        for u in utenti:
            if u["email"] and dati.get("smtp_host"):
                n._email(dict(dati, email_to=u["email"]), "ESCALATION: " + voce["title"], testo)
            if u["telegram"] and dati.get("telegram_token"):
                n._telegram(notify.unprotect(dati["telegram_token"]), u["telegram"], "ESCALATION: " + voce["title"] + "\n\n" + testo)
