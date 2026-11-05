"""The central server (2.10). One PC runs the server; every other PC runs an agent that contacts it (so it works also
from branches and laptops outside the office, behind NAT): it sends its summary and inventory, receives the jobs
queued for it, runs them and sends back the results.

Security: HTTPS with the server's self-signed certificate, pinned by its SHA-256 fingerprint; enrollment with a
one-time code (24 hours) that carries the server address and fingerprint and whose secret part never travels: the
enrollment request is signed with it. Each agent then gets its own secret; every request is signed (HMAC-SHA256 with
time and nonce, like the PCs of the network). What an agent accepts is decided on that PC (Settings: reports, safe
fixes, or everything the server sends), never by the server.

Server data: dati\\central.db (agents, jobs, groups, assets, software catalog, update rings). Agent data:
dati\\central_client.json (server, fingerprint, agent id, secret encrypted with DPAPI)."""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

from . import notify, securestore
from .fleet import MAX_SKEW, signature

DEFAULT_PORT = 8770
API = "/central/v1"
SIG, TIME, NONCE, AGENT = "X-WMM-Sig", "X-WMM-Time", "X-WMM-Nonce", "X-WMM-Agent"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
JOB_KINDS = ("actions", "winget", "policy", "baseline", "inventory")
LEVELS = ("reports", "safe", "all")
OFFLINE_MINUTES = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, hostname TEXT NOT NULL, machine_id TEXT NOT NULL, secret TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
  enrolled TEXT NOT NULL, last_seen TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '', level TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '{}', inventory TEXT NOT NULL DEFAULT '{}', inventory_at TEXT NOT NULL DEFAULT '', ring TEXT NOT NULL DEFAULT '',
  compliance TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  created TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', sent TEXT NOT NULL DEFAULT '', finished TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}',
  batch TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS jobs_agent ON jobs (agent_id, status);
