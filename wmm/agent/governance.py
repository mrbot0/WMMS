"""Governance (2.10): approval by a second person, API tokens for scripts, a tamper-evident audit log and forwarding
of the audit log to a SIEM.

Approvals: Settings › Runs chooses which risk levels need a second person. A run with such tools becomes a request;
someone with "approvals.decide" who is not the requester approves it (the run starts then) or rejects it. Requests
expire after 24 hours.

API tokens: "wmm_" + 40 hex characters, shown once, kept as SHA-256. A token acts as its user, limited to the scopes
chosen when it was created (never more than the user's role), and works only from this PC (127.0.0.1).

Audit chain: every entry carries the SHA-256 of the previous entry and of its own fields, so a changed or deleted
entry breaks the chain at that point (verify()). SIEM: each entry is also sent as RFC 5424 syslog (UDP or TCP)
and/or written to the Windows Application log, in the background."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import wmm
from . import securestore

APPROVAL_HOURS = 24
TOKEN = re.compile(r"wmm_[0-9a-f]{40}")
SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, requester_id TEXT NOT NULL, requester TEXT NOT NULL,
  actions TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT NOT NULL DEFAULT '',
  decided_at TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', job_id TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS api_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL, hash TEXT NOT NULL UNIQUE,
  scopes TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL, last_used TEXT NOT NULL DEFAULT '', expires TEXT NOT NULL DEFAULT '', revoked INTEGER NOT NULL DEFAULT 0);
"""


class GovernanceError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def setup(acc) -> None:
    with acc._db() as db:
        db.executescript(SCHEMA)
        colonne = {r["name"] for r in db.execute("PRAGMA table_info(audit)")}
        if "hash" not in colonne:
            db.execute("ALTER TABLE audit ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE audit ADD COLUMN hash TEXT NOT NULL DEFAULT ''")


# ---------- audit chain ----------

