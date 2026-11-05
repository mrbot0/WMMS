"""The routes of the 2.12 features (wmm/agent/plus212.py) and the agent methods behind them. api.py mixes AgentPlus into
Agent and HandlerPlus into Handler and appends PLUS_ROUTES; permissions.py merges RULES. Everything here reads, except
moving files to the Recycle Bin, the automation settings, the delegations and the access review mark, which are audited
like every other write."""
from __future__ import annotations

import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import wmm

from ..agent import actions, advisor, appsettings, central, governance, notify, plus212
from .errors import ApiError


class AgentPlus:
    # Set by Agent in api.py (declared for the type checker).
    data_dir: Any
    store: Any
    machine_id: str
    hostname: str
    preview: bool
    accounts: Any
    jobs: Any

    _plus_goals_at = 0.0

    def plus_metrics(self) -> Dict[str, Optional[float]]:
        ultime = {a: self.store.last_scan(self.machine_id, a) for a in actions.AREAS}
        punteggi = {a: s["score"] for a, s in ultime.items() if s}
        valori: Dict[str, Optional[float]] = {f"area:{a}": punteggi.get(a) for a in actions.AREAS}
        valori["overall"] = advisor.overall_score(punteggi) if punteggi else None
        valori["open_issues"] = sum(len((s.get("data") or {}).get("recommendations", [])) for s in ultime.values() if s)
        sistema = self.store.last_scan(self.machine_id, "system")
        c = next((v for v in ((sistema or {}).get("data") or {}).get("volumes") or [] if v.get("letter") == "C"), None)
        valori["c_free_gb"] = c.get("free_gb") if c else None
        valori["c_free_pct"] = round(100 * c["free_gb"] / c["total_gb"], 1) if c and c.get("free_gb") is not None and c.get("total_gb") else None
        return valori

    def plus_goals(self) -> list:
        return plus212.evaluate_goals(appsettings.load(self.data_dir)["goals"], self.plus_metrics())

    def plus_changes(self) -> dict:
        prima = (datetime.now() - timedelta(hours=20)).isoformat(timespec="seconds")
        attuali = {a: self.store.last_scan(self.machine_id, a) for a in actions.AREAS}
        precedenti = {a: self.store.scan_before(self.machine_id, a, prima) for a in actions.AREAS}
        inizio = min((p["created"] for p in precedenti.values() if p), default=prima)
        esecuzioni = [r for r in self.store.runs(self.machine_id, limit=300) if str(r.get("started") or "") >= inizio]
        return plus212.changes(attuali, precedenti, esecuzioni)

    def plus_disk_forecast(self) -> dict:
        punti = []
        for s in self.store.scan_history(self.machine_id, "system", 200):
            c = next((v for v in (s.get("data") or {}).get("volumes") or [] if v.get("letter") == "C"), None)
            if c:
                punti.append((s["created"], c.get("free_gb"), c.get("total_gb")))
        return plus212.disk_forecast(punti)

    def plus_tick(self) -> None:
        """Every minute from the ticker: rules of the queued events, delegations that expired, goals (once an hour)."""
        regole = appsettings.load(self.data_dir)["automation_rules"]
        if regole:
            plus212.process_rules(self.data_dir, regole, lambda aid: self.jobs.start([aid], "rule", True))
        if self.accounts.enabled:
            plus212.end_delegations(self.accounts, self.data_dir)
        adesso = datetime.now().timestamp()
        if adesso - self._plus_goals_at >= 3600:
            self._plus_goals_at = adesso
            for g in self.plus_goals():
                if g["enabled"] and g["ok"] is False:
                    notify.safe_event(self.data_dir, "goal_missed", f"Goal not met: {g['metric']} {g['op']} {g['value']} (now {g['current']}).",
                                      gruppo=g["id"] + datetime.now().date().isoformat())


