"""Accounts, roles and permissions (2.9). Off until an administrator turns them on in Settings › Accounts: from then on
every console session signs in with a user name and password (and a 6-digit code when two-step verification is on),
and every request is checked against the permissions of the user's role. Roles are fully configurable: which pages a
role sees, which tools it may run in every area and up to which risk, and what it may manage (schedules, registry,
users, settings...). Passwords are kept as scrypt hashes, sessions as SHA-256 hashes of random tokens, the two-step
secret encrypted for the Windows user (DPAPI). Every sign-in and every change is written to the audit log."""
from __future__ import annotations

import base64
import contextlib
import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import struct
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

from . import notify

# ---------- the catalog of permissions ----------

PAGES = [
    ("dashboard", "Dashboard"), ("recommendations", "Recommendations"), ("performance", "Performance"), ("cleanup", "Cleanup"),
    ("storage", "Storage"), ("startup", "Startup & Apps"), ("apps", "Applications"), ("services", "Services"), ("integrity", "System Integrity"),
    ("security", "Security"), ("updates", "Updates & Drivers"), ("network", "Network"), ("hardware", "Hardware"), ("events", "Event Viewer"),
    ("processes", "Task Manager"), ("registry", "Registry"), ("netscan", "Network scanner"), ("toolbox", "Toolbox"), ("activity", "Activity"),
    ("playbooks", "Playbooks"), ("schedules", "Schedules"), ("fleet", "PCs"), ("scripts", "Scripts"), ("history", "History"), ("reports", "Reports"),
    ("support", "Support"), ("settings", "Settings"), ("users", "Users and roles"),
]
AREAS = [("cleanup", "Cleanup"), ("integrity", "System Integrity"), ("services", "Services"), ("performance", "Performance"), ("storage", "Storage"),
         ("network", "Network"), ("startup", "Startup & Apps"), ("security", "Security"), ("updates", "Updates & Drivers")]
LEVELS = [("report", "Reports (read-only)"), ("safe", "Safe fixes"), ("moderate", "Moderate fixes"), ("high", "High-risk fixes")]
CAPABILITIES = [
    ("scan.run", "Operations", "Run scans of the areas"),
    ("schedules.manage", "Operations", "Create, change and delete schedules"),
    ("scripts.run", "Operations", "Run scripts and the shutdown timer"),
    ("scripts.manage", "Operations", "Create, change and delete scripts"),
    ("custom_tools.manage", "Operations", "Create and change your own tools"),
    ("run.custom", "Operations", "Run your own tools"),
    ("history.undo", "Operations", "Undo the changes of a run"),
    ("history.prune", "Operations", "Delete old history"),
    ("export.data", "Operations", "Export reports and data"),
    ("registry.edit", "System", "Edit the registry"),
    ("processes.control", "System", "End, prioritize and start processes"),
    ("services.control", "System", "Start, stop and restart services"),
    ("startup.toggle", "System", "Turn startup programs on and off"),
    ("apps.manage", "System", "Uninstall and update applications"),
    ("goodconfig.apply", "System", "Go back to an earlier configuration"),
    ("network.scan", "Network", "Scan the network, Wi-Fi and Bluetooth"),
    ("fleet.manage", "Network", "Add PCs and share this PC"),
    ("fleet.run", "Network", "Run tools on other PCs"),
    ("phone.manage", "Network", "Turn on the phone console and pair phones"),
    ("assistant.use", "Assistant", "Use the assistant"),
    ("notifications.manage", "Settings", "E-mail, Telegram and webhook alerts"),
    ("settings.edit", "Settings", "Change the settings of the app"),
    ("settings.security", "Settings", "Password, sign-in and session policies"),
    ("data.backup", "Settings", "Back up and restore the configuration"),
    ("agent.control", "Settings", "Restart, elevate, update and stop the agent"),
    ("users.view", "Users", "See users, roles and sessions"),
    ("users.manage", "Users", "Create, change and delete users"),
    ("roles.manage", "Users", "Create, change and delete roles"),
    ("sessions.manage", "Users", "Sign out other users"),
    ("audit.view", "Users", "Read and export the audit log"),
]


def catalog() -> List[dict]:
    """Every permission with its group and label (the role editor draws its matrix from this)."""
    voci = [{"id": f"view.{p}", "group": "Pages", "label": t} for p, t in PAGES]
    voci += [{"id": f"run.{a}.{l}", "group": "Tools", "label": f"{t}: {lt}", "area": a, "level": l} for a, t in AREAS for l, lt in LEVELS]
    voci += [{"id": c, "group": g, "label": t} for c, g, t in CAPABILITIES]
    return voci


ALL = frozenset(v["id"] for v in catalog())
ADMIN_ROLE = "admin"


def _pages(*nomi) -> List[str]:
    return [f"view.{n}" for n in nomi]


def _runs(*livelli) -> List[str]:
    return [f"run.{a}.{l}" for a, _ in AREAS for l in livelli]


AREA_PAGES = ("dashboard", "recommendations", "performance", "cleanup", "storage", "startup", "apps", "services", "integrity", "security", "updates", "network")
BUILTIN = {
    "admin": {"name": "Administrator", "description": "Everything, including users, roles and security policies. Cannot be changed.",
              "color": "red", "permissions": sorted(ALL)},
    "technician": {"name": "Technician", "description": "Every page and tool, schedules, scripts, registry and other PCs; no users, roles or security policies.",
                   "color": "blue", "permissions": sorted(set(_pages(*[p for p, _ in PAGES if p != "users"])) | set(_runs("report", "safe", "moderate", "high")) |
                                                         {c for c, g, _ in CAPABILITIES if g not in ("Users",)} - {"settings.security", "data.backup"})},
    "operator": {"name": "Operator", "description": "Scans, reports and safe fixes on the area pages; no system tools or settings.",
                 "color": "green", "permissions": sorted(set(_pages(*AREA_PAGES, "hardware", "toolbox", "activity", "playbooks", "history", "reports", "support")) |
                                                       set(_runs("report", "safe")) | {"scan.run", "export.data", "network.scan"})},
    "viewer": {"name": "Viewer", "description": "Sees the state of the PC and the reports; runs only read-only reports.",
               "color": "gray", "permissions": sorted(set(_pages(*AREA_PAGES, "hardware", "history", "reports", "support")) | set(_runs("report")))},
    "auditor": {"name": "Auditor", "description": "History, reports, users and the audit log, read-only.",
                "color": "purple", "permissions": sorted(set(_pages("dashboard", "history", "reports", "users", "support")) | {"users.view", "audit.view", "export.data"})},
}
COLORS = ("red", "blue", "green", "gray", "purple", "orange", "teal", "pink")

