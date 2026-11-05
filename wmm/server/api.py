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

from ..agent import (actions, advisor, apps, autostart, restore, collectors, core, events, hardware, health, inventory, live, processes, registry,
                     routines, scheduler, scripts, shutdown)
from ..agent import accounts, appsettings, custom_tools, verify
from . import permissions
from ..agent.jobs import ConfirmationRequired, JobManager, RunInProgress, TaskRegistry
from ..agent.store import Store
from .errors import ApiError  # noqa: F401 - part of this module's interface
from .features import AgentFeatures, HandlerFeatures, FEATURE_ROUTES
from .accounts_api import ACCOUNT_ROUTES, AccountsHandler
from .enterprise_api import ENTERPRISE_ROUTES, AgentEnterprise, HandlerEnterprise

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




def _delay(corpo: dict) -> int:
    """Minutes to wait after startup or sign-in; scheduler.validate checks the range."""
    valore = corpo.get("delay", 0)
    if isinstance(valore, bool):
        raise ApiError(400, "The delay must be a number of minutes.")
    try:
        return int(valore or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "The delay must be a number of minutes.") from None


class Agent(AgentEnterprise, AgentFeatures):
    def __init__(self, data_dir: Path, preview: bool, admin: bool):
        self.data_dir = Path(data_dir)
        self.preview = preview
        self.admin = admin
        self.store = Store(self.data_dir / "wmm.db")
        self.machine_id = core.machine_id()
        self.hostname = socket.gethostname()
        self.jobs = JobManager(self.store, self.machine_id, preview)
        self.jobs.recover_interrupted()
        custom_tools.register(self.data_dir)  # your own tools join the catalog (2.7)
        self.accounts = accounts.for_data_dir(self.data_dir)  # users, roles and the audit log (2.9)
        appsettings.apply_proxy(self.data_dir)
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
        self.events = events.EventReader()
        self.hardware = hardware.HardwareReader()
        self.procs = processes.ProcessMonitor()
        self.registry = registry.RegistryEditor(self.data_dir / "registry-backups")
        self.scripts = scripts.ScriptLibrary(self.data_dir / "scripts")
        self.timer = scripts.ShutdownTimer(self.data_dir / "shutdown_timer.json")
        self._protect_lock = threading.Lock()
        self._protect: dict = {"active": False, "status": "idle", "log": []}
        self._apps_lock = threading.Lock()
        self._apps: Optional[dict] = None
        # Rules of the Applications page: a newer copy downloaded into the data folder wins over the built-in one.
        apps.RULES_OVERRIDE = self.data_dir / "app_rules.json"
        apps.load_rules()
        self._uninstalls: Dict[str, dict] = {}
        self._netscan_lock = threading.Lock()  # app id -> the program and its uninstaller, until the page has seen the end

    # ---------- data ----------

    def info(self) -> dict:
        return {"name": APP_NAME, "version": VERSION, "machine_id": self.machine_id, "hostname": self.hostname,
                "admin": self.admin, "preview": self.preview, "run_active": self.jobs.busy,
                "actions": len(actions.CATALOG), "reports": len(actions.REPORTS), "accounts": self.accounts.enabled,
                "org_name": appsettings.load(self.data_dir)["org_name"],
                "run_rules": {k: appsettings.load(self.data_dir)[k] for k in ("block_high_risk", "require_reason", "confirm_high_with_name")},
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
        if area == "storage":
            self._alert_disk(system)
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
                prossime.append({"id": voce["id"], "action_id": voce["action_id"],
                                 "title": routines.describe(voce["action_id"])["title"], "next_run": quando})
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

    # ---------- system tools: events, processes, services, registry ----------

    def _logged_change(self, action_id: str, descrizione: str, cambia: Callable[[], dict], punto: bool = False,
                       senza_punto: bool = False) -> dict:
        """Runs one manual change with the same rules as actions: administrator, never in preview, recorded in History.
        `punto`: a restore point first (Settings › Start-up), unless the user chose to go on without one."""
        self._guard_changes()
        run_id = self.store.open_run(self.machine_id, action_id, "manual")
        if self.preview:
            self.store.close_run(run_id, "preview", f"{descrizione} (preview: nothing changed)", 0, "")
            return {"ok": True, "preview": True}
        protezione = None
        if punto and not senza_punto and self.store.settings().get("restore_before_changes") != "0":
            try:
                protezione = restore.ensure_point(descrizione)
            except (restore.RestoreError, OSError, subprocess.SubprocessError) as errore:
                self.store.close_run(run_id, "error", f"{descrizione}: not done, no restore point ({errore})", 0, "")
                # 412: the page offers to go on without a restore point.
                raise ApiError(412, f"No restore point, nothing was changed. {errore}") from None
        try:
            esito = cambia() or {}
            if protezione:
                esito = dict(esito, restore_point=protezione["seq"])
        except (processes.ControlError, registry.RegistryError, scripts.ScriptError, hardware.MonitorToolError) as errore:
            self.store.close_run(run_id, "error", f"{descrizione}: {errore}", 0, "")
            raise ApiError(409, str(errore)) from None
        except PermissionError:
            self.store.close_run(run_id, "error", f"{descrizione}: access denied", 0, "")
            raise ApiError(409, "Windows denies this change (access denied), even to administrators.") from None
        except (OSError, subprocess.SubprocessError) as errore:
            self.store.close_run(run_id, "error", f"{descrizione}: {errore}", 0, "")
            raise ApiError(500, f"{descrizione} failed: {errore}") from None
        dettaglio = esito.get("backup")
        nota = descrizione + (f" · backup {dettaglio}" if dettaglio else "") + (f" · restore point #{protezione['seq']}" if protezione else "")
        self.store.close_run(run_id, "ok", nota, 0,
                             json.dumps(esito, ensure_ascii=False))
        return dict(esito, ok=True)

    def monitor_tool(self, corpo: dict) -> dict:
        """Installs (with winget) and/or starts LibreHardwareMonitor, which publishes CPU, motherboard and fan sensors."""
        operazione = corpo.get("action")
        if operazione not in ("install", "start"):
            raise ApiError(400, "Unknown operation: use install or start.")

        def cambia():
            uscita = hardware.install_monitor_tool() if operazione == "install" else ""
            percorso = hardware.start_monitor_tool()
            return {"path": percorso, "output": uscita[-2000:]}
        testo = "Install and start LibreHardwareMonitor" if operazione == "install" else "Start LibreHardwareMonitor"
        return self._logged_change("hardware.monitor_tool", testo, cambia)

    def end_process(self, pid: int, corpo: dict) -> dict:
        nome, albero = str(corpo.get("name") or ""), bool(corpo.get("tree"))
        riga = processes.check_end_process(self.procs.processes()["processes"], pid, nome, [os.getpid(), os.getppid()])

        def cambia():
            return {"output": processes.end_process(pid, albero)}
        return self._logged_change("performance.end_process", f"End {riga['name']} (PID {pid}{', with child processes' if albero else ''})", cambia)

    def _process_row(self, pid: int, nome: str) -> dict:
        riga = next((r for r in self.procs.processes()["processes"] if r["pid"] == pid), None)
        if riga is None:
            raise processes.ControlError("The process has already ended.")
        if riga["name"].lower() != (nome or "").lower():
            raise processes.ControlError("The process ID now belongs to another program. Refresh the list.")
        return riga

    def process_priority(self, pid: int, corpo: dict) -> dict:
        riga = self._process_row(pid, str(corpo.get("name") or ""))
        priorita = str(corpo.get("priority") or "")
        if riga["critical"]:
            raise processes.ControlError(f"The priority of {riga['name']} is managed by Windows.")
        return self._logged_change("performance.process_priority", f"Priority of {riga['name']} (PID {pid}) set to {priorita.replace('_', ' ')}",
                                   lambda: {"output": processes.set_priority(pid, priorita)})

    def start_process(self, corpo: dict) -> dict:
        programma, argomenti = str(corpo.get("program") or ""), str(corpo.get("arguments") or "")
        elevato = bool(corpo.get("elevated"))
        percorso = processes.resolve_program(programma)
        return self._logged_change("performance.start_process",
                                   f"Start {percorso}{' ' + argomenti if argomenti else ''} ({'administrator' if elevato else 'standard user'})",
                                   lambda: processes.start_process(percorso, argomenti, str(corpo.get("folder") or ""), elevato))

    def reveal_process(self, pid: int, corpo: dict) -> dict:
        riga = self._process_row(pid, str(corpo.get("name") or ""))
        if not riga.get("path"):
            raise processes.ControlError("Windows does not share the location of this process.")
        subprocess.Popen(["explorer.exe", "/select,", riga["path"]])
        return {"ok": True}

    def control_service(self, nome: str, operazione: str) -> dict:
        servizio = processes.check_service(self.procs.services(fresh=True), nome, operazione)

        def cambia():
            stato = processes.control_service(servizio["name"], operazione)
            self.procs.services(fresh=True)
            return {"state": stato}
        return self._logged_change("services.control", f"{operazione.capitalize()} service {servizio['display'] or servizio['name']}", cambia)

    def registry_change(self, operazione: str, corpo: dict) -> dict:
        percorso = str(corpo.get("path") or "")
        operazioni = {
            "set": (lambda: self.registry.set_value(percorso, corpo.get("name", ""), str(corpo.get("type") or ""), corpo.get("data")),
                    f"Set {percorso}\\{corpo.get('name') or '(Default)'} ({corpo.get('type')})"),
            "delete-value": (lambda: self.registry.delete_value(percorso, corpo.get("name", "")), f"Delete value {percorso}\\{corpo.get('name') or '(Default)'}"),
            "rename-value": (lambda: self.registry.rename_value(percorso, corpo.get("name", ""), corpo.get("new_name", "")),
                             f"Rename value {percorso}\\{corpo.get('name')} to {corpo.get('new_name')}"),
            "create-key": (lambda: self.registry.create_key(percorso, corpo.get("name", "")), f"Create key {percorso}\\{corpo.get('name')}"),
            "delete-key": (lambda: self.registry.delete_key(percorso), f"Delete key {percorso}"),
            "restore": (lambda: {"restored": self.registry.restore(str(corpo.get("backup") or ""))}, f"Restore registry backup {corpo.get('backup')}"),
        }
        if operazione not in operazioni:
            raise ApiError(404, "Unknown registry operation.")
        cambia, descrizione = operazioni[operazione]
        # Deleting a whole key is the one registry change worth a restore point (the .reg backup covers the key only).
        return self._logged_change("integrity.registry", descrizione, cambia, punto=operazione == "delete-key",
                                   senza_punto=corpo.get("no_restore_point") is True)

    # ---------- scripts and shutdown timer ----------

    def scripts_overview(self) -> dict:
        return {"scripts": self.scripts.list(), "templates": scripts.templates_public(), "timer": self.timer.status(),
                "can_schedule": self.installation()["protected"], "can_change": self.admin or self.preview, "preview": self.preview}

    def script_run(self, script_id: str) -> dict:
        voce = self.scripts.get(script_id)
        self._guard_changes()
        run_id = self.store.open_run(self.machine_id, "scripts.run", "manual")
        if self.preview:
            self.store.close_run(run_id, "preview", f"Run script {voce['name']} (preview: nothing ran)", 0, "")
            return {"ok": True, "preview": True}

        def finito(esito: dict) -> None:
            self.store.close_run(run_id, esito["status"], f"Script {voce['name']}: exit code {esito['exit']} in {esito['seconds']} s", 0, esito["output"])
        try:
            return dict(self.scripts.run(script_id, finito), ok=True)
        except scripts.ScriptError as errore:
            self.store.close_run(run_id, "error", str(errore), 0, "")
            raise ApiError(409, str(errore)) from None

    def script_schedule(self, script_id: str, corpo: dict) -> dict:
        voce = self.scripts.get(script_id)
        tipo, quando, giorni = str(corpo.get("kind") or ""), str(corpo.get("at") or ""), str(corpo.get("days") or "")
        ritardo = _delay(corpo)
        return self._logged_change("scripts.schedule", f"Schedule script {voce['name']} ({tipo} from {quando.replace('T', ' ')})",
                                   lambda: {"script": self.scripts.schedule(script_id, tipo, quando, giorni, ritardo)})

    def script_unschedule(self, script_id: str) -> dict:
        voce = self.scripts.get(script_id)
        return self._logged_change("scripts.schedule", f"Remove the schedule of script {voce['name']}",
                                   lambda: {"script": self.scripts.unschedule(script_id)})

    def script_delete(self, script_id: str) -> dict:
        voce = self.scripts.get(script_id)
        if voce.get("schedule"):
            self._guard_changes()  # removing its Windows task needs administrator rights
        self.scripts.delete(script_id)
        return {"ok": True}

    def timer_start(self, corpo: dict) -> dict:
        azione = str(corpo.get("action") or "shutdown")
        return self._logged_change("scripts.shutdown_timer", f"{'Shut down' if azione == 'shutdown' else 'Restart'} in {corpo.get('minutes')} minute(s)",
                                   lambda: {"timer": self.timer.start(corpo.get("minutes"), azione)})

    def timer_cancel(self) -> dict:
        return self._logged_change("scripts.shutdown_timer", "Cancel the planned shutdown", lambda: {"timer": self.timer.cancel()})

    def prune_history(self, corpo: dict) -> dict:
        try:
            giorni = int(corpo.get("days"))
        except (TypeError, ValueError):
            raise ApiError(400, "Days must be a whole number.") from None
        if not 7 <= giorni <= 3650:
            raise ApiError(400, "Keep at least the last 7 days.")
        return self._logged_change("integrity.history_cleanup", f"Delete history older than {giorni} days",
                                   lambda: {"deleted": self.store.prune_runs(self.machine_id, giorni)})

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
            interprete = {os.path.normcase(p) for p in scheduler.python_paths(self.python)}
            python_aperto = [p for p in aperti if os.path.normcase(p) in interprete]
            self._installation = {
                "protected": not aperti, "writable": aperti[:5],
                # Which half is the problem: the program folder, the Python it runs with, or both.
                "program_protected": len(python_aperto) == len(aperti), "python_protected": not python_aperto,
                "python": self.python, "script": self.script,
                "command": f'"{self.python}" "{self.script}" --install',
                "can_fix": self.admin and not self.preview,
            }
        return self._installation

    # ---------- protected installation fix ----------

    def protection_status(self) -> dict:
        with self._protect_lock:
            return dict(self._protect, log=list(self._protect.get("log", [])))

    def protect(self) -> dict:
        """Makes schedules possible on this PC: a Python installed for all users (installed when missing),
        the program in Program Files, schedules registered again, then a restart with that Python."""
        if self.preview or not self.admin:
            raise ApiError(409, "Only a console running as administrator can fix the installation.")
        if self.jobs.busy:
            raise ApiError(409, "Wait for the current run to finish before fixing the installation.")
        with self._protect_lock:
            if self._protect.get("active"):
                raise ApiError(409, "The installation is already being fixed.")
            self._protect = {"active": True, "status": "running", "log": [], "step": "Looking for a Python installed for all users"}
        threading.Thread(target=self._protect_worker, name="wmm-protect", daemon=True).start()
        return self.protection_status()

    def _protect_log(self, riga: str) -> None:
        with self._protect_lock:
            self._protect["log"].append(riga)

    def _protect_step(self, task_id: str, testo: str) -> None:
        with self._protect_lock:
            self._protect["step"] = testo
        self._protect_log(f"== {testo} ==")
        self.tasks.step(task_id, testo)

    def _protect_worker(self) -> None:
        from wmm import installer, runtime
        task_id = self.tasks.start("fix", "Protect the installation for schedules", 4)
        run_id = self.store.open_run(self.machine_id, "integrity.protect_install", "manual")
        stato, nota = "error", ""
        try:
            self._protect_step(task_id, "Python installed for all users")
            python = runtime.ensure_protected_python(scheduler.unprotected_paths, self._protect_log)
            if not python:
                raise RuntimeError("no Python installed for all users could be found or installed (winget and python.org both failed)")
            self._protect_step(task_id, "Program in Program Files")
            radice, script = ROOT, self.script
            if scheduler.unprotected_paths(scheduler.program_paths(script)):
                radice = installer.default_target(os.environ)
                self._protect_log(f"Copying the program to {radice}")
                installer.copy_program(ROOT, radice)
                installer.harden(radice)
                script = str(radice / "wmm.py")
                aperti = scheduler.unprotected_paths(scheduler.program_paths(script))
                if aperti:
                    raise RuntimeError("the program folder is still writable by standard users: " + ", ".join(aperti[:3]))
            self._protect_log(f"Program protected: {script}")
            runtime.record(radice, python)
            self._protect_log(f"Every start now uses {python} ({runtime.PYTHON_FILE} next to the program)")
            self._protect_step(task_id, "Schedules registered with the protected Python")
            for voce in self.store.schedules():
                try:
                    scheduler.register(voce, python, script)
                    self._protect_log(f"  Schedule #{voce['id']} ({voce['action_id']}) registered again")
                except Exception as errore:  # one bad task must not block the others
                    self._protect_log(f"  Schedule #{voce['id']}: {errore}")
            self._protect_step(task_id, "Restarting the console with the protected Python")
            stato, nota = "ok", f"Python {python}; program {script}"
            ambiente = dict(os.environ, **{runtime.HANDOVER_ENV: "1"})
            subprocess.Popen([python, script, "--port", str(self.port), "--wait-port"], cwd=str(radice), env=ambiente,
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            with self._protect_lock:
                self._protect["restarting"] = True
        except Exception as errore:
            nota = str(errore)
            self._protect_log(f"Error: {errore}")
        finally:
            with self._protect_lock:
                self._protect.update(active=False, status=stato, note=nota)
                log = "\n".join(self._protect["log"])
            self.tasks.finish(task_id, stato)
            self.store.close_run(run_id, stato, nota, 0, log)
            self._installation = None
        if stato == "ok":
            self._schedule_shutdown()

    def schedules(self) -> List[dict]:
        elenco = self.store.schedules()
        stati = scheduler.sync_state(elenco, self.script) if elenco else {}
        # Task Scheduler's own view (last run, last result): one call for every task of the folder.
        windows = scheduler.task_status() if elenco else {}
        risultato = []
        for voce in elenco:
            descritta = routines.describe(voce["action_id"])
            risultato.append(dict(voce, title=descritta["title"], risk=descritta["risk"], area=descritta["area"],
                                  routine=descritta["routine"], steps=len(descritta["actions"]),
                                  task=windows.get(scheduler.task_name(voce["id"]).rsplit("\\", 1)[-1]),
                                  sync=stati.get(voce["id"], "ok"), next_run=scheduler.next_run(voce, datetime.now())))
        return risultato

    def routines_catalog(self) -> dict:
        dati = routines.catalog()
        attive: Dict[str, List[dict]] = {}
        for voce in self.store.schedules():
            attive.setdefault(voce["action_id"], []).append({"id": voce["id"], "kind": voce["kind"], "enabled": voce["enabled"]})
        for voce in dati["routines"] + dati["playbooks"]:
            voce["scheduled"] = attive.get(voce["ref"], [])
        return dict(dati, installation=self.installation())

    def create_schedule(self, corpo: dict) -> int:
        action_id = corpo.get("action_id")
        kind, at, days = corpo.get("kind"), corpo.get("at"), corpo.get("days") or ""
        ritardo = _delay(corpo) if kind in scheduler.EVENT_KINDS else 0
        confermata = bool(corpo.get("confirmed"))
        if not isinstance(action_id, str):
            raise ApiError(400, "Select an action or a routine.")
        try:
            passi = routines.expand(action_id)
        except KeyError:
            raise ApiError(400, f"Unknown action or routine: {action_id}") from None
        self._check_actions(passi, confermata)
        try:
            scheduler.validate(kind, at, days, ritardo)
        except ValueError as errore:
            raise ApiError(400, str(errore)) from None
        if kind == "once" and at < datetime.now().strftime("%Y-%m-%dT%H:%M"):
            raise ApiError(400, "That time has already passed: choose a time in the future for a one-time schedule.")
        self._guard_changes()
        if self.preview:
            raise ApiError(409, "Schedules cannot be created in preview mode.")
        schedule_id = self.store.create_schedule(action_id, kind, at, days, confermata, ritardo)
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

    def test_schedule(self, schedule_id: int) -> dict:
        """Starts the Windows task now, as SYSTEM: proves the schedule really runs, not only that the console can run the action."""
        voce = self._schedule_or_404(schedule_id)
        descritta = routines.describe(voce["action_id"])

        def cambia():
            try:
                scheduler.run_task_now(schedule_id)
            except RuntimeError as errore:
                raise OSError(str(errore)) from None
            return {"started": True}
        return self._logged_change("integrity.schedule_test", f"Start the scheduled task of {descritta['title']} now (test)", cambia)

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


class Handler(HandlerEnterprise, AccountsHandler, HandlerFeatures, BaseHTTPRequestHandler):
    agent: Agent
    server_version = "WMM/" + VERSION
    protocol_version = "HTTP/1.1"
    # An idle keep-alive connection frees its thread after two minutes instead of holding it forever.
    timeout = 120

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
        # API tokens of scripts (2.10) replace the console token; _authorize checks them.
        if self.headers.get("Authorization", "").startswith("Bearer ") and self.agent.accounts.enabled:
            return
        # Pairing is the one write without a token: it only works after a click on Yes at the PC.
        if self.command not in ("GET", "HEAD") and urlsplit(self.path).path not in ("/api/v1/pair", "/api/v1/auth/oidc/callback"):
            token = self.headers.get("X-WMM-Token", "")
            if not hmac.compare_digest(token, self.agent.token):
                raise ApiError(403, "Missing or invalid token.")

    # ---------- accounts (2.9) ----------

    user: Optional[dict] = None

    def _authorize(self, funzione, gruppi) -> None:
        """With accounts on: a valid session for every route but the sign-in ones, and the permissions the route needs."""
        self.user = None
        conti = self.agent.accounts
        if not conti.enabled:
            return
        nome = funzione.__name__
        if nome in permissions.PUBLIC:
            return
        intestazione = self.headers.get("Authorization", "")
        if intestazione.startswith("Bearer "):
            from ..agent import governance
            utente = governance.token_user(conti, intestazione[7:].strip())
            if utente is None:
                raise ApiError(401, "Invalid or expired API token.")
            if (nome.startswith("auth_") and nome != "auth_me") or nome in ("tokens_get", "token_create", "token_delete"):
                raise ApiError(403, "API tokens cannot sign in, change passwords or manage tokens.")
        else:
            utente = conti.session(self.headers.get("X-WMM-Session", ""))
        if utente is None:
            raise ApiError(401, "Sign in to continue.")
        self.user = utente
        if utente["limited"] and nome not in permissions.LIMITED_OK:
            raise ApiError(403, "Change your password or set up two-step verification first.")
        mancanti = [p for p in permissions.required(nome, self.command, tuple(gruppi)) if p not in utente["permissions"]]
        if mancanti:
            conti.audit(utente["username"], "denied", self.path[:200], ", ".join(mancanti), ok=False)
            raise ApiError(403, "Your role does not allow this (" + ", ".join(mancanti) + ").")

    def _audit_write(self, funzione, ok: bool) -> None:
        if self.user is not None and self.command not in ("GET", "HEAD") and not funzione.__name__.startswith("auth_"):
            self.agent.accounts.audit(self.user["username"], "api." + funzione.__name__, self.path[:200], "", ok=ok)

    def _check_role_tools(self, ids) -> list:
        """The signed-in user's role may run every one of these tools (area and risk)."""
        noti = [actions.CATALOG[a] for a in ids if isinstance(a, str) and a in actions.CATALOG]
        if self.user is not None:
            vietati = [a.title for a in noti if not accounts.can_run(self.user, a)]
            if vietati:
                self.agent.accounts.audit(self.user["username"], "denied", "run", ", ".join(vietati)[:500], ok=False)
                raise ApiError(403, "Your role does not allow running: " + ", ".join(vietati[:5]) + ("…" if len(vietati) > 5 else "") + ".")
        return noti

    def _check_schedule_tools(self, riferimento) -> None:
        """A schedule runs its tools later as SYSTEM: whoever creates, changes or starts it must be allowed to run them now."""
        if self.user is None or not isinstance(riferimento, str):
            return
        try:
            ids = routines.expand(riferimento)
        except KeyError:
            return  # unknown action: create_schedule answers 400
        self._check_role_tools(ids)

    def _check_tools(self, ids, corpo: Optional[dict] = None) -> None:
        """The role may run each tool (area and risk), and the run rules of Settings › Runs (2.9)."""
        if not isinstance(ids, list):
            return
        regole = appsettings.load(self.agent.data_dir)
        noti = self._check_role_tools(ids)
        from ..agent import governance
        if governance.needs_approval(self.agent.data_dir, self.user, noti):  # a second person decides (2.10)
            raise ApprovalPending(governance.request(self.agent.accounts, self.user, list(ids), str((corpo or {}).get("reason", ""))))
        if regole["block_high_risk"] and any(a.risk == "high" and a.kind != "report" for a in noti):
            raise ApiError(409, "High-risk tools are blocked on this PC (Settings › Runs).")
        corpo = corpo or {}
        if regole["require_reason"] and any(a.kind != "report" for a in noti):
            motivo = str(corpo.get("reason") or "").strip()
            if len(motivo) < 3:
                raise ApiError(400, "Write the reason or ticket number for these changes (Settings › Runs).")
            if self.user is not None or self.agent.accounts.enabled is False:
                self.agent.accounts.audit((self.user or {}).get("username", "local"), "run.reason", ", ".join(a.id for a in noti)[:200], motivo[:300])
        if regole["confirm_high_with_name"] and any(a.risk == "high" and a.kind != "report" for a in noti):
            if str(corpo.get("confirm_name") or "").strip().lower() != self.agent.hostname.lower():
                raise ApiError(400, f"Type the name of this PC ({self.agent.hostname}) to confirm high-risk tools.")

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
                        self._authorize(funzione, trovato.groups())
                        try:
                            funzione(self, query, *trovato.groups())
                        except ApprovalPending as attesa:
                            self._json(202, {"approval": attesa.request, "message": "This run needs the approval of a second person: the request was sent."})
                            return
                        except ApiError as errore:
                            self._audit_write(funzione, errore.status < 400)
                            raise
                        self._audit_write(funzione, True)
                        return
                raise ApiError(404, "Not found.")
            if self.command not in ("GET", "HEAD"):
                raise ApiError(405, "Method not allowed.")
            self._static(percorso)
        except DISCONNECTED:
            self.close_connection = True  # the browser went away: nobody is left to answer
        except ApiError as errore:
            self._answer_error(errore.status, {"error": errore.message, "status": errore.status})
        except Exception as errore:  # never leave the browser without an answer
            sys.stderr.write(f"Internal error on {self.command} {self.path}: {errore!r}\n")
            self._answer_error(500, {"error": f"Internal error: {errore}"})

    def _answer_error(self, status: int, dati: dict) -> None:
        try:
            self._json(status, dati)
        except DISCONNECTED:
            self.close_connection = True

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
        # "check": the before/after check that tells whether a fix worked (wmm/agent/verify.py), when it has one.
        self._json(200, {"actions": [dict(a.as_dict(), check=verify.CHECKS[a.id].label if a.id in verify.CHECKS else "",
                                          allowed=self.user is None or accounts.can_run(self.user, a)) for a in elenco],
                         "total": len(actions.CATALOG)})

    def changelog(self, query):
        self._json(200, {"version": VERSION, "releases": CHANGELOG})

    def start_run(self, query):
        corpo = self._body()
        self._check_tools(corpo.get("actions"), corpo)
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
        self._check_tools(ids, corpo)
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

    def protect(self, query):
        self._json(202, self.agent.protect())

    def event_list(self, query):
        try:
            self._json(200, self.agent.events.query(query, fresh=query.get("fresh") == "1"))
        except events.EventQueryError as errore:
            raise ApiError(400, str(errore)) from None

    def event_meta(self, query):
        self._json(200, events.meta())

    def hardware_inventory(self, query):
        try:
            self._json(200, self.agent.hardware.inventory(fresh=query.get("fresh") == "1"))
        except RuntimeError as errore:
            raise ApiError(500, str(errore)) from None

    def hardware_sensors(self, query):
        self._json(200, self.agent.hardware.sensors(fresh=query.get("fresh") == "1"))

    def hardware_monitor_tool(self, query):
        self._json(200, self.agent.monitor_tool(self._body()))

    def process_list(self, query):
        try:
            self._json(200, self.agent.procs.processes(full=query.get("full") == "1"))
        except OSError as errore:
            raise ApiError(500, f"Process counters are not available: {errore}") from None

    def process_operation(self, query, pid, operazione):
        corpo = self._body()
        try:
            if operazione == "end":
                risposta = self.agent.end_process(int(pid), corpo)
            elif operazione == "priority":
                risposta = self.agent.process_priority(int(pid), corpo)
            else:
                risposta = self.agent.reveal_process(int(pid), corpo)
        except processes.ControlError as errore:
            raise ApiError(409, str(errore)) from None
        self._json(200, risposta)

    def process_start(self, query):
        try:
            self._json(200, self.agent.start_process(self._body()))
        except processes.ControlError as errore:
            raise ApiError(409, str(errore)) from None

    def service_list(self, query):
        self._json(200, {"services": self.agent.procs.services(fresh=query.get("fresh") == "1")})

    def service_control(self, query, nome, operazione):
        try:
            self._json(200, self.agent.control_service(nome, operazione))
        except processes.ControlError as errore:
            raise ApiError(409, str(errore)) from None

    def registry_key(self, query):
        try:
            self._json(200, registry.list_key(query.get("path", "")))
        except registry.RegistryError as errore:
            raise ApiError(400, str(errore)) from None

    def registry_search(self, query):
        try:
            self._json(200, self.agent.registry.search(query.get("path", ""), query.get("q", ""), min(500, int(query.get("limit") or 200))))
        except (registry.RegistryError, ValueError) as errore:
            raise ApiError(400, str(errore)) from None

    def registry_export(self, query):
        try:
            dati = self.agent.registry.export(query.get("path", ""))
        except registry.RegistryError as errore:
            raise ApiError(400, str(errore)) from None
        nome = re.sub(r"[^\w.-]", "_", query.get("path", "registry").rsplit("\\", 1)[-1] or "registry")[:60]
        self._send(200, dati, "text/plain; charset=utf-16", {"Content-Disposition": f'attachment; filename="{nome}.reg"'})

    def prune_history(self, query):
        self._json(200, self.agent.prune_history(self._body()))

    def script_list(self, query):
        self._json(200, self.agent.scripts_overview())

    def script_get(self, query, script_id):
        try:
            self._json(200, self.agent.scripts.get(script_id))
        except scripts.ScriptError as errore:
            raise ApiError(404, str(errore)) from None

    def script_create(self, query):
        corpo = self._body()
        try:
            if corpo.get("template"):
                voce = self.agent.scripts.from_template(str(corpo["template"]), corpo.get("params") or {}, str(corpo.get("name") or ""))
            else:
                voce = self.agent.scripts.create(str(corpo.get("name") or ""), corpo.get("content"), str(corpo.get("filename") or "script.bat"))
        except scripts.ScriptError as errore:
            raise ApiError(400, str(errore)) from None
        self._json(201, voce)

    def script_operation(self, query, script_id, operazione):
        corpo = self._body()
        try:
            if operazione == "save":
                risposta = self.agent.scripts.update(script_id, str(corpo.get("name") or ""), corpo.get("content"))
            elif operazione == "delete":
                risposta = self.agent.script_delete(script_id)
            elif operazione == "run":
                risposta = self.agent.script_run(script_id)
            elif operazione == "schedule":
                risposta = self.agent.script_schedule(script_id, corpo)
            else:
                risposta = self.agent.script_unschedule(script_id)
        except scripts.ScriptError as errore:
            raise ApiError(400, str(errore)) from None
        self._json(200, risposta)

    def timer_start(self, query):
        self._json(200, self.agent.timer_start(self._body()))

    def timer_cancel(self, query):
        self._json(200, self.agent.timer_cancel())

    def registry_backups(self, query):
        self._json(200, {"backups": self.agent.registry.backups()})

    def registry_change(self, query, operazione):
        self._json(200, self.agent.registry_change(operazione, self._body()))

    def protection_status(self, query):
        self._json(200, self.agent.protection_status())

    def get_autostart(self, query):
        self._json(200, self.agent.autostart())

    def put_autostart(self, query):
        self._json(200, self.agent.set_autostart(self._body().get("enabled")))

    def toggle_startup(self, query, item_id):
        self._json(200, self.agent.toggle_startup(item_id, self._body().get("enabled")))

    def list_schedules(self, query):
        self._json(200, {"schedules": self.agent.schedules(), "installation": self.agent.installation()})

    def create_schedule(self, query):
        corpo = self._body()
        self._check_schedule_tools(corpo.get("action_id"))
        self._json(201, {"id": self.agent.create_schedule(corpo)})

    def list_routines(self, query):
        self._json(200, self.agent.routines_catalog())

    def update_schedule(self, query, schedule_id):
        corpo = self._body()
        if set(corpo) - {"enabled"}:  # only on and off: the action of a schedule never changes after it is created
            raise ApiError(400, "Only 'enabled' can be changed: delete the schedule and create a new one.")
        self._check_schedule_tools((self.agent.store.schedule(int(schedule_id)) or {}).get("action_id"))
        self.agent.update_schedule(int(schedule_id), corpo)
        self._json(200, {"ok": True})

    def delete_schedule(self, query, schedule_id):
        self.agent.delete_schedule(int(schedule_id))
        self._json(200, {"ok": True})

    def resync_schedule(self, query, schedule_id):
        self.agent.resync_schedule(int(schedule_id))
        self._json(200, {"ok": True})

    def test_schedule(self, query, schedule_id):
        self._check_schedule_tools((self.agent.store.schedule(int(schedule_id)) or {}).get("action_id"))
        self._json(200, self.agent.test_schedule(int(schedule_id)))


def _route(metodo: str, schema: str, funzione: Callable) -> Route:
    return metodo, re.compile("/api/v1" + schema), funzione


AREA = r"(cleanup|integrity|services|[^/]+)"
ROUTES: List[Route] = [
    _route("GET", "/agent/info", Handler.info),
    _route("POST", "/pair", Handler.pair),
    _route("POST", "/agent/token-check", Handler.token_check),
    _route("POST", "/agent/elevate", Handler.elevate),
    _route("POST", "/agent/shutdown", Handler.stop_all),
    _route("POST", "/agent/protect", Handler.protect),
    _route("GET", "/agent/protect", Handler.protection_status),
    _route("GET", "/events", Handler.event_list),
    _route("GET", "/events/meta", Handler.event_meta),
    _route("GET", "/hardware", Handler.hardware_inventory),
    _route("GET", "/hardware/sensors", Handler.hardware_sensors),
    _route("POST", "/hardware/monitor-tool", Handler.hardware_monitor_tool),
    _route("GET", "/processes", Handler.process_list),
    _route("POST", r"/processes/(\d{1,10})/(end|priority|reveal)", Handler.process_operation),
    _route("POST", "/processes/start", Handler.process_start),
    _route("GET", "/services/live", Handler.service_list),
    _route("POST", r"/services/([\w.\-@$]{1,128})/(start|stop|restart)", Handler.service_control),
    _route("GET", "/registry", Handler.registry_key),
    _route("GET", "/registry/search", Handler.registry_search),
    _route("GET", "/registry/export", Handler.registry_export),
    _route("GET", "/registry/backups", Handler.registry_backups),
    _route("GET", "/scripts", Handler.script_list),
    _route("POST", "/scripts", Handler.script_create),
    _route("GET", r"/scripts/([0-9a-f]{8})", Handler.script_get),
    _route("POST", r"/scripts/([0-9a-f]{8})/(save|delete|run|schedule|unschedule)", Handler.script_operation),
    _route("POST", "/shutdown-timer", Handler.timer_start),
    _route("POST", "/shutdown-timer/cancel", Handler.timer_cancel),
    _route("POST", r"/registry/(set|delete-value|rename-value|create-key|delete-key|restore)", Handler.registry_change),
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
    _route("POST", "/history/prune", Handler.prune_history),
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
    _route("GET", "/routines", Handler.list_routines),
    _route("POST", "/schedules", Handler.create_schedule),
    _route("PATCH", r"/schedules/(\d+)", Handler.update_schedule),
    _route("DELETE", r"/schedules/(\d+)", Handler.delete_schedule),
    _route("POST", r"/schedules/(\d+)/resync", Handler.resync_schedule),
    _route("POST", r"/schedules/(\d+)/test", Handler.test_schedule),
] + [_route(m, s, f) for m, s, f in ENTERPRISE_ROUTES] + [_route(m, s, f) for m, s, f in ACCOUNT_ROUTES] + [_route(m, s, f) for m, s, f in FEATURE_ROUTES]


DISCONNECTED = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)


class ApprovalPending(Exception):
    """A run that waits for a second person (2.10): answered 202 with the request."""

    def __init__(self, request: dict):
        super().__init__("approval pending")
        self.request = request


class AgentServer(ThreadingHTTPServer):
    # The console opens many requests at once (pages, live charts, activity): a longer queue never refuses one.
    request_queue_size = 64

    def handle_error(self, request, client_address) -> None:
        # A tab closed or reloaded mid-answer is normal: no traceback in the console or the log.
        if isinstance(sys.exc_info()[1], DISCONNECTED):
            return
        super().handle_error(request, client_address)


def make_server(agent: Agent, port: int) -> ThreadingHTTPServer:
    gestore = type("BoundHandler", (Handler,), {"agent": agent})
    server = AgentServer(("127.0.0.1", port), gestore)
    server.daemon_threads = True
    agent.port = server.server_address[1]
    agent.server = server
    agent.start_fleet_share()  # the read-only PC summary for other consoles, when turned on
    agent.start_phone_server()  # the console from a phone of the local network, when turned on (2.8)
    agent.start_enterprise()  # central server and client, escalation, SIEM (2.10)
    return server