class HandlerPlus:
    # Set by Handler in api.py (declared for the type checker).
    agent: Any
    user: Optional[dict]
    _body: Any
    _json: Any
    _send: Any
    _wrap: Any

    # ---------- performance, storage, apps ----------
    def plus_slow(self, query):
        self._json(200, plus212.slow_now())

    def plus_disk_forecast(self, query):
        self._json(200, self.agent.plus_disk_forecast())

    def plus_folders(self, query):
        self._json(200, self._wrap(plus212.folder_map, str(query.get("path", "")), 20.0))

    def plus_duplicates(self, query):
        self._json(200, plus212.duplicates())

    def plus_forgotten(self, query):
        try:
            giorni = max(90, min(3650, int(query.get("days", 365))))
        except ValueError:
            giorni = 365
        self._json(200, plus212.forgotten(giorni=giorni))

    def plus_recycle(self, query):
        self._json(200, plus212.recycle(self._body().get("paths") or [], preview=self.agent.preview))

    def plus_recent_installs(self, query):
        try:
            giorni = max(1, min(365, int(query.get("days", 30))))
        except ValueError:
            giorni = 30
        self._json(200, {"apps": plus212.recent_installs(self.agent.apps().get("apps", []), giorni), "days": giorni})

    # ---------- security, updates, network ----------
    def plus_extensions(self, query):
        self._json(200, {"extensions": plus212.browser_extensions()})

    def plus_bitlocker(self, query):
        self._json(200, plus212.bitlocker())

    def plus_ports(self, query):
        self._json(200, {"ports": plus212.listening_ports()})

    def plus_windows_support(self, query):
        self._json(200, plus212.windows_version())

    def plus_update_calendar(self, query):
        self._json(200, plus212.update_calendar())

    def plus_internet_check(self, query):
        self._json(200, plus212.internet_check())

    # ---------- dashboard ----------
    def plus_changes(self, query):
        self._json(200, self.agent.plus_changes())

    def plus_goals(self, query):
        self._json(200, {"goals": self.agent.plus_goals(), "metrics": list(plus212.METRICS)})

    # ---------- hardware and support ----------
    def plus_label(self, query):
        asset = str(query.get("asset", ""))[:40]
        self._json(200, plus212.inventory_label(central.collect_inventory(), self.agent.hostname, self.agent.machine_id, asset))

    def plus_diagnostic(self, query):
        a = self.agent
        sistema = a.store.last_scan(a.machine_id, "system")
        parti = {
            "about": {"app": wmm.VERSION, "pc": socket.gethostname(), "machine_id": a.machine_id, "admin": getattr(a, "admin", None),
                      "preview": a.preview, "created": plus212.now()},
            "dashboard": a.dashboard(), "recommendations": a.recommendations(), "system": (sistema or {}).get("data") or {},
            "history": a.store.runs(a.machine_id, limit=200), "schedules": a.store.schedules(), "health": a.health(False),
            "app_settings": appsettings.load(a.data_dir), "goals": a.plus_goals(),
        }
        nome = f"wmm-diagnostic-{socket.gethostname()}-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
        self._send(200, plus212.diagnostic_package(parti), "application/zip", {"Content-Disposition": f'attachment; filename="{nome}"'})

    # ---------- automation and backup settings ----------
    def plus_automation_get(self, query):
        s = appsettings.load(self.agent.data_dir)
        self._json(200, {"rules": s["automation_rules"], "goals": s["goals"], "winget_exclusions": s["winget_exclusions"],
                         "events": [{"id": k, "title": v} for k, v in notify.EVENTS.items()], "metrics": list(plus212.METRICS),
                         "file_backup": s["file_backup"], "backup_status": plus212.backup_status(self.agent.data_dir)})

    def plus_automation_put(self, query):
        corpo = self._body()
        valori = {k: corpo[k] for k in ("automation_rules", "goals", "winget_exclusions", "file_backup") if k in corpo}
        try:
            appsettings.save(self.agent.data_dir, valori)
        except appsettings.SettingsError as e:
            raise ApiError(400, str(e)) from None
        self.plus_automation_get(query)

    # ---------- people: delegations and access review ----------
    def plus_delegations_get(self, query):
        self._json(200, {"delegations": plus212.delegations(self.agent.data_dir)})

    def plus_delegations_post(self, query):
        corpo = self._body()
        self._json(201, self._wrap(plus212.delegate, self.agent.accounts, self.agent.data_dir, str(corpo.get("username", "")), str(corpo.get("role_id", "")),
                                   corpo.get("hours"), self.user))

    def plus_delegation_delete(self, query, nome):
        finiti = plus212.end_delegations(self.agent.accounts, self.agent.data_dir, username=nome, adesso=datetime.now() - timedelta(days=36500))
        if not finiti:
            raise ApiError(404, "No temporary role for this user.")
        self._json(200, {"ended": finiti})

    def plus_access_review(self, query):
        acc = self.agent.accounts
        revisione = governance.load_settings(self.agent.data_dir).get("access_review") or {}
        self._json(200, plus212.access_review(acc.users(), governance.tokens(acc), revisione))

    def plus_access_review_done(self, query):
        voce = {"by": (self.user or {}).get("username", "local"), "at": plus212.now(), "note": str(self._body().get("note", ""))[:300]}
        governance.save_settings(self.agent.data_dir, "access_review", voce)
        self._json(200, voce)