CREATE TABLE IF NOT EXISTS enroll (id TEXT PRIMARY KEY, secret TEXT NOT NULL, expires REAL NOT NULL, tags TEXT NOT NULL DEFAULT '[]', used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT NOT NULL DEFAULT '', ring TEXT NOT NULL DEFAULT '',
  maint TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS assets (agent_id TEXT PRIMARY KEY, asset_tag TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
  purchased TEXT NOT NULL DEFAULT '', warranty_until TEXT NOT NULL DEFAULT '', licenses TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY, winget_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', required INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rings (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, quality_days INTEGER NOT NULL DEFAULT 0,
  feature_days INTEGER NOT NULL DEFAULT 0, target_version TEXT NOT NULL DEFAULT '', paused_until TEXT NOT NULL DEFAULT '', active_hours TEXT NOT NULL DEFAULT '8-18');
"""


class CentralError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ======================================================================= server

class Server:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "central.db"
        self._lock = threading.RLock()
        self._seen: Dict[str, float] = {}
        with self._db() as db:
            db.executescript(SCHEMA)

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

    # ---------- enrollment ----------

    def enrollment_code(self, host: str, porta: int, fingerprint: str, tags: Optional[List[str]] = None) -> dict:
        """One-time, 24 hours: wmm://host:port/ID-SECRET#FINGERPRINT. Only ID travels; SECRET signs the request."""
        ident = "".join(secrets.choice(ALPHABET) for _ in range(6))
        segreto = "".join(secrets.choice(ALPHABET) for _ in range(20))
        with self._db() as db:
            db.execute("DELETE FROM enroll WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO enroll (id, secret, expires, tags) VALUES (?, ?, ?, ?)",
                       (ident, notify.protect(segreto), time.time() + 86400, json.dumps(tags or [])))
        fp = fingerprint.replace(":", "")
        return {"code": f"wmm://{host}:{int(porta)}/{ident}-{segreto}#{fp}", "expires": (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")}

    def enroll(self, ident: str, istante: str, nonce: str, corpo: bytes, firma: str, ip: str = "") -> dict:
        with self._db() as db:
            r = db.execute("SELECT * FROM enroll WHERE id = ?", (ident,)).fetchone()
        if r is None or r["used"] or r["expires"] < time.time():
            raise CentralError("The enrollment code is not valid or has expired.", 403)
        segreto = notify.unprotect(r["secret"])
        if not self._fresh(istante, nonce) or not hmac.compare_digest(signature(segreto, "POST", API + "/enroll", istante, nonce, corpo), firma or ""):
            raise CentralError("Wrong enrollment code.", 403)
        dati = json.loads(corpo.decode("utf-8"))
        hostname = str(dati.get("hostname", ""))[:64]
        machine = str(dati.get("machine_id", ""))[:80]
        agent_id, agent_secret = "a" + secrets.token_hex(8), secrets.token_hex(32)
        with self._db() as db:
            db.execute("UPDATE enroll SET used = 1 WHERE id = ?", (ident,))
            vecchio = db.execute("SELECT id FROM agents WHERE machine_id = ?", (machine,)).fetchone()
            if vecchio:  # the same PC enrolled again (reinstalled): replace its secret, keep its history
                agent_id = vecchio["id"]
                db.execute("UPDATE agents SET secret = ?, hostname = ?, ip = ? WHERE id = ?", (notify.protect(agent_secret), hostname, ip, agent_id))
            else:
                db.execute("INSERT INTO agents (id, hostname, machine_id, secret, tags, enrolled, ip) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (agent_id, hostname, machine, notify.protect(agent_secret), r["tags"], now(), ip))
        return {"agent_id": agent_id, "secret": agent_secret}

    def _fresh(self, istante: str, nonce: str) -> bool:
        adesso = time.time()
        try:
            if abs(adesso - float(istante)) > MAX_SKEW:
                return False
        except (TypeError, ValueError):
            return False
        if not (8 <= len(nonce or "") <= 64):
            return False
        with self._lock:
            for vecchio in [n for n, t in self._seen.items() if adesso - t > 2 * MAX_SKEW]:
                del self._seen[vecchio]
            if nonce in self._seen:
                return False
            self._seen[nonce] = adesso
        return True

    def authenticate(self, agent_id: str, metodo: str, percorso: str, istante: str, nonce: str, corpo: bytes, firma: str) -> Optional[dict]:
        with self._db() as db:
            r = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id or "",)).fetchone()
        if r is None:
            return None
        segreto = notify.unprotect(r["secret"])
        if not segreto or not hmac.compare_digest(signature(segreto, metodo, percorso, istante, nonce, corpo), firma or ""):
            return None
        if not self._fresh(istante, nonce):
            return None
        return dict(r)

    # ---------- heartbeat ----------

    def heartbeat(self, agent: dict, dati: dict, ip: str = "") -> dict:
        """Stores what the agent sent and hands it the jobs queued for it, with its update ring."""
        risultati = dati.get("results") if isinstance(dati.get("results"), list) else []
        with self._db() as db:
            campi = {"last_seen": now(), "ip": ip[:64], "version": str(dati.get("version", ""))[:20], "level": str(dati.get("level", ""))[:10]}
            if isinstance(dati.get("summary"), dict):
                campi["summary"] = json.dumps(dati["summary"])[:200_000]
            if isinstance(dati.get("inventory"), dict):
                campi["inventory"] = json.dumps(dati["inventory"])[:2_000_000]
                campi["inventory_at"] = now()
            if isinstance(dati.get("compliance"), dict):
                campi["compliance"] = json.dumps(dati["compliance"])[:200_000]
            db.execute(f"UPDATE agents SET {', '.join(k + ' = ?' for k in campi)} WHERE id = ?", (*campi.values(), agent["id"]))
            for r in risultati[:100]:
                if isinstance(r, dict) and isinstance(r.get("job_id"), int):
                    db.execute("UPDATE jobs SET status = ?, finished = ?, result = ? WHERE id = ? AND agent_id = ?",
                               ("done" if r.get("status") == "done" else "error", now(), json.dumps(r.get("result", {}))[:200_000], r["job_id"], agent["id"]))
            lavori = db.execute("SELECT id, kind, payload FROM jobs WHERE agent_id = ? AND status = 'queued' ORDER BY id LIMIT 20", (agent["id"],)).fetchall()
            for j in lavori:
                db.execute("UPDATE jobs SET status = 'sent', sent = ? WHERE id = ?", (now(), j["id"]))
            anello = None
            riga = db.execute("SELECT ring FROM agents WHERE id = ?", (agent["id"],)).fetchone()
            if riga and riga["ring"]:
                r = db.execute("SELECT * FROM rings WHERE id = ?", (riga["ring"],)).fetchone()
                anello = dict(r) if r else None
        return {"jobs": [{"job_id": j["id"], "kind": j["kind"], "payload": json.loads(j["payload"])} for j in lavori], "ring": anello, "server_time": now()}

    # ---------- management (from the console of the server PC) ----------

    def agents(self, tag: str = "", q: str = "") -> List[dict]:
        limite = (datetime.now() - timedelta(minutes=OFFLINE_MINUTES)).isoformat(timespec="seconds")
        with self._db() as db:
            righe = db.execute("SELECT a.*, s.asset_tag, s.owner, s.location, s.warranty_until FROM agents a LEFT JOIN assets s ON s.agent_id = a.id ORDER BY hostname").fetchall()
            in_coda = {r["agent_id"]: r["n"] for r in db.execute("SELECT agent_id, COUNT(*) AS n FROM jobs WHERE status IN ('queued', 'sent') GROUP BY agent_id")}
        elenco = []
        for r in righe:
            tags = json.loads(r["tags"])
            if tag and tag not in tags:
                continue
            if q and q.lower() not in f"{r['hostname']} {r['ip']} {r['asset_tag'] or ''} {r['owner'] or ''}".lower():
                continue
            s = json.loads(r["summary"] or "{}")
            comp = json.loads(r["compliance"] or "{}")
            elenco.append({"id": r["id"], "hostname": r["hostname"], "tags": tags, "enrolled": r["enrolled"], "last_seen": r["last_seen"], "ip": r["ip"],
                           "version": r["version"], "level": r["level"], "online": bool(r["last_seen"]) and r["last_seen"] >= limite,
                           "overall": s.get("overall"), "open_issues": s.get("open_issues"), "c_free_gb": s.get("c_free_gb"), "ring": r["ring"],
                           "compliance": comp.get("percent"), "queued": in_coda.get(r["id"], 0), "inventory_at": r["inventory_at"],
                           "asset_tag": r["asset_tag"] or "", "owner": r["owner"] or "", "location": r["location"] or "", "warranty_until": r["warranty_until"] or ""})
        return elenco

    def agent(self, agent_id: str) -> dict:
        with self._db() as db:
            r = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if r is None:
                raise CentralError("PC not found.", 404)
            a = db.execute("SELECT * FROM assets WHERE agent_id = ?", (agent_id,)).fetchone()
            jobs = db.execute("SELECT * FROM jobs WHERE agent_id = ? ORDER BY id DESC LIMIT 50", (agent_id,)).fetchall()
        d = {k: r[k] for k in r.keys() if k != "secret"}
        for k in ("tags", "summary", "inventory", "compliance"):
            d[k] = json.loads(d[k] or ("[]" if k == "tags" else "{}"))
        d["asset"] = dict(a) if a else {}
        d["jobs"] = [self._job(j) for j in jobs]
        return d

    def remove(self, agent_id: str) -> None:
        with self._db() as db:
            if not db.execute("DELETE FROM agents WHERE id = ?", (agent_id,)).rowcount:
                raise CentralError("PC not found.", 404)
            db.execute("DELETE FROM jobs WHERE agent_id = ?", (agent_id,))
            db.execute("DELETE FROM assets WHERE agent_id = ?", (agent_id,))

    def set_tags(self, agent_id: str, tags) -> List[str]:
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or not re.fullmatch(r"[\w .\-]{1,40}", t) for t in tags):
            raise CentralError("Groups: up to 20 names of letters, digits, spaces, dots or dashes.")
        pulite = sorted({t.strip() for t in tags if t.strip()})
        with self._db() as db:
            if not db.execute("UPDATE agents SET tags = ? WHERE id = ?", (json.dumps(pulite), agent_id)).rowcount:
                raise CentralError("PC not found.", 404)
        return pulite

    def set_asset(self, agent_id: str, dati: dict) -> dict:
        campi = {"asset_tag": 40, "owner": 80, "location": 80, "purchased": 10, "warranty_until": 10, "licenses": 1000, "notes": 1000}
        valori = {k: str(dati.get(k, "") or "")[:m] for k, m in campi.items()}
        for k in ("purchased", "warranty_until"):
            if valori[k] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valori[k]):
                raise CentralError("Dates as YYYY-MM-DD.")
        self.agent(agent_id)
        with self._db() as db:
            db.execute("INSERT INTO assets (agent_id, " + ", ".join(campi) + ") VALUES (?" + ", ?" * len(campi) + ") ON CONFLICT(agent_id) DO UPDATE SET " +
                       ", ".join(f"{k} = excluded.{k}" for k in campi), (agent_id, *valori.values()))
        return valori

    def groups(self) -> List[dict]:
        conti: Dict[str, int] = {}
        for a in self.agents():
            for t in a["tags"]:
                conti[t] = conti.get(t, 0) + 1
        with self._db() as db:
            definiti = {r["name"]: dict(r) for r in db.execute("SELECT * FROM groups")}
        nomi = sorted(set(conti) | set(definiti))
        return [dict(definiti.get(n, {"id": "", "name": n, "description": "", "ring": "", "maint": ""}), members=conti.get(n, 0)) for n in nomi]

    def save_group(self, dati: dict) -> dict:
        nome = str(dati.get("name", "")).strip()
        if not re.fullmatch(r"[\w .\-]{1,40}", nome):
            raise CentralError("Group name: letters, digits, spaces, dots or dashes (1-40).")
        anello = str(dati.get("ring", ""))
        if anello and anello not in {r["id"] for r in self.rings()}:
            raise CentralError("Unknown update ring.")
        with self._db() as db:
            db.execute("INSERT INTO groups (id, name, description, ring) VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET description = excluded.description, ring = excluded.ring",
                       ("g" + secrets.token_hex(5), nome, str(dati.get("description", ""))[:200], anello))
            if anello:  # the ring of a group applies to its members
                for a in db.execute("SELECT id, tags FROM agents").fetchall():
                    if nome in json.loads(a["tags"]):
                        db.execute("UPDATE agents SET ring = ? WHERE id = ?", (anello, a["id"]))
        return next(g for g in self.groups() if g["name"] == nome)

    def delete_group(self, nome: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM groups WHERE name = ?", (nome,))
            for a in db.execute("SELECT id, tags FROM agents").fetchall():
                tags = json.loads(a["tags"])
                if nome in tags:
                    db.execute("UPDATE agents SET tags = ? WHERE id = ?", (json.dumps([t for t in tags if t != nome]), a["id"]))

    def targets(self, agenti=None, gruppo: str = "") -> List[str]:
        if gruppo:
            return [a["id"] for a in self.agents(tag=gruppo)]
        noti = {a["id"] for a in self.agents()}
        return [a for a in (agenti or []) if a in noti]

    def queue(self, destinatari: List[str], kind: str, payload: dict, by: str = "") -> dict:
        if kind not in JOB_KINDS:
            raise CentralError("Unknown job kind.")
        if not destinatari:
            raise CentralError("Choose at least one PC or a group.")
        lotto = secrets.token_hex(6)
        with self._db() as db:
            for a in destinatari:
                db.execute("INSERT INTO jobs (agent_id, kind, payload, created, created_by, batch) VALUES (?, ?, ?, ?, ?, ?)",
                           (a, kind, json.dumps(payload), now(), by, lotto))
        return {"batch": lotto, "queued": len(destinatari)}

    @staticmethod
    def _job(j) -> dict:
        d = dict(j)
        d["payload"], d["result"] = json.loads(d["payload"]), json.loads(d["result"] or "{}")
        return d

    def batch(self, lotto: str) -> List[dict]:
        with self._db() as db:
            righe = db.execute("SELECT j.*, a.hostname FROM jobs j JOIN agents a ON a.id = j.agent_id WHERE batch = ? ORDER BY a.hostname", (lotto,)).fetchall()
        return [self._job(j) for j in righe]

    def recent_jobs(self, limite: int = 100) -> List[dict]:
        with self._db() as db:
            righe = db.execute("SELECT j.*, a.hostname FROM jobs j JOIN agents a ON a.id = j.agent_id ORDER BY j.id DESC LIMIT ?", (limite,)).fetchall()
        return [self._job(j) for j in righe]

    def cancel_job(self, job_id: int) -> None:
        with self._db() as db:
            if not db.execute("UPDATE jobs SET status = 'cancelled' WHERE id = ? AND status = 'queued'", (job_id,)).rowcount:
                raise CentralError("Only queued jobs can be cancelled.", 409)

    # ---------- inventory ----------

    def software_search(self, q: str) -> List[dict]:
        testo = (q or "").lower().strip()
        trovati = []
        for a in self.agents():
            inv = self.agent(a["id"])["inventory"]
            for s in inv.get("software", []):
                if not testo or testo in f"{s.get('name', '')} {s.get('publisher', '')}".lower():
                    trovati.append({"agent_id": a["id"], "hostname": a["hostname"], "name": s.get("name"), "version": s.get("version"), "publisher": s.get("publisher")})
        return trovati[:5000]

    def inventory_csv(self) -> str:
        import csv
        import io
        uscita = io.StringIO()
        w = csv.writer(uscita)
        w.writerow(["hostname", "asset_tag", "owner", "location", "warranty_until", "manufacturer", "model", "serial", "cpu", "ram_gb", "os", "build",
                    "disks", "last_seen", "groups"])
        for a in self.agents():
            d = self.agent(a["id"])
            hw = d["inventory"].get("hardware", {})
            w.writerow([a["hostname"], a["asset_tag"], a["owner"], a["location"], a["warranty_until"], hw.get("manufacturer", ""), hw.get("model", ""),
                        hw.get("serial", ""), hw.get("cpu", ""), hw.get("ram_gb", ""), hw.get("os", ""), hw.get("build", ""),
                        "; ".join(f"{x.get('model', '')} {x.get('size_gb', '')} GB" for x in hw.get("disks", [])), a["last_seen"], " ".join(a["tags"])])
        return uscita.getvalue()

    # ---------- software catalog and update rings ----------

    def catalog(self) -> List[dict]:
        with self._db() as db:
            return [dict(r, required=bool(r["required"])) for r in db.execute("SELECT * FROM catalog ORDER BY name")]

    def save_catalog(self, dati: dict) -> dict:
        from .deploy import valid_id
        wid = str(dati.get("winget_id", "")).strip()
        if not valid_id(wid):
            raise CentralError("The winget ID looks like Publisher.Program (e.g. Mozilla.Firefox).")
        nome = str(dati.get("name") or wid)[:80]
        with self._db() as db:
            db.execute("INSERT INTO catalog (id, winget_id, name, notes, required) VALUES (?, ?, ?, ?, ?) ON CONFLICT(winget_id) DO UPDATE SET name = excluded.name, "
                       "notes = excluded.notes, required = excluded.required", ("c" + secrets.token_hex(5), wid, nome, str(dati.get("notes", ""))[:300],
                                                                                 1 if dati.get("required") else 0))
        return next(c for c in self.catalog() if c["winget_id"] == wid)

    def delete_catalog(self, ident: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM catalog WHERE id = ?", (ident,))

    def rings(self) -> List[dict]:
        with self._db() as db:
            anelli = [dict(r) for r in db.execute("SELECT * FROM rings ORDER BY quality_days, name")]
            conti = {r["ring"]: r["n"] for r in db.execute("SELECT ring, COUNT(*) AS n FROM agents GROUP BY ring")}
        return [dict(r, members=conti.get(r["id"], 0)) for r in anelli]

    def save_ring(self, dati: dict) -> dict:
        from .updatepolicy import clean_ring
        anello = clean_ring(dati)
        ident = dati.get("id") or "r" + secrets.token_hex(5)
        with self._db() as db:
            try:
                db.execute("INSERT INTO rings (id, name, quality_days, feature_days, target_version, paused_until, active_hours) VALUES (?, ?, ?, ?, ?, ?, ?) "
                           "ON CONFLICT(id) DO UPDATE SET name = excluded.name, quality_days = excluded.quality_days, feature_days = excluded.feature_days, "
                           "target_version = excluded.target_version, paused_until = excluded.paused_until, active_hours = excluded.active_hours",
                           (ident, anello["name"], anello["quality_days"], anello["feature_days"], anello["target_version"], anello["paused_until"], anello["active_hours"]))
            except sqlite3.IntegrityError:
                raise CentralError("A ring with this name already exists.", 409) from None
        return next(r for r in self.rings() if r["id"] == ident)

    def delete_ring(self, ident: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM rings WHERE id = ?", (ident,))
            db.execute("UPDATE agents SET ring = '' WHERE ring = ?", (ident,))

    def assign_ring(self, agenti: List[str], ident: str) -> int:
        if ident and ident not in {r["id"] for r in self.rings()}:
            raise CentralError("Unknown update ring.")
        with self._db() as db:
            return sum(db.execute("UPDATE agents SET ring = ? WHERE id = ?", (ident, a)).rowcount for a in agenti)

    def overview(self) -> dict:
        a = self.agents()
        oggi = datetime.now().date().isoformat()
        return {"agents": len(a), "online": sum(x["online"] for x in a), "weak": sum(1 for x in a if (x["overall"] or 100) < 60),
                "warranty_expired": sum(1 for x in a if x["warranty_until"] and x["warranty_until"] < oggi),
                "compliance": round(sum(x["compliance"] for x in a if x["compliance"] is not None) / max(1, sum(1 for x in a if x["compliance"] is not None)), 1)
                if any(x["compliance"] is not None for x in a) else None,
                "queued": sum(x["queued"] for x in a), "groups": len(self.groups())}


def server_http(server: Server, porta: int, data_dir: Path, tls: bool = True) -> ThreadingHTTPServer:
    """The HTTPS endpoint the agents contact: enroll and heartbeat, nothing else."""

    class Gestore(BaseHTTPRequestHandler):
        server_version = "WMM-Central"

        def log_message(self, *a):
            pass

        def _answer(self, stato: int, corpo: dict) -> None:
            dati = json.dumps(corpo).encode("utf-8")
            self.send_response(stato)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dati)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dati)

        def do_POST(self):  # noqa: N802
            try:
                lunghezza = min(int(self.headers.get("Content-Length") or 0), 4_000_000)
            except ValueError:
                lunghezza = 0
            corpo = self.rfile.read(lunghezza)
            h = self.headers
            try:
                if self.path == API + "/enroll":
                    self._answer(200, server.enroll(h.get(AGENT, ""), h.get(TIME, ""), h.get(NONCE, ""), corpo, h.get(SIG, ""), self.client_address[0]))
                    return
                if self.path != API + "/heartbeat":
                    self._answer(404, {"error": "Not found."})
                    return
                agente = server.authenticate(h.get(AGENT, ""), "POST", self.path, h.get(TIME, ""), h.get(NONCE, ""), corpo, h.get(SIG, ""))
                if agente is None:
                    self._answer(403, {"error": "Unknown agent or wrong signature."})
                    return
                self._answer(200, server.heartbeat(agente, json.loads(corpo.decode("utf-8") or "{}"), self.client_address[0]))
            except CentralError as e:
                self._answer(e.status, {"error": str(e)})
            except (ValueError, UnicodeDecodeError):
                self._answer(400, {"error": "Bad request."})

        def do_GET(self):  # noqa: N802
            self._answer(404, {"error": "Not found."})

    http = ThreadingHTTPServer(("0.0.0.0", porta), Gestore)
    http.daemon_threads = True
    if tls:
        from . import tlsutil
        tlsutil.wrap(http, data_dir)
    threading.Thread(target=http.serve_forever, name="wmm-central", daemon=True).start()
    return http


# ======================================================================= agent side

INVENTORY_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem; $bios = Get-CimInstance Win32_BIOS; $os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$disks = @(Get-PhysicalDisk | ForEach-Object { [ordered]@{ model = "$($_.FriendlyName)"; size_gb = [math]::Round($_.Size / 1GB); media = "$($_.MediaType)"; health = "$($_.HealthStatus)" } })
$nics = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {
  [ordered]@{ name = "$($_.Name)"; mac = "$($_.MacAddress)"; ip = @(Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 | ForEach-Object { $_.IPAddress }) } })
