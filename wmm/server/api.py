"""Agent facade and HTTP server. The web console talks only to /api/v1.

A future central console can call the same API on remote agents: every
payload carries machine_id, and /api/v1/agent/info identifies the agent.
"""
from __future__ import annotations

import csv
import ctypes
import gzip
import hmac
import subprocess
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

import wmm
from wmm import APP_NAME, ROOT, VERSION
from wmm.changelog import CHANGELOG
import ottimizza_pc as op

from concurrent.futures import ThreadPoolExecutor

from ..agent import actions, advisor, autostart, collectors, core, health, inventory, live, scheduler, shutdown
from ..agent.jobs import ConfirmationRequired, JobManager, RunInProgress, TaskRegistry
from ..agent.store import Store

WEB = Path(wmm.__file__).resolve().parent / "web"
STATIC_FILES: Dict[str, Path] = {p.relative_to(WEB).as_posix(): p for p in WEB.rglob("*") if p.is_file() and p.name != "index.html"}
SCRIPT = ROOT / "wmm.py"
SYSTEM_CACHE_SECONDS = 60
CONTENT_TYPES = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}
COMPRESSIBLE = {"application/javascript", "text/css", "text/html", "image/svg+xml", "application/json", "text/csv"}
GZIP_MIN_BYTES = 1024
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "no-referrer",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
                    "Cross-Origin-Opener-Policy": "same-origin"}