NOME = r"([\w.\-@]{1,64})"
PLUS_ROUTES = [
    ("GET", "/plus/slow-now", HandlerPlus.plus_slow),
    ("GET", "/plus/disk-forecast", HandlerPlus.plus_disk_forecast),
    ("GET", "/plus/folders", HandlerPlus.plus_folders),
    ("POST", "/plus/duplicates", HandlerPlus.plus_duplicates),
    ("POST", "/plus/forgotten", HandlerPlus.plus_forgotten),
    ("POST", "/plus/recycle", HandlerPlus.plus_recycle),
    ("GET", "/plus/recent-installs", HandlerPlus.plus_recent_installs),
    ("GET", "/plus/extensions", HandlerPlus.plus_extensions),
    ("GET", "/plus/ports", HandlerPlus.plus_ports),
    ("GET", "/plus/bitlocker", HandlerPlus.plus_bitlocker),
    ("GET", "/plus/windows-support", HandlerPlus.plus_windows_support),
    ("GET", "/plus/update-calendar", HandlerPlus.plus_update_calendar),
    ("POST", "/plus/internet-check", HandlerPlus.plus_internet_check),
    ("GET", "/plus/changes", HandlerPlus.plus_changes),
    ("GET", "/plus/goals", HandlerPlus.plus_goals),
    ("GET", "/plus/label", HandlerPlus.plus_label),
    ("GET", "/plus/diagnostic.zip", HandlerPlus.plus_diagnostic),
    ("GET", "/plus/automation", HandlerPlus.plus_automation_get),
    ("PUT", "/plus/automation", HandlerPlus.plus_automation_put),
    ("GET", "/plus/delegations", HandlerPlus.plus_delegations_get),
    ("POST", "/plus/delegations", HandlerPlus.plus_delegations_post),
    ("DELETE", "/plus/delegations/" + NOME, HandlerPlus.plus_delegation_delete),
    ("GET", "/plus/access-review", HandlerPlus.plus_access_review),
    ("POST", "/plus/access-review", HandlerPlus.plus_access_review_done),
]

RULES = {
    "plus_slow": "view.performance", "plus_disk_forecast": "view.storage", "plus_folders": "view.storage", "plus_duplicates": "view.storage",
    "plus_forgotten": "view.storage", "plus_recycle": ("view.storage", "run.cleanup.moderate"), "plus_recent_installs": "view.apps",
    "plus_extensions": "view.security", "plus_ports": "view.security", "plus_bitlocker": "view.security", "plus_windows_support": "view.updates", "plus_update_calendar": "view.updates",
    "plus_internet_check": "view.network", "plus_changes": "view.dashboard", "plus_goals": "view.dashboard", "plus_label": "view.hardware",
    "plus_diagnostic": ("view.support", "export.data"), "plus_automation_get": "view.settings", "plus_automation_put": "settings.edit",
    "plus_delegations_get": "users.view", "plus_delegations_post": ("users.manage", "roles.manage"), "plus_delegation_delete": "users.manage",
    "plus_access_review": ("users.view", "audit.view"), "plus_access_review_done": "users.manage",
}