[ordered]@{ manufacturer = "$($cs.Manufacturer)"; model = "$($cs.Model)"; serial = "$($bios.SerialNumber)"; bios = "$($bios.SMBIOSBIOSVersion)";
  cpu = "$($cpu.Name)".Trim(); cores = $cpu.NumberOfCores; ram_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB);
  os = "$($os.Caption)"; build = "$($os.BuildNumber)"; installed = $os.InstallDate.ToString('s'); boot = $os.LastBootUpTime.ToString('s');
  domain = "$($cs.Domain)"; user = "$($cs.UserName)"; disks = $disks; nics = $nics } | ConvertTo-Json -Depth 4 -Compress
"""


def collect_inventory(runner=None) -> dict:
    """Hardware (model, serial, BIOS, processor, memory, disks, network) and installed programs of this PC."""
    from .crashes import run_json
    hw = run_json(INVENTORY_SCRIPT, runner, timeout=120)
    try:
        from .inventory import installed_apps
        programmi = [{"name": a.get("name"), "version": a.get("version"), "publisher": a.get("publisher")} for a in installed_apps()][:3000]
    except Exception:  # noqa: BLE001 - the hardware alone is still useful
        programmi = []
    return {"hardware": hw, "software": programmi, "collected": now()}

CODE = re.compile(r"wmm://([\w.\-]+|\[[0-9a-fA-F:]+\]):(\d{2,5})/([A-Z2-9]{6})-([A-Z2-9]{20})#([0-9A-F]{64})")


def _client_path(data_dir: Path) -> Path:
    return Path(data_dir) / "central_client.json"


def client_settings(data_dir: Path) -> dict:
    try:
        d = json.loads(securestore.read_text(_client_path(data_dir)))
    except (OSError, ValueError):
        d = {}
    return {"server": d.get("server", ""), "port": d.get("port"), "fingerprint": d.get("fingerprint", ""), "agent_id": d.get("agent_id", ""),
            "enrolled": bool(d.get("secret")), "interval": int(d.get("interval") or 300), "level": d.get("level") or "safe",
            "last_contact": d.get("last_contact"), "last_error": d.get("last_error", ""), "inventory_at": d.get("inventory_at")}


def _client_write(data_dir: Path, **campi) -> None:
    try:
        d = json.loads(securestore.read_text(_client_path(data_dir)))
    except (OSError, ValueError):
        d = {}
    d.update(campi)
    securestore.write_text(_client_path(data_dir), json.dumps(d, indent=1))


def _fp(testo: str) -> str:
    t = testo.replace(":", "").upper()
    return ":".join(t[i:i + 2] for i in range(0, len(t), 2))


def request(host: str, porta: int, fingerprint: str, percorso: str, corpo: dict, segreto: str, agent_id: str) -> dict:
    """A signed POST over HTTPS to the server, accepted only from the pinned certificate."""
    import http.client
    from . import tlsutil
    dati = json.dumps(corpo).encode("utf-8")
    istante, nonce = str(int(time.time())), secrets.token_hex(12)
    intestazioni = {"Content-Type": "application/json", AGENT: agent_id, TIME: istante, NONCE: nonce,
                    SIG: signature(segreto, "POST", percorso, istante, nonce, dati), "Host": f"{host}:{porta}"}
    sock, _ = tlsutil.pinned_connection(host.strip("[]"), int(porta), fingerprint, timeout=20)
    conn = http.client.HTTPConnection(host.strip("[]"), int(porta), timeout=60)
    conn.sock = sock
    try:
        conn.request("POST", percorso, body=dati, headers=intestazioni)
        r = conn.getresponse()
        risposta = json.loads(r.read(8_000_000).decode("utf-8") or "{}")
        if r.status != 200:
            raise CentralError(risposta.get("error") or f"HTTP {r.status}", r.status)
        return risposta
    finally:
        conn.close()


def enroll(data_dir: Path, codice: str, hostname: str, machine_id: str, req=None) -> dict:
    m = CODE.fullmatch((codice or "").strip())
    if not m:
        raise CentralError("Paste the whole enrollment code (wmm://…) shown by the central server.")
    host, porta, ident, segreto, fp = m.group(1), int(m.group(2)), m.group(3), m.group(4), _fp(m.group(5))
    risposta = (req or request)(host, porta, fp, API + "/enroll", {"hostname": hostname, "machine_id": machine_id}, segreto, ident)
    _client_write(data_dir, server=host, port=porta, fingerprint=fp, agent_id=risposta["agent_id"], secret=notify.protect(risposta["secret"]),
                  last_error="", last_contact=now())
    return client_settings(data_dir)


def leave(data_dir: Path) -> None:
    _client_path(data_dir).unlink(missing_ok=True)


def set_client(data_dir: Path, interval=None, level=None) -> dict:
    campi = {}
    if interval is not None:
        if isinstance(interval, bool) or not isinstance(interval, int) or not 60 <= interval <= 86400:
            raise CentralError("Contact the server every 60 seconds to 24 hours.")
        campi["interval"] = interval
    if level is not None:
        if level not in LEVELS:
            raise CentralError("What the server may run: reports, safe or all.")
        campi["level"] = level
    _client_write(data_dir, **campi)
    return client_settings(data_dir)


def allowed_job(livello: str, lavoro: dict) -> Optional[str]:
    """Why this PC refuses a job, or None. Decided here, whatever the server asks."""
    from . import actions
    tipo, carico = lavoro.get("kind"), lavoro.get("payload") or {}
    if tipo in ("inventory", "baseline") and not carico.get("fix"):
        return None
    if tipo == "actions":
        for a in carico.get("actions", []):
            azione = actions.CATALOG.get(a)
            if azione is None or a.startswith("custom."):
                return f"unknown tool {a}"
            if azione.kind == "report":
                continue
            if livello == "reports" or (livello == "safe" and azione.risk != "safe"):
                return f"{azione.title} is not allowed from the central server on this PC"
        return None
    if livello != "all":
        return "software, update policies and fixes from the central server need the level 'everything' on this PC"
    return None


class Client:
    """The agent side, in a background thread of the console or of the background agent."""

    def __init__(self, data_dir: Path, execute: Callable[[dict], dict], summary: Callable[[], dict], hostname: str, machine_id: str, version: str):
        self.data_dir, self.execute, self.summary = Path(data_dir), execute, summary
        self.hostname, self.machine_id, self.version = hostname, machine_id, version
        self._stop = threading.Event()
        self._pending: List[dict] = []
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="wmm-central-client", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            s = client_settings(self.data_dir)
            if s["enrolled"]:
                try:
                    self.contact()
                except Exception as e:  # noqa: BLE001 - the server is down or unreachable: try again later
                    _client_write(self.data_dir, last_error=str(e)[:200])
            self._stop.wait(max(60, s["interval"]))

    def contact(self, req=None) -> dict:
        from . import baselines
        try:
            d = json.loads(securestore.read_text(_client_path(self.data_dir)))
        except (OSError, ValueError):
            raise CentralError("This PC is not enrolled.", 409) from None
        s = client_settings(self.data_dir)
        corpo = {"version": self.version, "level": s["level"], "summary": self.summary(), "results": self._pending}
        oggi = datetime.now().date().isoformat()
        if not (s["inventory_at"] or "").startswith(oggi):
            corpo["inventory"] = collect_inventory()
            corpo["compliance"] = baselines.last_summary(self.data_dir)
        risposta = (req or request)(d["server"], d["port"], d["fingerprint"], API + "/heartbeat", corpo, notify.unprotect(d["secret"]), d["agent_id"])
        self._pending = []
        _client_write(self.data_dir, last_contact=now(), last_error="", **({"inventory_at": now()} if "inventory" in corpo else {}))
        if risposta.get("ring") and s["level"] == "all":  # the same rule as a "policy" job
            try:
                from . import updatepolicy
                updatepolicy.apply_ring(updatepolicy.clean_ring(risposta["ring"]), preview=False)
            except Exception:  # noqa: BLE001 - recorded at the next job
                pass
        for lavoro in risposta.get("jobs", []):
            motivo = allowed_job(s["level"], lavoro)
            if motivo:
                self._pending.append({"job_id": lavoro["job_id"], "status": "error", "result": {"error": motivo}})
                continue
            try:
                self._pending.append({"job_id": lavoro["job_id"], "status": "done", "result": self.execute(lavoro)})
            except Exception as e:  # noqa: BLE001 - one failed job does not stop the others
                self._pending.append({"job_id": lavoro["job_id"], "status": "error", "result": {"error": str(e)[:300]}})
        return risposta