def entry_hash(prev: str, at: str, user: str, action: str, target: str, detail: str, ok: int) -> str:
    dati = json.dumps([prev, at, user, action, target, detail, int(ok)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(dati.encode("utf-8")).hexdigest()


def verify(acc) -> dict:
    """Recomputes the chain from the first chained entry: the first entry that does not match is where it was changed."""
    with acc._db() as db:
        righe = db.execute("SELECT id, at, user, action, target, detail, ok, prev_hash, hash FROM audit ORDER BY id").fetchall()
    precedente, controllate, rotta = None, 0, None
    for r in righe:
        if not r["hash"]:
            continue  # entries written before 2.10
        if precedente is not None and r["prev_hash"] != precedente:
            rotta = {"id": r["id"], "at": r["at"], "reason": "an entry before this one was deleted or changed"}
            break
        if entry_hash(r["prev_hash"], r["at"], r["user"], r["action"], r["target"], r["detail"], r["ok"]) != r["hash"]:
            rotta = {"id": r["id"], "at": r["at"], "reason": "this entry was changed"}
            break
        precedente, controllate = r["hash"], controllate + 1
    return {"ok": rotta is None, "checked": controllate, "total": len(righe), "broken": rotta,
            "last_hash": precedente, "checked_at": datetime.now().isoformat(timespec="seconds")}


# ---------- SIEM ----------

def _settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "integrations.json"


def load_settings(data_dir: Path) -> dict:
    try:
        dati = json.loads(securestore.read_text(_settings_path(data_dir)))
    except (OSError, ValueError):
        dati = {}
    return dati if isinstance(dati, dict) else {}


def save_settings(data_dir: Path, parte: str, valori: dict) -> dict:
    dati = load_settings(data_dir)
    dati[parte] = valori
    _settings_path(data_dir).parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(_settings_path(data_dir), json.dumps(dati, indent=1, ensure_ascii=False), encoding="utf-8")
    return dati


def siem_settings(data_dir: Path) -> dict:
    s = load_settings(data_dir).get("siem") or {}
    return {"syslog_host": s.get("syslog_host", ""), "syslog_port": int(s.get("syslog_port") or 514), "syslog_proto": s.get("syslog_proto", "udp"),
            "eventlog": bool(s.get("eventlog"))}


def save_siem(data_dir: Path, valori: dict) -> dict:
    host = str(valori.get("syslog_host") or "").strip()
    if host and not re.fullmatch(r"[A-Za-z0-9.\-:]{1,253}", host):
        raise GovernanceError("The syslog server is a host name or an IP address.")
    porta = valori.get("syslog_port", 514)
    if isinstance(porta, bool) or not isinstance(porta, int) or not 1 <= porta <= 65535:
        raise GovernanceError("The syslog port is a number from 1 to 65535.")
    proto = valori.get("syslog_proto", "udp")
    if proto not in ("udp", "tcp"):
        raise GovernanceError("Syslog: udp or tcp.")
    save_settings(data_dir, "siem", {"syslog_host": host, "syslog_port": porta, "syslog_proto": proto, "eventlog": bool(valori.get("eventlog"))})
    return siem_settings(data_dir)


def syslog_line(entry: dict, hostname: str = "") -> bytes:
    """RFC 5424: facility auth (4), severity notice (5) or warning (4) for failures; structured data with the fields."""
    pri = 4 * 8 + (5 if entry.get("ok", True) else 4)
    def sd(v):
        return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")[:500]
    dati = f'[wmm@32473 user="{sd(entry.get("user", ""))}" action="{sd(entry.get("action", ""))}" target="{sd(entry.get("target", ""))}" ok="{1 if entry.get("ok", True) else 0}"]'
    testo = f"<{pri}>1 {entry.get('at', '')} {hostname or socket.gethostname()} WMM - {sd(entry.get('action', ''))[:32]} {dati} {str(entry.get('detail', ''))[:1000]}"
    return testo.encode("utf-8")


def _send_syslog(s: dict, riga: bytes) -> None:
    if s["syslog_proto"] == "tcp":
        with socket.create_connection((s["syslog_host"], s["syslog_port"]), timeout=5) as c:
            c.sendall(str(len(riga)).encode() + b" " + riga)  # octet counting (RFC 6587)
    else:
        with socket.socket(socket.AF_INET6 if ":" in s["syslog_host"] else socket.AF_INET, socket.SOCK_DGRAM) as c:
            c.sendto(riga[:8192], (s["syslog_host"], s["syslog_port"]))


def _write_eventlog(entry: dict) -> None:
    import ctypes
    advapi = ctypes.windll.advapi32
    sorgente = advapi.RegisterEventSourceW(None, "Windows Maintenance Manager")
    if not sorgente:
        return
    try:
        testo = f"{entry.get('action')} by {entry.get('user')} on {entry.get('target')}: {entry.get('detail')}"[:30000]
        stringhe = (ctypes.c_wchar_p * 1)(testo)
        tipo = 0x0004 if entry.get("ok", True) else 0x0002  # information / warning
        advapi.ReportEventW(sorgente, tipo, 0, 1000, None, 1, 0, stringhe, None)
    finally:
        advapi.DeregisterEventSource(sorgente)


def forward(data_dir: Path, entry: dict, sync: bool = False) -> None:
    """Sends an audit entry to the SIEM targets in the background: a SIEM that is down never slows the console."""
    s = siem_settings(data_dir)
    if not s["syslog_host"] and not s["eventlog"]:
        return

    def invia():
        if s["syslog_host"]:
            try:
                _send_syslog(s, syslog_line(entry))
            except OSError:
                pass
        if s["eventlog"]:
            try:
                _write_eventlog(entry)
            except Exception:  # noqa: BLE001 - not on Windows, or the log refused it
                pass
    if sync:
        invia()
    else:
        threading.Thread(target=invia, name="wmm-siem", daemon=True).start()


# ---------- approvals ----------

def approval_levels(data_dir: Path) -> List[str]:
    from . import appsettings
    return list(appsettings.load(data_dir).get("approval_levels") or [])


def needs_approval(data_dir: Path, user: Optional[dict], noti) -> List[str]:
    """The tools of a run that need a second person, for this user (none for those who may bypass, or with accounts off)."""
    livelli = approval_levels(data_dir)
    if user is None or not livelli or "approvals.bypass" in user.get("permissions", ()):
        return []
    return [a.id for a in noti if a.kind != "report" and a.risk in livelli]


def request(acc, user: dict, ids: List[str], motivo: str = "") -> dict:
    with acc._db() as db:
        c = db.execute("INSERT INTO approvals (created, requester_id, requester, actions, reason) VALUES (?, ?, ?, ?, ?)",
                       (datetime.now().isoformat(timespec="seconds"), user["id"], user["username"], json.dumps(ids), str(motivo or "")[:300]))
        ident = c.lastrowid
    acc.audit(user["username"], "approval.request", str(ident), ", ".join(ids)[:500])
    return get(acc, ident)


def _row(r) -> dict:
    d = dict(r)
    d["actions"] = json.loads(d["actions"])
    return d


def _expire(acc) -> None:
    limite = (datetime.now() - timedelta(hours=APPROVAL_HOURS)).isoformat(timespec="seconds")
    with acc._db() as db:
        db.execute("UPDATE approvals SET status = 'expired' WHERE status = 'pending' AND created < ?", (limite,))


def get(acc, ident: int) -> dict:
    with acc._db() as db:
        r = db.execute("SELECT * FROM approvals WHERE id = ?", (ident,)).fetchone()
    if r is None:
        raise GovernanceError("Request not found.", 404)
    return _row(r)


def listing(acc, status: str = "") -> List[dict]:
    _expire(acc)
    with acc._db() as db:
        righe = db.execute("SELECT * FROM approvals" + (" WHERE status = ?" if status else "") + " ORDER BY id DESC LIMIT 200",
                           (status,) if status else ()).fetchall()
    return [_row(r) for r in righe]


def decide(acc, ident: int, decisore: dict, approva: bool, nota: str = "", avvia=None) -> dict:
    """Approve (the run starts through `avvia(ids, requester_id)`) or reject. Never the requester; never twice."""
    _expire(acc)
    voce = get(acc, ident)
    if voce["status"] != "pending":
        raise GovernanceError(f"This request is already {voce['status']}.", 409)
    if voce["requester_id"] == decisore["id"]:
        raise GovernanceError("A request must be decided by someone else.", 403)
    job = ""
    if approva and avvia is not None:
        job = avvia(voce["actions"], voce["requester_id"]) or ""
    with acc._db() as db:
        db.execute("UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, note = ?, job_id = ? WHERE id = ? AND status = 'pending'",
                   ("approved" if approva else "rejected", decisore["username"], datetime.now().isoformat(timespec="seconds"), str(nota)[:300], job, ident))
    acc.audit(decisore["username"], "approval." + ("approve" if approva else "reject"), str(ident), voce["requester"] + ": " + ", ".join(voce["actions"])[:400])
    return get(acc, ident)


# ---------- API tokens ----------

def create_token(acc, user: dict, nome: str, scopes: Optional[List[str]] = None, giorni: int = 90) -> dict:
    nome = str(nome or "").strip()
    if not 2 <= len(nome) <= 60:
        raise GovernanceError("Give the token a name (2 to 60 characters).")
    if isinstance(giorni, bool) or not isinstance(giorni, int) or not 0 <= giorni <= 730:
        raise GovernanceError("Expiry: 0 (never) to 730 days.")
    scopes = sorted(set(scopes or []))
    oltre = [p for p in scopes if p not in user.get("permissions", ())]
    if oltre:
        raise GovernanceError("A token cannot have permissions its user does not have: " + ", ".join(oltre[:5]), 403)
    with acc._db() as db:
        if db.execute("SELECT COUNT(*) FROM api_tokens WHERE user_id = ? AND revoked = 0", (user["id"],)).fetchone()[0] >= 20:
            raise GovernanceError("At most 20 tokens per user: revoke one first.", 409)
    segreto = "wmm_" + secrets.token_hex(20)
    ident = "t" + secrets.token_hex(6)
    scade = (datetime.now() + timedelta(days=giorni)).isoformat(timespec="seconds") if giorni else ""
    with acc._db() as db:
        db.execute("INSERT INTO api_tokens (id, user_id, name, prefix, hash, scopes, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (ident, user["id"], nome, segreto[:12], hashlib.sha256(segreto.encode()).hexdigest(), json.dumps(scopes),
                    datetime.now().isoformat(timespec="seconds"), scade))
    acc.audit(user["username"], "token.create", nome, f"{len(scopes) or 'all'} scopes, expires {scade or 'never'}")
    return {"id": ident, "token": segreto, "name": nome, "expires": scade, "scopes": scopes}


def tokens(acc, user_id: Optional[str] = None) -> List[dict]:
    with acc._db() as db:
        righe = db.execute("SELECT t.*, u.username FROM api_tokens t JOIN users u ON u.id = t.user_id" + (" WHERE t.user_id = ?" if user_id else "") +
                           " ORDER BY t.created DESC", (user_id,) if user_id else ()).fetchall()
    return [{k: (json.loads(r[k]) if k == "scopes" else bool(r[k]) if k == "revoked" else r[k])
             for k in ("id", "user_id", "username", "name", "prefix", "scopes", "created", "last_used", "expires", "revoked")} for r in righe]


def revoke_token(acc, ident: str, by: dict) -> None:
    with acc._db() as db:
        r = db.execute("SELECT user_id, name FROM api_tokens WHERE id = ?", (ident,)).fetchone()
        if r is None:
            raise GovernanceError("Token not found.", 404)
        if r["user_id"] != by["id"] and "users.manage" not in by.get("permissions", ()):
            raise GovernanceError("Only its owner or an administrator can revoke a token.", 403)
        db.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (ident,))
    acc.audit(by["username"], "token.revoke", r["name"], "")


def token_user(acc, segreto: str) -> Optional[dict]:
    """The user a token acts as, with the permissions of its role limited to the token scopes."""
    if not TOKEN.fullmatch(segreto or ""):
        return None
    with acc._db() as db:
        r = db.execute("SELECT * FROM api_tokens WHERE hash = ?", (hashlib.sha256(segreto.encode()).hexdigest(),)).fetchone()
        if r is None or r["revoked"] or (r["expires"] and r["expires"] < datetime.now().isoformat(timespec="seconds")):
            return None
        db.execute("UPDATE api_tokens SET last_used = ? WHERE id = ?", (datetime.now().isoformat(timespec="seconds"), r["id"]))
    try:
        u = acc.get_user(r["user_id"])
    except Exception:  # noqa: BLE001 - user deleted
        return None
    if u["status"] != "active":
        return None
    ruolo = acc.get_role(u["role_id"])
    permessi = set(ruolo["permissions"])
    scopes = json.loads(r["scopes"])
    if scopes:
        permessi &= set(scopes)
    return dict(u, role=ruolo["name"], permissions=sorted(permessi), limited=False, session="", token=r["id"])


def version() -> str:
    return wmm.VERSION