def index_page() -> bytes:
    """index.html with ?v=VERSION on scripts and styles, so an upgrade never runs a stale cached file."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    return re.sub(r'(/static/[\w/.-]+\.(?:js|css))"', rf'\1?v={VERSION}"', html).encode("utf-8")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Agent:
    def __init__(self, data_dir: Path, preview: bool, admin: bool):
        self.data_dir = Path(data_dir)
        self.preview = preview
        self.admin = admin
        self.store = Store(self.data_dir / "wmm.db")
        self.machine_id = core.machine_id()
        self.hostname = socket.gethostname()
        self.jobs = JobManager(self.store, self.machine_id, preview)
        self.jobs.recover_interrupted()
        self.token = secrets.token_hex(16)
        self.port = 0
        self.python = sys.executable
        self.script = str(SCRIPT)
        self._system_lock = threading.Lock()
        self._system: Optional[dict] = None
        self._system_time = 0.0
        self._installation: Optional[dict] = None
        self._health: Optional[dict] = None
        self._pair_lock = threading.Lock()
        self.server = None
        self.monitor = live.LiveMonitor()
        self.tasks = TaskRegistry()
        self.started = time.time()

    # ---------- data ----------

    def info(self) -> dict:
        return {"name": APP_NAME, "version": VERSION, "machine_id": self.machine_id, "hostname": self.hostname,
                "admin": self.admin, "preview": self.preview, "run_active": self.jobs.busy,
                "actions": len(actions.CATALOG), "reports": len(actions.REPORTS),
                "uptime_seconds": int(time.time() - self.started), "python": sys.version.split()[0]}

    def _context(self) -> op.Contesto:
        return op.Contesto(anteprima=True)

    def system(self, force: bool = False) -> dict:
        with self._system_lock:
            if force or self._system is None or time.time() - self._system_time > SYSTEM_CACHE_SECONDS:
                self._system = collectors.collect_system(self._context())
                self._system_time = time.time()
                self.store.save_scan(self.machine_id, "system", 0, self._system)
            return self._system

    def scan(self, area: str) -> dict:
        if area not in actions.AREAS:
            raise ApiError(404, f"Unknown area: {area}")
        task_id = self.tasks.start("scan", f"Scan · {actions.AREA_TITLES[area]}", 1)
        try:
            risultato = self._scan(area)
        except Exception:
            self.tasks.finish(task_id, "error")
            raise
        self.tasks.finish(task_id, "ok")
        return risultato

    def _scan(self, area: str) -> dict:
        system = self.system()
        ctx = self._context()
        ultimi = lambda: self.store.last_runs_by_action(self.machine_id)  # noqa: E731
        raccolta = {
            "cleanup": lambda: collectors.collect_cleanup(ctx, system),
            "integrity": lambda: self._integrity(ctx, system, ultimi()),
            "services": lambda: collectors.collect_services(ctx),
            "performance": lambda: inventory.collect_performance(ctx, system),
            "storage": lambda: inventory.collect_storage(ctx, system, ultimi()),
            "network": lambda: inventory.collect_network(ctx),
            "startup": lambda: inventory.collect_startup(ctx),
            "security": lambda: inventory.collect_security(ctx),
            "updates": lambda: inventory.collect_updates(ctx),
        }
        dati = raccolta[area]()
        try:
            dati.update(inventory.extras_for(area))
        except Exception as errore:  # optional settings: a warning, never a failed scan
            dati.setdefault("warnings", []).append(f"Extra settings: {errore}")
        punteggio, raccomandazioni = advisor.assess(area, dati)
        dati["recommendations"] = [r.as_dict() for r in raccomandazioni]
        self.store.save_scan(self.machine_id, area, punteggio, dati)
        return self.store.last_scan(self.machine_id, area)

    @staticmethod
    def _integrity(ctx, system: dict, ultimi: dict) -> dict:
        dati = collectors.collect_integrity(system, ultimi)
        # An unreadable event log is a warning, not a failed scan.
        dati["events"], avvisi = inventory.collect_events(ctx)
        dati["warnings"] = dati.get("warnings", []) + avvisi
        return dati

    def scan_all(self) -> dict:
        task_id = self.tasks.start("scan", "Full scan · all areas", len(actions.AREAS) + 1)
        stato = "error"
        try:
            self.system(force=True)
            self.tasks.step(task_id, "System inventory")

            def una(area: str) -> None:
                self._scan(area)
                self.tasks.step(task_id, actions.AREA_TITLES[area])

            # Areas are independent: scanning them in parallel turns minutes into the slowest one.
            with ThreadPoolExecutor(max_workers=5, thread_name_prefix="wmm-scan") as pool:
                for futuro in [pool.submit(una, area) for area in actions.AREAS]:
                    futuro.result()
            stato = "ok"
        finally:
            self.tasks.finish(task_id, stato)
        return self.dashboard()

    def activity(self) -> dict:
        adesso = datetime.now()
        prossime = []
        for voce in self.store.schedules():
            quando = scheduler.next_run(voce, adesso)
            if quando:
                azione = actions.CATALOG.get(voce["action_id"])
                prossime.append({"id": voce["id"], "action_id": voce["action_id"], "title": azione.title if azione else voce["action_id"], "next_run": quando})
        prossime.sort(key=lambda v: v["next_run"])
        return {"jobs": self.jobs.list(), "tasks": self.tasks.list(), "schedules": prossime[:6],
                "run_active": self.jobs.busy, "now": time.time()}

    def _last_or_scan(self, area: str) -> dict:
        return self.store.last_scan(self.machine_id, area) or self.scan(area)

    def area_view(self, area: str) -> dict:
        if area not in actions.AREAS:
            raise ApiError(404, f"Unknown area: {area}")
        scansione = self._last_or_scan(area)
        ultimi = self.store.last_runs_by_action(self.machine_id)
        azioni = [dict(a.as_dict(), last_run=ultimi.get(a.id)) for a in actions.by_area(area)]
        dati = dict(scansione["data"])
        return {
            "area": area, "created": scansione["created"], "score": scansione["score"],
            "recommendations": dati.pop("recommendations", []), "data": dati, "actions": azioni,
            "trend": self.store.trend(self.machine_id, area),
            "runs": self.store.runs(self.machine_id, area=area, limit=20),
        }

    def _latest(self) -> Dict[str, Optional[dict]]:
        return {area: self.store.last_scan(self.machine_id, area) for area in actions.AREAS}

    def recommendations(self, ultime: Optional[Dict[str, Optional[dict]]] = None) -> List[dict]:
        elenco: List[dict] = []
        for area, scansione in (ultime or self._latest()).items():
            if scansione:
                elenco += [dict(r, scanned=scansione["created"]) for r in scansione["data"].get("recommendations", [])]
        elenco.sort(key=lambda r: (r["priority"], advisor.RISK_ORDER.get(r["risk"], 3)))
        return elenco

    def dashboard(self) -> dict:
        # Never scans areas here (some take minutes): unscanned areas report None.
        ultime = self._latest()
        punteggi: Dict[str, Optional[int]] = {a: (s["score"] if s else None) for a, s in ultime.items()}
        scansioni = {a: (s["created"] if s else None) for a, s in ultime.items()}
        presenti = {a: p for a, p in punteggi.items() if p is not None}
        punteggi["overall"] = advisor.overall_score(presenti) if presenti else None
        raccomandazioni = self.recommendations(ultime)
        sistema = self.store.last_scan(self.machine_id, "system")
        dati = lambda a, chiave, predefinito=None: ((ultime[a] or {}).get("data") or {}).get(chiave, predefinito)  # noqa: E731
        return {
            "scores": punteggi, "scanned": scansioni,
            "system": sistema["data"] if sistema else self.system(),
            "recommendations": raccomandazioni[:8], "open_issues": len(raccomandazioni),
            "issues_by_impact": {i: sum(1 for r in raccomandazioni if r["impact"] == i) for i in ("high", "medium", "low")},
            "highlights": {
                "recoverable_bytes": dati("cleanup", "recoverable_bytes"),
                "pending_updates": len(dati("updates", "pending", []) or []) if ultime["updates"] else None,
                "startup_enabled": sum(1 for v in dati("startup", "items", []) or [] if v.get("enabled")) if ultime["startup"] else None,
                "security_issues": sum(1 for r in raccomandazioni if r["area"] == "security"),
                "network": dati("network", "targets"),
            },
            "runs": self.store.runs(self.machine_id, limit=10),
            "activity": self.store.runs(self.machine_id, limit=2000),
            "trends": {area: self.store.trend(self.machine_id, area) for area in actions.AREAS},
        }

    def playbooks(self) -> List[dict]:
        elenco = []
        for playbook in actions.PLAYBOOKS:
            passi = [actions.CATALOG[a] for a in playbook["actions"]]
            rischio = max((p.risk for p in passi), key=lambda r: advisor.RISK_ORDER[r])
            elenco.append(dict(playbook, steps=[p.as_dict() for p in passi], risk=rischio,
                               minutes=round(sum(p.minutes for p in passi), 1)))
        return elenco

    def toggle_startup(self, item_id: str, enabled) -> dict:
        if not isinstance(enabled, bool):
            raise ApiError(400, "'enabled' must be true or false.")
        self._guard_changes()
        voce = next((v for v in inventory.startup_items() if v["id"] == item_id), None)
        if voce is None:
            raise ApiError(404, "Startup entry not found. Scan the area again.")
        stato = "enabled" if enabled else "disabled"
        run_id = self.store.open_run(self.machine_id, "startup.toggle", "manual")
        if self.preview:
            self.store.close_run(run_id, "preview", f"{voce['name']}: would be {stato}", 0, "")
            return {"ok": True, "preview": True}
        try:
            inventory.set_startup_enabled(voce, enabled)
        except OSError as errore:
            self.store.close_run(run_id, "error", f"{voce['name']}: {errore}", 0, "")
            raise ApiError(500, f"Could not change the startup entry: {errore}") from None
        self.store.close_run(run_id, "ok", f"{voce['name']}: {stato}", 0, f"{voce['location']} › {voce['name']} {stato}")
        return {"ok": True}

    def history(self, area: Optional[str], limit: int) -> dict:
        if area and area not in actions.AREAS:
            raise ApiError(404, f"Unknown area: {area}")
        return {
            "runs": self.store.runs(self.machine_id, area=area, limit=limit),
            "trends": {a: self.store.trend(self.machine_id, a, limit=90) for a in actions.AREAS},
        }

    # ---------- changes ----------

    def _guard_changes(self) -> None:
        if not self.admin and not self.preview:
            raise ApiError(409, "Administrator rights are required. Restart Windows Maintenance Manager as administrator.")

    @staticmethod
    def _check_actions(ids: List[str], confirmed: bool) -> None:
        if not isinstance(ids, list) or not ids or not all(isinstance(a, str) for a in ids):
            raise ApiError(400, "Select at least one action.")
        sconosciute = [a for a in ids if a not in actions.CATALOG]
        if sconosciute:
            raise ApiError(400, f"Unknown action: {', '.join(map(str, sconosciute))}")
        if not confirmed and any(actions.CATALOG[a].risk != "safe" for a in ids):
            raise ApiError(400, "Confirmation is required for actions that are not safe.")

    def start_run(self, ids: List[str], confirmed: bool, origin: str = "manual") -> str:
        self._check_actions(ids, confirmed)
        self._guard_changes()
        try:
            return self.jobs.start(ids, origin, confirmed)
        except ConfirmationRequired as errore:
            raise ApiError(400, str(errore)) from None
        except RunInProgress as errore:
            raise ApiError(409, str(errore)) from None

    def autostart(self) -> dict:
        try:
            attivo = autostart.is_enabled()
        except (OSError, subprocess.SubprocessError):
            attivo = False
        return {"enabled": attivo, "protected": self.installation()["protected"]}

    def set_autostart(self, enabled) -> dict:
        if not isinstance(enabled, bool):
            raise ApiError(400, "'enabled' must be true or false.")
        self._guard_changes()
        if self.preview:
            raise ApiError(409, "Start with Windows cannot be changed in preview mode.")
        try:
            if enabled:
                autostart.enable(self.python, self.script, self.port or 8765)
            else:
                autostart.disable()
        except scheduler.UnprotectedProgram as errore:
            raise ApiError(409, str(errore)) from None
        except (RuntimeError, OSError, subprocess.SubprocessError) as errore:
            raise ApiError(500, f"Task Scheduler refused the change: {errore}") from None
        return self.autostart()

    def shutdown(self) -> dict:
        """Power button: stops every WMM process on this PC, this agent last (after answering)."""
        if not self.admin or self.preview:
            raise ApiError(409, "Only a console running as administrator can stop Windows Maintenance Manager.")
        fermati = shutdown.stop_others(os.getpid())
        running = self.jobs.busy
        # Answer the browser first, then end this process and whatever it started.
        threading.Timer(1.0, self._stop_self).start()
        return {"stopping": True, "stopped_processes": len(fermati), "run_interrupted": running}

    @staticmethod
    def _stop_self() -> None:
        shutdown.stop_self()

    def restore_point_on_start(self) -> Optional[str]:
        """Settings › Restore point at every start: one automatic run when the console starts."""
        if self.preview or not self.admin or self.store.settings().get("restore_on_start") != "1":
            return None
        try:
            return self.jobs.start(["security.restore_point"], "auto", confirmed=True)
        except RunInProgress:
            return None  # a scheduled run holds the lock: it creates its own restore point when needed

    # ---------- access ----------

    def _ask_user(self) -> bool:
        """Asks the person sitting at this PC; only a click on Yes hands out the session token."""
        testo = ("A browser window asks to control Windows Maintenance Manager on this PC.\n\n"
                 "Allow it only if you opened the console yourself.")
        flags = 0x4 | 0x20 | 0x1000 | 0x10000 | 0x40000  # YESNO | QUESTION | SYSTEMMODAL | SETFOREGROUND | TOPMOST
        return ctypes.windll.user32.MessageBoxW(None, testo, "Windows Maintenance Manager", flags) == 6  # IDYES

    def pair(self) -> dict:
        if not self._pair_lock.acquire(blocking=False):
            raise ApiError(409, "An access request is already waiting for an answer on the desktop of this PC.")
        try:
            consentito = self._ask_user()
        finally:
            self._pair_lock.release()
        if not consentito:
            raise ApiError(403, "Access was denied on the desktop of this PC.")
        return {"token": self.token}

    def _launch_elevated(self) -> bool:
        parametri = subprocess.list2cmdline([self.script, "--port", str(self.port), "--wait-port"])
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", self.python, parametri, str(ROOT), 1) > 32

    def _schedule_shutdown(self) -> None:
        if self.server is not None:
            # Answer the browser first, then free the port for the elevated copy.
            threading.Timer(1.0, self.server.shutdown).start()

    def elevate(self) -> dict:
        if self.admin and not self.preview:
            raise ApiError(409, "The console already runs as administrator.")
        if self.jobs.busy:
            raise ApiError(409, "Wait for the current run to finish before restarting.")
        if not self._launch_elevated():
            raise ApiError(409, "The administrator prompt was declined or failed. Click Restart as administrator to try again.")
        self._schedule_shutdown()
        return {"restarting": True}

    def set_health(self, checks: List[dict]) -> None:
        self._health = {"checks": checks, "summary": health.summary(checks), "checked": datetime.now().isoformat(timespec="seconds")}

    def health(self, refresh: bool) -> dict:
        if refresh or self._health is None:
            # The port is ours now: it is checked only before the server starts.
            self.set_health(health.run_checks(self.data_dir, None, self.admin, self.python, self.script))
            self._installation = None
        return self._health

    def installation(self) -> dict:
        """Whether SYSTEM tasks may run this copy of the program (cached: reading ACLs takes a second)."""
        if self._installation is None:
            aperti = scheduler.unprotected_paths(scheduler.protected_targets(self.python, self.script))
            self._installation = {
                "protected": not aperti, "writable": aperti[:5],
                "command": f'"{self.python}" "{self.script}" --install',
            }
        return self._installation

    def schedules(self) -> List[dict]:
        elenco = self.store.schedules()
        stati = scheduler.sync_state(elenco, self.script) if elenco else {}
        risultato = []
        for voce in elenco:
            azione = actions.CATALOG.get(voce["action_id"])
            risultato.append(dict(voce, title=azione.title if azione else voce["action_id"],
                                  risk=azione.risk if azione else "high", area=voce["action_id"].split(".")[0],
                                  sync=stati.get(voce["id"], "ok"), next_run=scheduler.next_run(voce, datetime.now())))
        return risultato

    def create_schedule(self, corpo: dict) -> int:
        action_id = corpo.get("action_id")
        kind, at, days = corpo.get("kind"), corpo.get("at"), corpo.get("days") or ""
        confermata = bool(corpo.get("confirmed"))
        self._check_actions([action_id], confermata)
        try:
            scheduler.validate(kind, at, days)
        except ValueError as errore:
            raise ApiError(400, str(errore)) from None
        self._guard_changes()
        if self.preview:
            raise ApiError(409, "Schedules cannot be created in preview mode.")
        schedule_id = self.store.create_schedule(action_id, kind, at, days, confermata)
        try:
            scheduler.register(self.store.schedule(schedule_id), self.python, self.script)
        except scheduler.UnprotectedProgram as errore:
            self.store.delete_schedule(schedule_id)
            raise ApiError(409, str(errore)) from None
        except Exception as errore:
            self.store.delete_schedule(schedule_id)
            raise ApiError(500, f"Task Scheduler refused the schedule: {errore}") from None
        return schedule_id

    def _schedule_or_404(self, schedule_id: int) -> dict:
        voce = self.store.schedule(schedule_id)
        if voce is None:
            raise ApiError(404, "Schedule not found.")
        return voce

    def update_schedule(self, schedule_id: int, corpo: dict) -> None:
        self._schedule_or_404(schedule_id)
        self._guard_changes()
        if "enabled" in corpo:
            try:
                scheduler.set_enabled(schedule_id, bool(corpo["enabled"]))
            except Exception as errore:
                raise ApiError(500, f"Task Scheduler error: {errore}") from None
            self.store.update_schedule(schedule_id, enabled=bool(corpo["enabled"]))

    def delete_schedule(self, schedule_id: int) -> None:
        self._schedule_or_404(schedule_id)
        self._guard_changes()
        scheduler.unregister(schedule_id)
        self.store.delete_schedule(schedule_id)

    def resync_schedule(self, schedule_id: int) -> None:
        voce = self._schedule_or_404(schedule_id)
        self._guard_changes()
        try:
            scheduler.register(voce, self.python, self.script)
        except scheduler.UnprotectedProgram as errore:
            raise ApiError(409, str(errore)) from None
        except Exception as errore:
            raise ApiError(500, f"Task Scheduler refused the schedule: {errore}") from None

    # ---------- export ----------

    def export(self, scope: str, formato: str) -> Tuple[bytes, str, str]:
        if scope != "all" and scope not in actions.AREAS:
            raise ApiError(404, f"Unknown area: {scope}")
        area = None if scope == "all" else scope
        runs = self.store.runs(self.machine_id, area=area, limit=10000)
        timbro = datetime.now().strftime("%Y%m%d-%H%M")
        nome = f"wmm-{scope}-{self.hostname}-{timbro}.{formato}"
        if formato == "csv":
            testo = io.StringIO()
            scrittore = csv.writer(testo, lineterminator="\n")
            scrittore.writerow(["date", "action", "area", "origin", "status", "note", "bytes_freed"])
            for run in runs:
                scrittore.writerow([run["started"], run["action_id"], run["area"], run["origin"], run["status"], run["note"], run["bytes_freed"]])
            return testo.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", nome
        if formato == "json":
            dati = {"generated": datetime.now().isoformat(timespec="seconds"), "agent": self.info()}
            if area:
                dati["area"] = self.area_view(area)
            else:
                dati["dashboard"] = self.dashboard()
                dati["areas"] = {a: self.area_view(a) for a in actions.AREAS}
            dati["runs"] = runs
            return json.dumps(dati, indent=2, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", nome
        raise ApiError(404, f"Unknown format: {formato}")


# ---------- HTTP ----------

Route = Tuple[str, "re.Pattern[str]", Callable]


class Handler(BaseHTTPRequestHandler):
    agent: Agent
    server_version = "WMM/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):  # keep the console readable
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            sys.stderr.write("%s - %s\n" % (self.address_string(), formato % args))

    # ---------- plumbing ----------

    def _send(self, status: int, corpo: bytes, tipo: str, extra: Optional[Dict[str, str]] = None, cache: str = "no-store") -> None:
        # Text larger than a packet travels compressed when the browser accepts it.
        comprimi = (len(corpo) >= GZIP_MIN_BYTES and tipo.split(";")[0] in COMPRESSIBLE
                    and "gzip" in self.headers.get("Accept-Encoding", ""))
        if comprimi:
            corpo = gzip.compress(corpo, 6)
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Accept-Encoding")
        if comprimi:
            self.send_header("Content-Encoding", "gzip")
        for nome, valore in SECURITY_HEADERS.items():
            self.send_header(nome, valore)
        inizio = getattr(self, "_started", None)
        if inizio is not None:
            self.send_header("Server-Timing", f"app;dur={(time.perf_counter() - inizio) * 1000:.1f}")
        for nome, valore in (extra or {}).items():
            self.send_header(nome, valore)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, status: int, dati) -> None:
        self._send(status, json.dumps(dati, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _not_modified(self, etag: str) -> bool:
        if self.headers.get("If-None-Match") != etag:
            return False
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def _read_raw_body(self) -> None:
        # Always drain the body: on a keep-alive connection unread bytes would
        # be parsed as the start of the next request.
        self._raw_body = b""
        try:
            lunghezza = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            raise ApiError(400, "Invalid Content-Length.") from None
        if lunghezza > 1_000_000:
            self.close_connection = True
            raise ApiError(413, "Request too large.")
        if lunghezza > 0:
            self._raw_body = self.rfile.read(lunghezza)

    def _body(self) -> dict:
        if not self._raw_body:
            return {}
        try:
            dati = json.loads(self._raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Invalid JSON body.") from None
        if not isinstance(dati, dict):
            raise ApiError(400, "The body must be a JSON object.")
        return dati

    def _check_request(self) -> None:
        porta = self.agent.port
        consentiti = {f"127.0.0.1:{porta}", f"localhost:{porta}"}
        if self.headers.get("Host", "") not in consentiti:
            raise ApiError(403, "Forbidden host.")
        origine = self.headers.get("Origin")
        if origine and origine not in {f"http://{h}" for h in consentiti}:
            raise ApiError(403, "Forbidden origin.")
        # Pairing is the one write without a token: it only works after a click on Yes at the PC.
        if self.command not in ("GET", "HEAD") and urlsplit(self.path).path != "/api/v1/pair":
            token = self.headers.get("X-WMM-Token", "")
            if not hmac.compare_digest(token, self.agent.token):
                raise ApiError(403, "Missing or invalid token.")

    def _dispatch(self) -> None:
        self._started = time.perf_counter()
        try:
            self._read_raw_body()
            self._check_request()
            parti = urlsplit(self.path)
            percorso = parti.path
            query = {k: v[-1] for k, v in parse_qs(parti.query).items()}
            if percorso.startswith("/api/"):
                for metodo, schema, funzione in ROUTES:
                    if metodo != self.command:
                        continue
                    trovato = schema.fullmatch(percorso)
                    if trovato:
                        funzione(self, query, *trovato.groups())
                        return
                raise ApiError(404, "Not found.")
            if self.command not in ("GET", "HEAD"):
                raise ApiError(405, "Method not allowed.")
            self._static(percorso)
        except ApiError as errore:
            self._json(errore.status, {"error": errore.message, "status": errore.status})
        except Exception as errore:  # never leave the browser without an answer
            sys.stderr.write(f"Internal error on {self.command} {self.path}: {errore!r}\n")
            self._json(500, {"error": f"Internal error: {errore}"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _dispatch

    def _static(self, percorso: str) -> None:
        # The page never contains the token: the browser gets it from the #k= link the agent opens.
        if percorso in ("/", "/index.html"):
            self._send(200, index_page(), CONTENT_TYPES[".html"])
            return
        if not percorso.startswith("/static/"):
            raise ApiError(404, "Not found.")
        # Only files that exist in web/ at startup: no path from the request reaches the filesystem
        # (a UNC path would make the agent authenticate to a remote server).
        file = STATIC_FILES.get(unquote(percorso[len("/static/"):]))
        if file is None:
            raise ApiError(404, "Not found.")
        tipo = CONTENT_TYPES.get(file.suffix.lower()) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        # Revalidated on every load (no-cache + ETag): an unchanged file costs a 304 without a body.
        info = file.stat()
        etag = f'"{info.st_mtime_ns:x}-{info.st_size:x}"'
        if self._not_modified(etag):
            return
        self._send(200, file.read_bytes(), tipo, {"ETag": etag}, cache="no-cache")

    # ---------- routes ----------

    def info(self, query):
        self._json(200, self.agent.info())

    def dashboard(self, query):
        self._json(200, self.agent.dashboard())

    def scan_all(self, query):
        self._json(200, self.agent.scan_all())

    def area(self, query, area):
        self._json(200, self.agent.area_view(area))

    def scan_area(self, query, area):
        self.agent.scan(area)
        self._json(200, self.agent.area_view(area))

    def list_actions(self, query):
        """Optional filters: area, kind (fix/report), risk and q (text in title, description or id)."""
        testo = query.get("q", "").lower()
        elenco = [a for a in actions.CATALOG.values()
                  if all(not query.get(campo) or getattr(a, campo) == query[campo] for campo in ("area", "kind", "risk"))
                  and (not testo or testo in f"{a.id} {a.title} {a.description}".lower())]
        self._json(200, {"actions": [a.as_dict() for a in elenco], "total": len(actions.CATALOG)})

    def changelog(self, query):
        self._json(200, {"version": VERSION, "releases": CHANGELOG})

    def start_run(self, query):
        corpo = self._body()
        job_id = self.agent.start_run(corpo.get("actions"), bool(corpo.get("confirmed")))
        self._json(202, {"id": job_id})

    def start_safe(self, query):
        corpo = self._body()
        area = corpo.get("area")
        if area is not None and area not in actions.AREAS:
            raise ApiError(404, f"Unknown area: {area}")
        ids = [a.id for a in actions.safe(area)]
        if not ids:
            raise ApiError(400, "There are no safe actions in this area.")
        self._json(202, {"id": self.agent.start_run(ids, False, origin="auto"), "actions": ids})

    def current_run(self, query):
        self._json(200, {"id": self.agent.jobs.current_id, "active": self.agent.jobs.busy})

    def run_status(self, query, job_id):
        try:
            self._json(200, self.agent.jobs.status(job_id))
        except KeyError:
            raise ApiError(404, "Run not found.") from None

    def history(self, query):
        try:
            limite = max(1, min(5000, int(query.get("limit", 200))))
        except ValueError:
            raise ApiError(400, "Invalid limit.") from None
        self._json(200, self.agent.history(query.get("area") or None, limite))

    def run_log(self, query, run_id):
        log = self.agent.store.run_log(int(run_id))
        if log is None:
            raise ApiError(404, "Run not found.")
        self._json(200, {"id": int(run_id), "log": log})

    def export(self, query, scope, formato):
        corpo, tipo, nome = self.agent.export(scope, formato)
        self._send(200, corpo, tipo, {"Content-Disposition": f'attachment; filename="{nome}"'})

    def live(self, query):
        try:
            dal = float(query.get("since", 0))
        except ValueError:
            raise ApiError(400, "Invalid 'since'.") from None
        self._json(200, {"samples": self.agent.monitor.request(dal), "error": self.agent.monitor.last_error})

    def recommendations(self, query):
        self._json(200, {"items": self.agent.recommendations()})

    def activity(self, query):
        self._json(200, self.agent.activity())

    def pair(self, query):
        self._json(200, self.agent.pair())

    def token_check(self, query):
        self._json(200, {"ok": True})

    def elevate(self, query):
        self._json(200, self.agent.elevate())

    def health(self, query):
        self._json(200, self.agent.health(query.get("refresh") == "1"))

    def playbooks(self, query):
        self._json(200, {"playbooks": self.agent.playbooks()})

    def get_settings(self, query):
        self._json(200, self.agent.store.settings())

    def put_settings(self, query):
        try:
            self.agent.store.save_settings(self._body())
        except ValueError as errore:
            raise ApiError(400, str(errore)) from None
        self._json(200, self.agent.store.settings())

    def stop_all(self, query):
        self._json(200, self.agent.shutdown())

    def get_autostart(self, query):
        self._json(200, self.agent.autostart())

    def put_autostart(self, query):
        self._json(200, self.agent.set_autostart(self._body().get("enabled")))

    def toggle_startup(self, query, item_id):
        self._json(200, self.agent.toggle_startup(item_id, self._body().get("enabled")))

    def list_schedules(self, query):
        self._json(200, {"schedules": self.agent.schedules(), "installation": self.agent.installation()})

    def create_schedule(self, query):
        self._json(201, {"id": self.agent.create_schedule(self._body())})

    def update_schedule(self, query, schedule_id):
        self.agent.update_schedule(int(schedule_id), self._body())
        self._json(200, {"ok": True})

    def delete_schedule(self, query, schedule_id):
        self.agent.delete_schedule(int(schedule_id))
        self._json(200, {"ok": True})

    def resync_schedule(self, query, schedule_id):
        self.agent.resync_schedule(int(schedule_id))
        self._json(200, {"ok": True})


def _route(metodo: str, schema: str, funzione: Callable) -> Route:
    return metodo, re.compile("/api/v1" + schema), funzione


AREA = r"(cleanup|integrity|services|[^/]+)"
ROUTES: List[Route] = [
    _route("GET", "/agent/info", Handler.info),
    _route("POST", "/pair", Handler.pair),
    _route("POST", "/agent/token-check", Handler.token_check),
    _route("POST", "/agent/elevate", Handler.elevate),
    _route("POST", "/agent/shutdown", Handler.stop_all),
    _route("GET", "/dashboard", Handler.dashboard),
    _route("POST", "/scan", Handler.scan_all),
    _route("GET", f"/areas/{AREA}", Handler.area),
    _route("POST", f"/areas/{AREA}/scan", Handler.scan_area),
    _route("GET", "/actions", Handler.list_actions),
    _route("GET", "/changelog", Handler.changelog),
    _route("POST", "/runs", Handler.start_run),
    _route("POST", "/runs/safe", Handler.start_safe),
    _route("GET", "/runs/current", Handler.current_run),
    _route("GET", r"/runs/([0-9a-f]{32})", Handler.run_status),
    _route("GET", "/history", Handler.history),
    _route("GET", r"/history/runs/(\d+)/log", Handler.run_log),
    _route("GET", r"/export/([a-z]+)\.(json|csv)", Handler.export),
    _route("GET", "/live", Handler.live),
    _route("GET", "/recommendations", Handler.recommendations),
    _route("GET", "/activity", Handler.activity),
    _route("GET", "/health", Handler.health),
    _route("GET", "/playbooks", Handler.playbooks),
    _route("GET", "/settings", Handler.get_settings),
    _route("PUT", "/settings", Handler.put_settings),
    _route("GET", "/agent/autostart", Handler.get_autostart),
    _route("PUT", "/agent/autostart", Handler.put_autostart),
    _route("POST", r"/startup/([0-9a-f]{16})/toggle", Handler.toggle_startup),
    _route("GET", "/schedules", Handler.list_schedules),
    _route("POST", "/schedules", Handler.create_schedule),
    _route("PATCH", r"/schedules/(\d+)", Handler.update_schedule),
    _route("DELETE", r"/schedules/(\d+)", Handler.delete_schedule),
    _route("POST", r"/schedules/(\d+)/resync", Handler.resync_schedule),
]


def make_server(agent: Agent, port: int) -> ThreadingHTTPServer:
    gestore = type("BoundHandler", (Handler,), {"agent": agent})
    server = ThreadingHTTPServer(("127.0.0.1", port), gestore)
    server.daemon_threads = True
    agent.port = server.server_address[1]
    agent.server = server
    return server