POLICY_DEFAULTS = {"enabled": False, "min_length": 10, "classes": 3, "history": 5, "expiry_days": 0, "lockout_attempts": 5, "lockout_minutes": 15,
                   "idle_minutes": 30, "max_hours": 12, "single_session": False, "audit_days": 365, "require_2fa_admins": False}
POLICY_LIMITS = {"min_length": (8, 64), "classes": (1, 4), "history": (0, 24), "expiry_days": (0, 365), "lockout_attempts": (3, 20),
                 "lockout_minutes": (1, 1440), "idle_minutes": (5, 480), "max_hours": (1, 168), "audit_days": (30, 3650)}
USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,31}")
SCRYPT = (2 ** 14, 8, 1)


class AccountError(ValueError):
    """A request that breaks a rule: shown as it is on the page."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now_iso(t: Optional[float] = None) -> str:
    return datetime.fromtimestamp(t if t is not None else time.time()).isoformat(timespec="seconds")


# ---------- passwords and two-step codes ----------

def hash_password(password: str) -> str:
    sale = secrets.token_bytes(16)
    n, r, p = SCRYPT
    calcolo = hashlib.scrypt(password.encode("utf-8"), salt=sale, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${sale.hex()}${calcolo.hex()}"


def check_password(password: str, salvato: str) -> bool:
    try:
        _, n, r, p, sale, atteso = salvato.split("$")
        calcolo = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(sale), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calcolo.hex(), atteso)


_DUMMY = None


def totp_code(secret_b32: str, counter: int) -> str:
    chiave = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(chiave, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def totp_match(secret_b32: str, code: str, t: Optional[float] = None, last: int = -1) -> Optional[int]:
    """The time step the code belongs to (now ±30 s), never one already used."""
    if not re.fullmatch(r"\d{6}", code or ""):
        return None
    passo = int((t if t is not None else time.time()) // 30)
    for c in (passo, passo - 1, passo + 1):
        if c > last and hmac.compare_digest(totp_code(secret_b32, c), code):
            return c
    return None


def password_problems(password: str, policy: dict, username: str = "") -> List[str]:
    problemi = []
    if not isinstance(password, str) or len(password) < policy["min_length"]:
        problemi.append(f"at least {policy['min_length']} characters")
        password = password if isinstance(password, str) else ""
    classi = sum(bool(re.search(x, password)) for x in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classi < policy["classes"]:
        problemi.append(f"at least {policy['classes']} of lowercase, uppercase, digits, symbols")
    if username and username.lower() in password.lower():
        problemi.append("without the user name")
    if len(password) > 200:
        problemi.append("at most 200 characters")
    return problemi


def temporary_password() -> str:
    """Random, readable and valid for any policy: 4 groups of letters and digits plus a symbol."""
    lettere = "abcdefghjkmnpqrstuvwxyz"
    gruppi = ["".join(secrets.choice(lettere) for _ in range(4)), "".join(secrets.choice(lettere.upper()) for _ in range(4)),
              "".join(secrets.choice("23456789") for _ in range(4)), "".join(secrets.choice(lettere) for _ in range(4))]
    return "-".join(gruppi) + secrets.choice("!#%+")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '', telegram TEXT NOT NULL DEFAULT '', role_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, password TEXT NOT NULL,
  must_change INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL, last_login TEXT, failed INTEGER NOT NULL DEFAULT 0,
  locked_until REAL NOT NULL DEFAULT 0, password_changed TEXT NOT NULL, totp_secret TEXT NOT NULL DEFAULT '', totp_on INTEGER NOT NULL DEFAULT 0,
  totp_last INTEGER NOT NULL DEFAULT -1, expires TEXT NOT NULL DEFAULT '', hours TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
  lang TEXT NOT NULL DEFAULT '', history TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT 'gray', permissions TEXT NOT NULL DEFAULT '[]', builtin INTEGER NOT NULL DEFAULT 0, require_2fa INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL, last_seen REAL NOT NULL, ip TEXT NOT NULL DEFAULT '',
  agent TEXT NOT NULL DEFAULT '', limited INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, user TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '', ok INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS audit_at ON audit (at);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
PUBLIC_USER = ("id", "username", "display", "email", "telegram", "role_id", "active", "must_change", "created", "updated", "last_login", "failed",
               "password_changed", "totp_on", "expires", "notes", "lang")


class Accounts:
    def __init__(self, path: Path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            for ident, r in BUILTIN.items():
                db.execute("INSERT OR IGNORE INTO roles (id, name, description, color, permissions, builtin, created, updated) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                           (ident, r["name"], r["description"], r["color"], json.dumps(r["permissions"]), now_iso(), now_iso()))
            # The administrator role always has every permission, also those added by a newer version.
            db.execute("UPDATE roles SET permissions = ? WHERE id = ?", (json.dumps(sorted(ALL)), ADMIN_ROLE))

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

    # ---------- policy ----------

    def policy(self) -> dict:
        with self._db() as db:
            salvati = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key, value FROM config")}
        return {k: salvati.get(k, v) for k, v in POLICY_DEFAULTS.items()}

    def set_policy(self, valori: dict, by: str = "") -> dict:
        nuovi = {}
        for k, v in (valori or {}).items():
            if k not in POLICY_DEFAULTS or k == "enabled":
                raise AccountError(f"Unknown policy: {k}")
            if isinstance(POLICY_DEFAULTS[k], bool):
                if not isinstance(v, bool):
                    raise AccountError(f"{k} must be true or false.")
            else:
                minimo, massimo = POLICY_LIMITS[k]
                if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= massimo:
                    raise AccountError(f"{k} must be a number from {minimo} to {massimo}.")
            nuovi[k] = v
        self._config(nuovi)
        self.audit(by, "policy.change", "", json.dumps(nuovi))
        return self.policy()

    def _config(self, valori: dict) -> None:
        with self._db() as db:
            db.executemany("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                           [(k, json.dumps(v)) for k, v in valori.items()])

    @property
    def enabled(self) -> bool:
        return bool(self.policy()["enabled"])

    # ---------- turning accounts on and off ----------

    def setup(self, username: str, password: str, display: str = "") -> dict:
        """The first administrator; accounts are on from now."""
        if self.enabled:
            raise AccountError("Accounts are already on.", 409)
        with self._db() as db:
            esistente = db.execute("SELECT id FROM users WHERE role_id = ? AND active = 1", (ADMIN_ROLE,)).fetchone()
        utente = self.get_user(esistente["id"]) if esistente else self.create_user({"username": username, "display": display, "role_id": ADMIN_ROLE,
                                                                                    "password": password}, by=username or "setup")
        self._config({"enabled": True})
        self.audit(utente["username"], "accounts.on", "", "")
        return utente

    def disable(self, user: dict, password: str) -> None:
        if not self._verify_own_password(user["id"], password):
            raise AccountError("Wrong password.", 403)
        self._config({"enabled": False})
        with self._db() as db:
            db.execute("DELETE FROM sessions")
        self.audit(user["username"], "accounts.off", "", "")

    # ---------- roles ----------

    def roles(self) -> List[dict]:
        with self._db() as db:
            conti = {r["role_id"]: r["n"] for r in db.execute("SELECT role_id, COUNT(*) AS n FROM users GROUP BY role_id")}
            return [dict(self._role_row(r), users=conti.get(r["id"], 0)) for r in db.execute("SELECT * FROM roles ORDER BY builtin DESC, name")]

    @staticmethod
    def _role_row(r) -> dict:
        d = dict(r)
        d["permissions"] = json.loads(d["permissions"])
        d["builtin"], d["require_2fa"] = bool(d["builtin"]), bool(d["require_2fa"])
        d["locked"] = d["id"] == ADMIN_ROLE
        return d

    def get_role(self, role_id: str) -> dict:
        with self._db() as db:
            r = db.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
            if r is None:
                raise AccountError("Role not found.", 404)
            n = db.execute("SELECT COUNT(*) FROM users WHERE role_id = ?", (role_id,)).fetchone()[0]
        return dict(self._role_row(r), users=n)

    @staticmethod
    def _clean_role(dati: dict, parziale: bool = False) -> dict:
        pulito = {}
        if "name" in dati or not parziale:
            nome = str(dati.get("name") or "").strip()
            if not 2 <= len(nome) <= 40:
                raise AccountError("The role name has 2 to 40 characters.")
            pulito["name"] = nome
        if "description" in dati:
            pulito["description"] = str(dati["description"] or "").strip()[:200]
        if "color" in dati:
            if dati["color"] not in COLORS:
                raise AccountError("Unknown color.")
            pulito["color"] = dati["color"]
        if "permissions" in dati or not parziale:
            permessi = dati.get("permissions") or []
            if not isinstance(permessi, list) or any(p not in ALL for p in permessi):
                raise AccountError("Unknown permission: " + ", ".join(str(p) for p in permessi if p not in ALL)[:200] if isinstance(permessi, list) else "Invalid permissions.")
            pulito["permissions"] = sorted(set(permessi))
        if "require_2fa" in dati:
            pulito["require_2fa"] = 1 if dati["require_2fa"] else 0
        return pulito

    def create_role(self, dati: dict, by: str = "") -> dict:
        base = dati.get("base")
        if base:  # start from a role or a template
            modello = BUILTIN.get(base) or self.get_role(base)
            dati = dict({"permissions": modello["permissions"], "color": modello.get("color", "gray")}, **{k: v for k, v in dati.items() if k != "base"})
        pulito = self._clean_role(dati)
        ident = "r" + secrets.token_hex(5)
        try:
            with self._db() as db:
                db.execute("INSERT INTO roles (id, name, description, color, permissions, builtin, require_2fa, created, updated) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
                           (ident, pulito["name"], pulito.get("description", ""), pulito.get("color", "gray"), json.dumps(pulito["permissions"]),
                            pulito.get("require_2fa", 0), now_iso(), now_iso()))
        except sqlite3.IntegrityError:
            raise AccountError("A role with this name already exists.", 409) from None
        self.audit(by, "role.create", pulito["name"], f"{len(pulito['permissions'])} permissions")
        return self.get_role(ident)

    def update_role(self, role_id: str, dati: dict, by: str = "") -> dict:
        ruolo = self.get_role(role_id)
        if ruolo["locked"]:
            raise AccountError("The Administrator role cannot be changed.", 409)
        pulito = self._clean_role(dati, parziale=True)
        if not pulito:
            return ruolo
        if "permissions" in pulito and not self._admin_left(role_changes={role_id: pulito["permissions"]}):
            raise AccountError("At least one active user must keep the permission to manage users and roles.", 409)
        campi = {k: (json.dumps(v) if k == "permissions" else v) for k, v in pulito.items()}
        try:
            with self._db() as db:
                db.execute(f"UPDATE roles SET {', '.join(k + ' = ?' for k in campi)}, updated = ? WHERE id = ?", (*campi.values(), now_iso(), role_id))
        except sqlite3.IntegrityError:
            raise AccountError("A role with this name already exists.", 409) from None
        prima, dopo = set(ruolo["permissions"]), set(pulito.get("permissions", ruolo["permissions"]))
        self.audit(by, "role.update", ruolo["name"], json.dumps({"added": sorted(dopo - prima), "removed": sorted(prima - dopo),
                                                                 **{k: v for k, v in pulito.items() if k != "permissions"}})[:1000])
        return self.get_role(role_id)

    def copy_role(self, role_id: str, nome: str, by: str = "") -> dict:
        ruolo = self.get_role(role_id)
        return self.create_role({"name": nome or f"{ruolo['name']} (copy)", "description": ruolo["description"], "color": ruolo["color"],
                                 "permissions": ruolo["permissions"], "require_2fa": ruolo["require_2fa"]}, by)

    def delete_role(self, role_id: str, reassign: Optional[str] = None, by: str = "") -> dict:
        ruolo = self.get_role(role_id)
        if ruolo["builtin"]:
            raise AccountError("Built-in roles cannot be deleted: change them or reset them.", 409)
        if ruolo["users"]:
            if not reassign or reassign == role_id:
                raise AccountError(f"{ruolo['users']} users have this role: choose the role they move to.", 409)
            nuovo = self.get_role(reassign)
            with self._db() as db:
                db.execute("UPDATE users SET role_id = ?, updated = ? WHERE role_id = ?", (nuovo["id"], now_iso(), role_id))
        with self._db() as db:
            db.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        self.audit(by, "role.delete", ruolo["name"], f"users moved to {reassign}" if ruolo["users"] else "")
        return {"deleted": role_id, "moved": ruolo["users"]}

    def reset_role(self, role_id: str, by: str = "") -> dict:
        if role_id not in BUILTIN or role_id == ADMIN_ROLE:
            raise AccountError("Only the built-in roles can be reset.", 409)
        b = BUILTIN[role_id]
        return self.update_role(role_id, {"name": b["name"], "description": b["description"], "color": b["color"], "permissions": b["permissions"],
                                          "require_2fa": False}, by)

    def compare_roles(self, a: str, b: str) -> dict:
        ra, rb = self.get_role(a), self.get_role(b)
        pa, pb = set(ra["permissions"]), set(rb["permissions"])
        return {"a": ra["name"], "b": rb["name"], "only_a": sorted(pa - pb), "only_b": sorted(pb - pa), "both": sorted(pa & pb)}

    def export_role(self, role_id: str) -> dict:
        r = self.get_role(role_id)
        return {"format": "wmm-role/1", "name": r["name"], "description": r["description"], "color": r["color"], "permissions": r["permissions"],
                "require_2fa": r["require_2fa"]}

    def import_role(self, dati: dict, by: str = "") -> dict:
        if not isinstance(dati, dict) or dati.get("format") != "wmm-role/1":
            raise AccountError("Not a role exported by Windows Maintenance Manager.")
        ignoti = [p for p in dati.get("permissions", []) if p not in ALL]
        dati = dict(dati, permissions=[p for p in dati.get("permissions", []) if p in ALL])
        dati.pop("format", None)
        ruolo = self.create_role(dati, by)
        return dict(ruolo, skipped=ignoti)

    def templates(self) -> List[dict]:
        return [{"id": k, "name": v["name"], "description": v["description"], "permissions": v["permissions"]} for k, v in BUILTIN.items()]

    # ---------- users ----------

    def _user_row(self, r) -> dict:
        d = {k: r[k] for k in PUBLIC_USER}
        d["active"], d["must_change"], d["totp_on"] = bool(d["active"]), bool(d["must_change"]), bool(d["totp_on"])
        d["hours"] = json.loads(r["hours"]) if r["hours"] else None
        adesso = self.clock()
        d["locked"] = r["locked_until"] > adesso
        d["locked_until"] = now_iso(r["locked_until"]) if d["locked"] else None
        d["expired"] = bool(r["expires"]) and r["expires"] < date.fromtimestamp(adesso).isoformat()
        d["status"] = "disabled" if not d["active"] else "expired" if d["expired"] else "locked" if d["locked"] else "active"
        pol = self.policy()
        if pol["expiry_days"] and r["password_changed"]:
            scade = datetime.fromisoformat(r["password_changed"]) + timedelta(days=pol["expiry_days"])
            d["password_expires"] = scade.isoformat(timespec="seconds")
        return d

    def users(self, q: str = "", role: str = "", status: str = "") -> List[dict]:
        with self._db() as db:
            righe = db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
            sessioni = {r["user_id"]: r["n"] for r in db.execute("SELECT user_id, COUNT(*) AS n FROM sessions GROUP BY user_id")}
            nomi = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM roles")}
        elenco = []
        testo = (q or "").lower()
        for r in righe:
            u = self._user_row(r)
            u["role"] = nomi.get(u["role_id"], u["role_id"])
            u["sessions"] = sessioni.get(u["id"], 0)
            if testo and testo not in f"{u['username']} {u['display']} {u['email']}".lower():
                continue
            if (role and u["role_id"] != role) or (status and u["status"] != status):
                continue
            elenco.append(u)
        return elenco

    def get_user(self, user_id: str) -> dict:
        with self._db() as db:
            r = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if r is None:
            raise AccountError("User not found.", 404)
        u = self._user_row(r)
        u["role"] = self.get_role(u["role_id"])["name"]
        return u

    def _clean_user(self, dati: dict, parziale: bool) -> dict:
        pulito = {}
        if "username" in dati or not parziale:
            nome = str(dati.get("username") or "").strip()
            if not USERNAME.fullmatch(nome):
                raise AccountError("User name: 2 to 32 letters, digits, dots, dashes or underscores, starting with a letter or digit.")
            pulito["username"] = nome
        for campo, massimo in (("display", 80), ("notes", 500)):
            if campo in dati:
                pulito[campo] = str(dati[campo] or "").strip()[:massimo]
        if "email" in dati:
            email = str(dati["email"] or "").strip()
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                raise AccountError("The e-mail address is not valid.")
            pulito["email"] = email[:200]
        if "telegram" in dati:
            chat = str(dati["telegram"] or "").strip()
            if chat and not re.fullmatch(r"-?\d{3,20}|@[A-Za-z0-9_]{5,32}", chat):
                raise AccountError("Telegram: a chat ID (digits) or a @channel name.")
            pulito["telegram"] = chat
        if "role_id" in dati or not parziale:
            self.get_role(str(dati.get("role_id") or ""))
            pulito["role_id"] = dati["role_id"]
        if "active" in dati:
            pulito["active"] = 1 if dati["active"] else 0
        if "lang" in dati:
            if dati["lang"] not in ("", "it", "en"):
                raise AccountError("Language: it or en.")
            pulito["lang"] = dati["lang"]
        if "expires" in dati:
            scade = str(dati["expires"] or "")
            if scade and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", scade):
                raise AccountError("The expiry is a date (YYYY-MM-DD).")
            pulito["expires"] = scade
        if "hours" in dati:
            pulito["hours"] = json.dumps(self._clean_hours(dati["hours"])) if dati["hours"] else ""
        if "must_change" in dati:
            pulito["must_change"] = 1 if dati["must_change"] else 0
        return pulito

    @staticmethod
    def _clean_hours(ore) -> dict:
        if not isinstance(ore, dict):
            raise AccountError("Access hours: days and a time window.")
        giorni = ore.get("days")
        if not isinstance(giorni, list) or not giorni or any(g not in range(7) for g in giorni):
            raise AccountError("Access hours: choose at least one day.")
        da, a = str(ore.get("from", "")), str(ore.get("to", ""))
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", da) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", a) or da == a:
            raise AccountError("Access hours: a start and an end time (HH:MM), different.")
        return {"days": sorted(set(giorni)), "from": da, "to": a}

    def create_user(self, dati: dict, by: str = "") -> dict:
        pulito = self._clean_user(dati, parziale=False)
        password = dati.get("password") or ""
        temporanea = not password
        if temporanea:
            password = temporary_password()
        else:
            problemi = password_problems(password, self.policy(), pulito["username"])
            if problemi:
                raise AccountError("The password does not follow the rules: " + ", ".join(problemi) + ".")
        ident = "u" + secrets.token_hex(6)
        adesso = now_iso()
        try:
            with self._db() as db:
                campi = dict(pulito, id=ident, password=hash_password(password), created=adesso, updated=adesso, password_changed=adesso,
                             must_change=1 if temporanea or dati.get("must_change") else 0)
                db.execute(f"INSERT INTO users ({', '.join(campi)}) VALUES ({', '.join('?' * len(campi))})", tuple(campi.values()))
        except sqlite3.IntegrityError:
            raise AccountError("A user with this name already exists.", 409) from None
        self.audit(by, "user.create", pulito["username"], f"role {pulito['role_id']}")
        utente = self.get_user(ident)
        if temporanea:
            utente["temporary_password"] = password
        return utente

    def update_user(self, user_id: str, dati: dict, by: str = "") -> dict:
        utente = self.get_user(user_id)
        pulito = self._clean_user(dati, parziale=True)
        if not pulito:
            return utente
        disattiva = pulito.get("active") == 0 or ("role_id" in pulito and pulito["role_id"] != utente["role_id"])
        if disattiva and not self._admin_left(user_changes={user_id: pulito}):
            raise AccountError("At least one active user must keep the permission to manage users and roles.", 409)
        try:
            with self._db() as db:
                db.execute(f"UPDATE users SET {', '.join(k + ' = ?' for k in pulito)}, updated = ? WHERE id = ?", (*pulito.values(), now_iso(), user_id))
                if pulito.get("active") == 0:
                    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        except sqlite3.IntegrityError:
            raise AccountError("A user with this name already exists.", 409) from None
        self.audit(by, "user.update", utente["username"], json.dumps({k: v for k, v in pulito.items() if k != "notes"})[:500])
        return self.get_user(user_id)

    def delete_user(self, user_id: str, by: str = "", self_id: str = "") -> dict:
        utente = self.get_user(user_id)
        if user_id == self_id:
            raise AccountError("You cannot delete yourself.", 409)
        if not self._admin_left(user_changes={user_id: {"active": 0}}):
            raise AccountError("At least one active user must keep the permission to manage users and roles.", 409)
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.audit(by, "user.delete", utente["username"], "")
        return {"deleted": user_id}

    def copy_user(self, user_id: str, username: str, display: str = "", by: str = "") -> dict:
        """A new user with the same role, access hours, expiry, language and alert contacts; a new temporary password."""
        u = self.get_user(user_id)
        return self.create_user({"username": username, "display": display or "", "role_id": u["role_id"], "hours": u["hours"], "expires": u["expires"],
                                 "lang": u["lang"], "notes": f"Copied from {u['username']}"}, by)

    def reset_password(self, user_id: str, by: str = "") -> dict:
        u = self.get_user(user_id)
        password = temporary_password()
        with self._db() as db:
            db.execute("UPDATE users SET password = ?, must_change = 1, failed = 0, locked_until = 0, password_changed = ?, updated = ? WHERE id = ?",
                       (hash_password(password), now_iso(), now_iso(), user_id))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        self.audit(by, "user.password_reset", u["username"], "")
        return {"temporary_password": password}

    def unlock(self, user_id: str, by: str = "") -> dict:
        u = self.get_user(user_id)
        with self._db() as db:
            db.execute("UPDATE users SET failed = 0, locked_until = 0 WHERE id = ?", (user_id,))
        self.audit(by, "user.unlock", u["username"], "")
        return self.get_user(user_id)

    def reset_2fa(self, user_id: str, by: str = "") -> dict:
        u = self.get_user(user_id)
        with self._db() as db:
            db.execute("UPDATE users SET totp_secret = '', totp_on = 0, totp_last = -1 WHERE id = ?", (user_id,))
        self.audit(by, "user.2fa_reset", u["username"], "")
        return self.get_user(user_id)

    def bulk(self, ids: Sequence[str], azione: str, valore=None, by: str = "", self_id: str = "") -> dict:
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            raise AccountError("Choose the users first.")
        fatti, errori = 0, []
        for ident in ids:
            try:
                if azione == "enable":
                    self.update_user(ident, {"active": True}, by)
                elif azione == "disable":
                    if ident == self_id:
                        raise AccountError("You cannot disable yourself.")
                    self.update_user(ident, {"active": False}, by)
                elif azione == "role":
                    self.update_user(ident, {"role_id": valore}, by)
                elif azione == "delete":
                    self.delete_user(ident, by, self_id)
                elif azione == "unlock":
                    self.unlock(ident, by)
                elif azione == "signout":
                    self.revoke_user_sessions(ident, by)
                elif azione == "must_change":
                    self.update_user(ident, {"must_change": True}, by)
                elif azione == "expires":
                    self.update_user(ident, {"expires": valore or ""}, by)
                else:
                    raise AccountError("Unknown action.")
                fatti += 1
            except AccountError as errore:
                errori.append({"id": ident, "error": str(errore)})
        return {"done": fatti, "errors": errori}

    def export_users(self) -> str:
        uscita = io.StringIO()
        w = csv.writer(uscita)
        w.writerow(["username", "display", "email", "telegram", "role", "active", "expires", "last_login", "two_step", "status"])
        for u in self.users():
            w.writerow([u["username"], u["display"], u["email"], u["telegram"], u["role"], "1" if u["active"] else "0", u["expires"],
                        u["last_login"] or "", "1" if u["totp_on"] else "0", u["status"]])
        return uscita.getvalue()

    def import_users(self, testo: str, by: str = "") -> dict:
        """CSV with a header: username, display, email, telegram, role (name or id), active. Every new user gets a temporary password."""
        if not isinstance(testo, str) or len(testo) > 500_000:
            raise AccountError("The file is too large.")
        ruoli = {r["name"].lower(): r["id"] for r in self.roles()} | {r["id"]: r["id"] for r in self.roles()}
        creati, saltati = [], []
        for riga in csv.DictReader(io.StringIO(testo.lstrip("\ufeff"))):
            nome = (riga.get("username") or "").strip()
            ruolo = ruoli.get((riga.get("role") or "viewer").strip().lower())
            try:
                if not ruolo:
                    raise AccountError(f"unknown role {riga.get('role')}")
                u = self.create_user({"username": nome, "display": riga.get("display", ""), "email": riga.get("email", ""), "telegram": riga.get("telegram", ""),
                                      "role_id": ruolo, "active": (riga.get("active") or "1").strip() not in ("0", "no", "false")}, by)
                creati.append({"username": u["username"], "temporary_password": u["temporary_password"]})
            except AccountError as errore:
                saltati.append({"username": nome, "error": str(errore)})
        return {"created": creati, "skipped": saltati}

    def _admin_left(self, user_changes: Optional[dict] = None, role_changes: Optional[dict] = None) -> bool:
        """After the change, is there still an active user whose role can manage users and roles?"""
        user_changes, role_changes = user_changes or {}, role_changes or {}
        with self._db() as db:
            ruoli = {r["id"]: set(json.loads(r["permissions"])) for r in db.execute("SELECT id, permissions FROM roles")}
            utenti = db.execute("SELECT id, role_id, active, expires FROM users").fetchall()
        ruoli.update({k: set(v) for k, v in role_changes.items()})
        if not utenti:
            return True
        oggi = date.fromtimestamp(self.clock()).isoformat()
        for u in utenti:
            c = user_changes.get(u["id"], {})
            attivo = c.get("active", u["active"])
            ruolo = c.get("role_id", u["role_id"])
            if attivo and not (u["expires"] and u["expires"] < oggi) and {"users.manage", "roles.manage"} <= ruoli.get(ruolo, set()):
                return True
        return False

    # ---------- signing in ----------

    def _within_hours(self, ore: Optional[dict], t: float) -> bool:
        if not ore:
            return True
        momento = datetime.fromtimestamp(t)
        ora = momento.strftime("%H:%M")
        if ore["from"] < ore["to"]:
            return momento.weekday() in ore["days"] and ore["from"] <= ora < ore["to"]
        # A window across midnight (22:00-06:00) belongs to the day it starts.
        if ora >= ore["from"]:
            return momento.weekday() in ore["days"]
        return ora < ore["to"] and (momento.weekday() - 1) % 7 in ore["days"]

    def login(self, username: str, password: str, code: str = "", ip: str = "", agent: str = "") -> dict:
        pol = self.policy()
        if not pol["enabled"]:
            raise AccountError("Accounts are off.", 409)
        adesso = self.clock()
        with self._db() as db:
            r = db.execute("SELECT * FROM users WHERE username = ?", (str(username or "").strip(),)).fetchone()
        if r is None:
            check_password(password or "", _dummy_hash())  # the same time as a real check: names cannot be guessed by timing
            self.audit(str(username)[:32], "login.fail", "", "unknown user", ok=False)
            raise AccountError("Wrong user name or password.", 401)
        if r["locked_until"] > adesso:
            self.audit(r["username"], "login.locked", "", "", ok=False)
            raise AccountError(f"Too many wrong passwords: try again after {now_iso(r['locked_until'])[11:16]}.", 423)
        if not check_password(password or "", r["password"]):
            falliti = r["failed"] + 1
            blocco = adesso + pol["lockout_minutes"] * 60 if falliti >= pol["lockout_attempts"] else 0
            with self._db() as db:
                db.execute("UPDATE users SET failed = ?, locked_until = ? WHERE id = ?", (0 if blocco else falliti, blocco, r["id"]))
            self.audit(r["username"], "login.fail", "", "locked" if blocco else f"attempt {falliti}", ok=False)
            raise AccountError("Wrong user name or password.", 401)
        u = self._user_row(r)
        if not u["active"]:
            self.audit(r["username"], "login.denied", "", "disabled", ok=False)
            raise AccountError("This account is disabled.", 403)
        if u["expired"]:
            self.audit(r["username"], "login.denied", "", "expired", ok=False)
            raise AccountError("This account has expired.", 403)
        if not self._within_hours(u["hours"], adesso):
            self.audit(r["username"], "login.denied", "", "outside access hours", ok=False)
            raise AccountError("This account cannot sign in at this time.", 403)
        if r["totp_on"]:
            if not code:
                raise AccountError("Type the 6-digit code of your authenticator app.", 428)
            passo = totp_match(notify.unprotect(r["totp_secret"]), code, adesso, r["totp_last"])
            if passo is None:
                falliti = r["failed"] + 1
                with self._db() as db:
                    db.execute("UPDATE users SET failed = ? WHERE id = ?", (falliti, r["id"]))
                self.audit(r["username"], "login.fail", "", "wrong code", ok=False)
                raise AccountError("Wrong or already used code.", 401)
            with self._db() as db:
                db.execute("UPDATE users SET totp_last = ? WHERE id = ?", (passo, r["id"]))
        limitata = bool(r["must_change"]) or "password_expires" in u and u["password_expires"] < now_iso(adesso)
        serve_2fa = self._needs_2fa(r["role_id"], bool(r["totp_on"]))
        token = secrets.token_hex(24)
        with self._db() as db:
            if pol["single_session"]:
                db.execute("DELETE FROM sessions WHERE user_id = ?", (r["id"],))
            db.execute("INSERT INTO sessions (id, user_id, created, last_seen, ip, agent, limited) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (_hash_token(token), r["id"], adesso, adesso, ip[:64], agent[:200], 1 if (limitata or serve_2fa) else 0))
            db.execute("UPDATE users SET failed = 0, locked_until = 0, last_login = ? WHERE id = ?", (now_iso(adesso), r["id"]))
        self.audit(r["username"], "login.ok", "", ip)
        return {"token": token, "user": self.get_user(r["id"]), "must_change": limitata, "must_enroll_2fa": serve_2fa}

    def session(self, token: str) -> Optional[dict]:
        """The user of a session token, with the permissions of the role; None when unknown, idle too long or too old."""
        if not token or not re.fullmatch(r"[0-9a-f]{48}", token):
            return None
        pol = self.policy()
        adesso = self.clock()
        with self._db() as db:
            s = db.execute("SELECT * FROM sessions WHERE id = ?", (_hash_token(token),)).fetchone()
            if s is None:
                return None
            if adesso - s["last_seen"] > pol["idle_minutes"] * 60 or adesso - s["created"] > pol["max_hours"] * 3600:
                db.execute("DELETE FROM sessions WHERE id = ?", (s["id"],))
                return None
            r = db.execute("SELECT * FROM users WHERE id = ?", (s["user_id"],)).fetchone()
            if r is None:
                return None
            if adesso - s["last_seen"] > 30:
                db.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (adesso, s["id"]))
        u = self._user_row(r)
        if not u["active"] or u["expired"] or not self._within_hours(u["hours"], adesso):
            return None
        ruolo = self.get_role(u["role_id"])
        return dict(u, role=ruolo["name"], permissions=sorted(ruolo["permissions"]), limited=bool(s["limited"]), session=s["id"])

    def _needs_2fa(self, role_id: str, totp_on: bool) -> bool:
        ruolo = self.get_role(role_id)
        return not totp_on and (ruolo["require_2fa"] or (self.policy()["require_2fa_admins"] and "users.manage" in ruolo["permissions"]))

    def logout(self, token: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE id = ?", (_hash_token(token or ""),))

    def sessions(self, user_id: Optional[str] = None) -> List[dict]:
        with self._db() as db:
            righe = db.execute("SELECT s.*, u.username FROM sessions s JOIN users u ON u.id = s.user_id" + (" WHERE s.user_id = ?" if user_id else "") +
                               " ORDER BY s.last_seen DESC", (user_id,) if user_id else ()).fetchall()
        return [{"id": r["id"][:16], "user_id": r["user_id"], "username": r["username"], "created": now_iso(r["created"]), "last_seen": now_iso(r["last_seen"]),
                 "ip": r["ip"], "agent": r["agent"], "limited": bool(r["limited"])} for r in righe]

    def revoke_session(self, prefix: str, by: str = "", only_user: Optional[str] = None) -> int:
        if not re.fullmatch(r"[0-9a-f]{16}", prefix or ""):
            raise AccountError("Session not found.", 404)
        with self._db() as db:
            q, p = "DELETE FROM sessions WHERE id LIKE ?", [prefix + "%"]
            if only_user:
                q, p = q + " AND user_id = ?", p + [only_user]
            n = db.execute(q, p).rowcount
        if not n:
            raise AccountError("Session not found.", 404)
        self.audit(by, "session.revoke", prefix, "")
        return n

    def revoke_user_sessions(self, user_id: str, by: str = "", keep: str = "") -> int:
        u = self.get_user(user_id)
        with self._db() as db:
            n = db.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, keep)).rowcount
        self.audit(by, "session.revoke_all", u["username"], str(n))
        return n

    # ---------- self-service ----------

    def _verify_own_password(self, user_id: str, password: str) -> bool:
        with self._db() as db:
            r = db.execute("SELECT password FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(r) and check_password(password or "", r["password"])

    def change_password(self, user: dict, vecchia: str, nuova: str) -> dict:
        if not self._verify_own_password(user["id"], vecchia):
            self.audit(user["username"], "password.change", "", "wrong current password", ok=False)
            raise AccountError("The current password is wrong.", 403)
        pol = self.policy()
        problemi = password_problems(nuova, pol, user["username"])
        with self._db() as db:
            r = db.execute("SELECT password, history FROM users WHERE id = ?", (user["id"],)).fetchone()
        precedenti = [r["password"]] + json.loads(r["history"] or "[]")
        if any(check_password(nuova or "", h) for h in precedenti[:max(1, pol["history"])]):
            problemi.append("different from your last passwords")
        if problemi:
            raise AccountError("The new password does not follow the rules: " + ", ".join(problemi) + ".")
        with self._db() as db:
            db.execute("UPDATE users SET password = ?, history = ?, must_change = 0, password_changed = ?, updated = ? WHERE id = ?",
                       (hash_password(nuova), json.dumps(precedenti[:pol["history"]]), now_iso(), now_iso(), user["id"]))
            db.execute("UPDATE sessions SET limited = ? WHERE user_id = ? AND id = ?",
                       (1 if self._needs_2fa(user["role_id"], bool(user.get("totp_on"))) else 0, user["id"], user.get("session", "")))
            db.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user["id"], user.get("session", "")))
        self.audit(user["username"], "password.change", "", "")
        return self.get_user(user["id"])

    def update_profile(self, user: dict, dati: dict) -> dict:
        permessi = {k: dati[k] for k in ("display", "email", "telegram", "lang") if k in dati}
        return self.update_user(user["id"], permessi, by=user["username"])

    def totp_begin(self, user: dict) -> dict:
        segreto = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        with self._db() as db:
            db.execute("UPDATE users SET totp_secret = ?, totp_on = 0, totp_last = -1 WHERE id = ?", (notify.protect(segreto), user["id"]))
        etichetta = f"WMM:{user['username']}"
        return {"secret": segreto, "uri": f"otpauth://totp/{etichetta}?secret={segreto}&issuer=Windows%20Maintenance%20Manager&digits=6&period=30"}

    def totp_confirm(self, user: dict, code: str) -> dict:
        with self._db() as db:
            r = db.execute("SELECT totp_secret FROM users WHERE id = ?", (user["id"],)).fetchone()
        segreto = notify.unprotect(r["totp_secret"]) if r and r["totp_secret"] else ""
        passo = totp_match(segreto, code, self.clock()) if segreto else None
        if passo is None:
            raise AccountError("The code does not match: check the time of the phone and try the next code.")
        with self._db() as db:
            db.execute("UPDATE users SET totp_on = 1, totp_last = ? WHERE id = ?", (passo, user["id"]))
            db.execute("UPDATE sessions SET limited = 0 WHERE user_id = ? AND id = ? AND ? = 0", (user["id"], user.get("session", ""), 1 if user.get("must_change") else 0))
        self.audit(user["username"], "2fa.on", "", "")
        return self.get_user(user["id"])

    def totp_disable(self, user: dict, password: str) -> dict:
        if not self._verify_own_password(user["id"], password):
            raise AccountError("Wrong password.", 403)
        ruolo = self.get_role(user["role_id"])
        if ruolo["require_2fa"]:
            raise AccountError("Your role requires two-step verification.", 409)
        return self.reset_2fa(user["id"], by=user["username"])

    # ---------- audit ----------

    def audit(self, user: str, action: str, target: str = "", detail: str = "", ok: bool = True) -> None:
        try:
            with self._db() as db:
                db.execute("INSERT INTO audit (at, user, action, target, detail, ok) VALUES (?, ?, ?, ?, ?, ?)",
                           (now_iso(self.clock()), str(user or "")[:64], action[:64], str(target)[:200], str(detail)[:2000], 1 if ok else 0))
        except sqlite3.Error:
            pass  # the audit log never blocks the action it records

    def audit_list(self, user: str = "", action: str = "", since: str = "", until: str = "", q: str = "", failed: bool = False,
                   limit: int = 200, offset: int = 0) -> dict:
        condizioni, parametri = [], []
        if user:
            condizioni.append("user = ?")
            parametri.append(user)
        if action:
            condizioni.append("action LIKE ?")
            parametri.append(action.replace("%", "") + "%")
        if since:
            condizioni.append("at >= ?")
            parametri.append(since)
        if until:
            condizioni.append("at <= ?")
            parametri.append(until + ("T23:59:59" if len(until) == 10 else ""))
        if q:
            condizioni.append("(target LIKE ? OR detail LIKE ? OR user LIKE ?)")
            parametri += ["%" + q.replace("%", "") + "%"] * 3
        if failed:
            condizioni.append("ok = 0")
        dove = (" WHERE " + " AND ".join(condizioni)) if condizioni else ""
        with self._db() as db:
            totale = db.execute("SELECT COUNT(*) FROM audit" + dove, parametri).fetchone()[0]
            righe = db.execute("SELECT * FROM audit" + dove + " ORDER BY id DESC LIMIT ? OFFSET ?", parametri + [max(1, min(limit, 2000)), max(0, offset)]).fetchall()
        return {"total": total_or(totale), "entries": [dict(r, ok=bool(r["ok"])) for r in righe]}

    def audit_csv(self, **filtri) -> str:
        uscita = io.StringIO()
        w = csv.writer(uscita)
        w.writerow(["at", "user", "action", "target", "detail", "ok"])
        for e in reversed(self.audit_list(limit=2000, **filtri)["entries"]):
            w.writerow([e["at"], e["user"], e["action"], e["target"], e["detail"], "1" if e["ok"] else "0"])
        return uscita.getvalue()

    def audit_prune(self) -> int:
        limite = (datetime.fromtimestamp(self.clock()) - timedelta(days=self.policy()["audit_days"])).isoformat(timespec="seconds")
        with self._db() as db:
            return db.execute("DELETE FROM audit WHERE at < ?", (limite,)).rowcount

    def login_history(self, username: str, limit: int = 50) -> List[dict]:
        with self._db() as db:
            righe = db.execute("SELECT * FROM audit WHERE user = ? AND action LIKE 'login.%' ORDER BY id DESC LIMIT ?", (username, limit)).fetchall()
        return [dict(r, ok=bool(r["ok"])) for r in righe]

    def overview(self) -> dict:
        utenti = self.users()
        giorno = (datetime.fromtimestamp(self.clock()) - timedelta(days=1)).isoformat(timespec="seconds")
        with self._db() as db:
            falliti = db.execute("SELECT COUNT(*) FROM audit WHERE action LIKE 'login.%' AND ok = 0 AND at >= ?", (giorno,)).fetchone()[0]
        return {"users": len(utenti), "active": sum(u["status"] == "active" for u in utenti), "locked": sum(u["status"] == "locked" for u in utenti),
                "disabled": sum(u["status"] == "disabled" for u in utenti), "two_step": sum(u["totp_on"] for u in utenti),
                "sessions": len(self.sessions()), "roles": len(self.roles()), "failed_24h": falliti}


def total_or(n) -> int:
    return int(n or 0)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _dummy_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_hex(8))
    return _DUMMY


def has(user: Optional[dict], permesso: str) -> bool:
    return bool(user) and permesso in user.get("permissions", ())


def can_run(user: Optional[dict], action) -> bool:
    """A tool of the catalog, for a user: its area and its risk level ("report" for read-only ones)."""
    if action.id.startswith("custom."):
        return has(user, "run.custom")
    livello = "report" if action.kind == "report" else action.risk
    return has(user, f"run.{action.area}.{livello}")


def for_data_dir(data_dir: Path) -> Accounts:
    return Accounts(Path(data_dir) / "accounts.db")
