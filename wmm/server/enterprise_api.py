"""Enterprise features of 2.10: the agent side (central server and client, escalation, SIEM) and the routes of company
sign-in, approvals, API tokens, audit chain, SIEM, tickets, incidents, HTTPS, encryption, ransomware protection,
background agent, central server, inventory, software, update rings, baselines and the executive report.
Mixed into Agent and Handler like the other feature modules; wmm/server/permissions.py maps every route."""
from __future__ import annotations

import base64
import json
import re
import socket
import sys
import threading
import time
from typing import Any, Optional
from datetime import datetime
from html import escape as html_escape

import wmm

from ..agent import (accounts, appsettings, baselines, canary, central, centralmove, deploy, governance, incidents, pdfreport, securestore, service, sso,
                     tickets, tlsutil, updatepolicy)
from .errors import ApiError


def _err(e: Exception) -> ApiError:
    return ApiError(getattr(e, "status", 400), str(e))


class AgentEnterprise:
    # Set by Agent in api.py, which mixes this class in (declared for the type checker).
    accounts: Any
    data_dir: Any
    hostname: str
    machine_id: str
    preview: bool
    jobs: Any
    pc_summary: Any
    # ---------- start ----------

    def start_enterprise(self) -> None:
        self.accounts.audit_hooks.append(lambda voce: governance.forward(self.data_dir, voce))
        self._central_server = central.Server(self.data_dir)
        self.start_central_server()
        self.central_client = central.Client(self.data_dir, self._central_execute, self.pc_summary, self.hostname, self.machine_id, wmm.VERSION)
        if not self.preview:
            self.central_client.start()
        threading.Thread(target=self._ticker, name="wmm-ticker", daemon=True).start()

    def _ticker(self) -> None:
        while True:
            try:
                incidents.escalate_due(self.data_dir)
            except Exception:  # noqa: BLE001 - try again in a minute
                pass
            tick = getattr(self, "plus_tick", None)
            if tick:
                try:
                    tick()
                except Exception:  # noqa: BLE001 - the same
                    pass
            time.sleep(60)

    def central_server_settings(self) -> dict:
        s = governance.load_settings(self.data_dir).get("central_server") or {}
        return {"enabled": bool(s.get("enabled")), "port": int(s.get("port") or central.DEFAULT_PORT),
                "running": getattr(self, "_central_http", None) is not None}

    def start_central_server(self) -> None:
        vecchio = getattr(self, "_central_http", None)
        if vecchio is not None:
            vecchio.shutdown()
            vecchio.server_close()
            self._central_http = None
        s = self.central_server_settings()
        if not s["enabled"] or self.preview:
            return
        try:
            self._central_http = central.server_http(self._central_server, s["port"], self.data_dir, tls=True)
        except OSError as errore:
            sys.stderr.write(f"The central server could not start on port {s['port']}: {errore}\n")

    def _central_execute(self, lavoro: dict) -> dict:
        """A job sent by the central server, already allowed by central.allowed_job for this PC."""
        tipo, carico = lavoro["kind"], lavoro.get("payload") or {}
        if tipo == "actions":
            ids = [a for a in carico.get("actions", []) if isinstance(a, str)][:20]
            stato = self.jobs.run_sync(ids, "central", True)
            return {"results": [{k: r.get(k) for k in ("action_id", "status", "note", "verify")} for r in stato["results"]]}
        if tipo == "winget":
            return deploy.run(carico.get("op", "install"), str(carico.get("id", "")), preview=self.preview)
        if tipo == "policy":
            return updatepolicy.apply_ring(updatepolicy.clean_ring(carico.get("ring") or {}), preview=self.preview)
        if tipo == "baseline":
            esito = baselines.evaluate([c for c in carico.get("checks", []) if isinstance(c, str)])
            if carico.get("fix") and esito["failing"]:
                stato = self.jobs.run_sync(esito["failing"], "central", True)
                esito["fixed"] = [r["action_id"] for r in stato["results"] if r["status"] in ("ok", "warning")]
            return esito
        if tipo == "inventory":
            return {"inventory": central.collect_inventory()}
        raise ValueError("unknown job")


class _ScopedServer:
    """The central server as a user limited to some clients sees it (for the executive report)."""

    def __init__(self, server, scope):
        self._server, self._scope = server, scope

    def agents(self, *a, **k):
        return self._server.agents(*a, scope=self._scope, **k)

    def agent(self, agent_id):
        return self._server.agent(agent_id, self._scope)

    def overview(self):
        return self._server.overview(self._scope)


class HandlerEnterprise:
    # Set by Handler in api.py, which mixes this class in (declared for the type checker).
    agent: Any
    user: Optional[dict]
    _body: Any
    _check_role_tools: Any
    _check_tools: Any
    def _me(self) -> dict:
        if self.user is None:
            raise ApiError(409, "Turn accounts on first (Settings › Accounts and security).")
        return self.user

    def _role_ids(self):
        return [r["id"] for r in self.agent.accounts.roles()]

    def _wrap(self, funzione, *a, **k):
        try:
            return funzione(*a, **k)
        except (governance.GovernanceError, sso.SsoError, central.CentralError, accounts.AccountError, ValueError, KeyError) as e:
            if isinstance(e, KeyError):
                raise ApiError(404, "Not found.") from None
            raise _err(e) from None
        except OSError as e:
            raise ApiError(502, str(e)[:300]) from None

    # ---------- company sign-in ----------

    def sso_state(self, query):
        s = sso.settings(self.agent.data_dir)
        self._json(200, {"oidc": s["oidc_enabled"] and bool(s["issuer"] and s["client_id"]), "windows": s["windows_enabled"]})

    def sso_get(self, query):
        self._json(200, dict(sso.settings(self.agent.data_dir), redirect=f"http://127.0.0.1:{self.agent.port}/api/v1/auth/oidc/callback"))

    def sso_put(self, query):
        self._json(200, self._wrap(sso.save, self.agent.data_dir, self._body(), self._role_ids()))

    def oidc_start(self, query):
        self._json(200, {"url": self._wrap(sso.start, self.agent.data_dir, f"http://127.0.0.1:{self.agent.port}/api/v1/auth/oidc/callback")})

    def oidc_callback(self, query):
        try:
            if query.get("error"):
                raise sso.SsoError(query.get("error_description") or query["error"], 401)
            c = sso.finish(self.agent.data_dir, query.get("state", ""), query.get("code", ""))
            identita = sso.oidc_identity(self.agent.data_dir, c)
            esito = self.agent.accounts.login_external(identita, self.client_address[0], self.headers.get("User-Agent", ""), "entra",
                                                       sso.settings(self.agent.data_dir)["auto_create"])
            pagina = ("<!DOCTYPE html><meta charset=utf-8><title>WMM</title><script>sessionStorage.setItem('wmm.session'," +
                      json.dumps(esito["token"]) + ");location.replace('/#/dashboard');</script>")
        except (sso.SsoError, accounts.AccountError) as e:
            pagina = ("<!DOCTYPE html><meta charset=utf-8><title>WMM</title><body style='font-family:sans-serif;padding:40px'><h2>Sign-in failed</h2><p>" +
                      html_escape(str(e)) + "</p><p><a href='/'>Back</a></p>")
        self._send(200, pagina.encode("utf-8"), "text/html; charset=utf-8")

    def windows_login(self, query):
        corpo = self._body()
        s = sso.settings(self.agent.data_dir)
        if not s["windows_enabled"]:
            raise ApiError(409, "Windows sign-in is off.")
        utente, password = str(corpo.get("username", "")).strip(), str(corpo.get("password", ""))
        if not utente or not password:
            raise ApiError(400, "Write the Windows user name and password.")
        gruppi = sso.windows_logon(utente, password)
        if gruppi is None:
            self.agent.accounts.audit(utente[:64], "login.fail", "", "windows", ok=False)
            raise ApiError(401, "Windows refused the user name or password.")
        self._json(200, self._wrap(self.agent.accounts.login_external, sso.windows_identity(self.agent.data_dir, utente, gruppi),
                                   self.client_address[0], self.headers.get("User-Agent", ""), "windows"))

    # ---------- approvals and tokens ----------

    def approvals_get(self, query):
        self._json(200, {"approvals": governance.listing(self.agent.accounts, query.get("status", "")), "levels": governance.approval_levels(self.agent.data_dir)})

    def approval_decide(self, query, ident, azione):
        def avvia(ids, requester_id):
            return self.agent.start_run(ids, True, origin="approved")
        self._json(200, self._wrap(governance.decide, self.agent.accounts, int(ident), self._me(), azione == "approve", self._body().get("note", ""), avvia))

    def tokens_get(self, query):
        tutti = query.get("all") == "1" and "users.manage" in (self.user or {}).get("permissions", ())
        self._json(200, {"tokens": governance.tokens(self.agent.accounts, None if tutti else self._me()["id"])})

    def token_create(self, query):
        corpo = self._body()
        self._json(201, self._wrap(governance.create_token, self.agent.accounts, self._me(), corpo.get("name"), corpo.get("scopes") or [], corpo.get("days", 90)))

    def token_delete(self, query, ident):
        self._wrap(governance.revoke_token, self.agent.accounts, ident, self._me())
        self._json(200, {"ok": True})

    def audit_verify(self, query):
        self._json(200, governance.verify(self.agent.accounts))

    # ---------- SIEM, tickets, escalation, incidents ----------

    def siem_get(self, query):
        self._json(200, governance.siem_settings(self.agent.data_dir))

    def siem_put(self, query):
        self._json(200, self._wrap(governance.save_siem, self.agent.data_dir, self._body()))

    def siem_test(self, query):
        voce = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": self._by() if hasattr(self, "_by") else "local", "action": "siem.test",
                "target": "", "detail": "Test from Windows Maintenance Manager", "ok": True}
        governance.forward(self.agent.data_dir, voce, sync=True)
        self._json(200, {"sent": True})

    def tickets_get(self, query):
        self._json(200, tickets.settings(self.agent.data_dir))

    def tickets_put(self, query):
        self._json(200, self._wrap(tickets.save, self.agent.data_dir, self._body()))

    def tickets_test(self, query):
        self._json(200, tickets.create(self.agent.data_dir, "Test from Windows Maintenance Manager", "This ticket was opened by a test from the console."))

    def escalation_get(self, query):
        self._json(200, incidents.settings(self.agent.data_dir))

    def escalation_put(self, query):
        self._json(200, self._wrap(incidents.save_settings, self.agent.data_dir, self._body(), self._role_ids()))

    def incidents_get(self, query):
        self._json(200, {"incidents": incidents.listing(self.agent.data_dir, query.get("status", ""))})

    def incident_update(self, query, ident, azione):
        utente = (self.user or {}).get("username", "local")
        voce = self._wrap(incidents.update, self.agent.data_dir, ident, azione, utente, self._body().get("note", ""))
        self.agent.accounts.audit(utente, "incident." + azione, voce["title"][:200], voce.get("note", ""))
        self._json(200, voce)

    # ---------- HTTPS, encryption, ransomware, background agent ----------

    def tls_get(self, query):
        cartella = self.agent.data_dir / "tls"
        info = tlsutil.ensure(self.agent.data_dir) if (cartella / "server.crt").exists() else None
        self._json(200, {"https_lan": appsettings.load(self.agent.data_dir).get("https_lan", False), "fingerprint": info["fingerprint"] if info else None})

    def tls_put(self, query):
        attivo = bool(self._body().get("enabled"))
        info = tlsutil.ensure(self.agent.data_dir) if attivo else None
        appsettings.save(self.agent.data_dir, {"https_lan": attivo})
        self.agent.start_fleet_share()
        self.agent.start_phone_server()
        self._json(200, {"https_lan": attivo, "fingerprint": info["fingerprint"] if info else None})

    def tls_regenerate(self, query):
        for nome in ("server.crt", "server.key"):
            (self.agent.data_dir / "tls" / nome).unlink(missing_ok=True)
        info = tlsutil.ensure(self.agent.data_dir)
        self.agent.start_fleet_share()
        self.agent.start_phone_server()
        self.agent.start_central_server()
        self._json(200, {"fingerprint": info["fingerprint"]})

    def encryption_put(self, query):
        attivo = bool(self._body().get("enabled"))
        appsettings.save(self.agent.data_dir, {"encrypt_data": attivo})
        self._json(200, {"enabled": attivo, "converted": self._wrap(securestore.convert, self.agent.data_dir, attivo)})

    def canary_get(self, query):
        self._json(200, {"decoys": canary.state(self.agent.data_dir), "cfa": canary.cfa_state()})

    def canary_place(self, query):
        if self.agent.preview:
            raise ApiError(409, "Decoy files are not placed in preview mode.")
        self._json(200, {"decoys": canary.place(self.agent.data_dir)})

    def canary_remove(self, query):
        self._json(200, {"removed": canary.remove(self.agent.data_dir)})

    def cfa_put(self, query):
        self.agent._guard_changes()
        if self.agent.preview:
            raise ApiError(409, "Nothing changes in preview mode.")
        self._wrap(canary.cfa_set, str(self._body().get("mode", "")))
        self._json(200, canary.cfa_state())

    def service_get(self, query):
        self._json(200, service.status())

    def service_install(self, query):
        self.agent._guard_changes()
        if self.agent.preview:
            raise ApiError(409, "Nothing changes in preview mode.")
        self._json(200, self._wrap(service.install, self.agent.python, self.agent.script, self.agent.port))

    def service_remove(self, query):
        self.agent._guard_changes()
        self._json(200, self._wrap(service.uninstall))

    # ---------- central server ----------

    @property
    def _srv(self) -> central.Server:
        return self.agent._central_server

    @property
    def _scope(self) -> central.Scope:
        """The clients the signed-in user may see on the central server (None: every client)."""
        return self._srv.scope_for((self.user or {}).get("username"))

    def _shared_change(self) -> None:
        """Server settings, groups, catalog and rings are shared by every client: not for someone limited to some clients."""
        if self._scope is not None:
            raise ApiError(403, "You manage only some clients: settings shared by every client are changed by the provider's staff.")

    def central_get(self, query):
        info = tlsutil.ensure(self.agent.data_dir) if self.agent.central_server_settings()["enabled"] else None
        ambito = self._scope
        clienti = [t for t in self._srv.tenants() if ambito is None or t["id"] in ambito]
        if ambito is not None:
            clienti = [dict(t, users=[]) for t in clienti]
        self._json(200, {"server": self.agent.central_server_settings(), "fingerprint": info["fingerprint"] if info else None,
                         "overview": self._srv.overview(ambito),
                         "agents": self._srv.agents(query.get("group", ""), query.get("q", ""), ambito, query.get("tenant", "")),
                         "groups": self._srv.groups(ambito), "rings": self._srv.rings(), "catalog": self._srv.catalog(), "jobs": self._srv.recent_jobs(50, ambito),
                         "tenants": clienti, "limited": ambito is not None})

    def central_server_put(self, query):
        self._shared_change()
        corpo = self._body()
        porta = corpo.get("port", central.DEFAULT_PORT)
        if isinstance(porta, bool) or not isinstance(porta, int) or not 1024 <= porta <= 65535:
            raise ApiError(400, "The port is a number from 1024 to 65535.")
        governance.save_settings(self.agent.data_dir, "central_server", {"enabled": bool(corpo.get("enabled")), "port": porta})
        if corpo.get("enabled"):
            tlsutil.ensure(self.agent.data_dir)
        self.agent.start_central_server()
        self._json(200, self.agent.central_server_settings())

    def central_code(self, query):
        corpo = self._body()
        host = str(corpo.get("host") or socket.gethostname())
        if not re.fullmatch(r"[\w.\-]{1,253}", host):
            raise ApiError(400, "The address the PCs use to reach this server: a name or an IP.")
        info = tlsutil.ensure(self.agent.data_dir)
        tags = corpo.get("tags") or []
        cliente = str(corpo.get("tenant") or "")
        ambito = self._scope
        if ambito is not None and cliente not in ambito:
            raise ApiError(403, "Choose one of your clients for the new PCs.")
        self._json(200, self._wrap(self._srv.enrollment_code, host, self.agent.central_server_settings()["port"], info["fingerprint"],
                                   tags if isinstance(tags, list) else [], cliente))

    def central_agent_get(self, query, ident):
        self._json(200, self._wrap(self._srv.agent, ident, self._scope))

    def central_agent_delete(self, query, ident):
        self._wrap(self._srv.remove, ident, self._scope)
        self._json(200, {"ok": True})

    def central_agent_tags(self, query, ident):
        self._json(200, {"tags": self._wrap(self._srv.set_tags, ident, self._body().get("tags"), self._scope)})

    def central_agent_asset(self, query, ident):
        self._json(200, self._wrap(self._srv.set_asset, ident, self._body(), self._scope))

    def central_jobs_post(self, query):
        corpo = self._body()
        tipo, carico, destinatari = self._central_job(corpo)
        self._json(202, self._wrap(self._srv.queue, destinatari, tipo, carico, (self.user or {}).get("username", "local")))

    def _central_job(self, corpo: dict) -> tuple:
        """The checks of a job for the PCs (also for campaigns, 2.12): the same rules as running the tools here."""
        tipo, carico = corpo.get("kind"), corpo.get("payload") or {}
        if tipo in ("actions", "baseline"):
            ids = list(carico.get("actions") or []) if tipo == "actions" else (list(carico.get("checks") or []) if carico.get("fix") else [])
            if ids:
                noti = self._check_role_tools(ids)
                if governance.needs_approval(self.agent.data_dir, self.user, noti):
                    raise ApiError(409, "These tools need the approval of a second person: someone who may skip approvals must send this job.")
                self._check_tools(ids, corpo)  # high-risk lock, reason, confirmation with the PC name
        if tipo == "policy":
            carico = dict(carico, ring=self._wrap(updatepolicy.clean_ring, carico.get("ring") or {}))
        if tipo == "winget" and "deploy.manage" not in (self.user or {"permissions": ["deploy.manage"]})["permissions"]:
            raise ApiError(403, "Your role does not allow installing software.")
        if tipo == "policy" and "updates.policy" not in (self.user or {"permissions": ["updates.policy"]})["permissions"]:
            raise ApiError(403, "Your role does not allow update policies.")
        if tipo == "relocate":
            self._shared_change()
        if tipo == "winget" and not deploy.valid_id(str(carico.get("id", ""))):
            raise ApiError(400, "Unknown winget ID.")
        ambito = self._scope
        return tipo, carico, self._srv.targets(corpo.get("agents"), str(corpo.get("group", "")), ambito, str(corpo.get("tenant", "") or ""))

    def central_campaigns_get(self, query):
        self._json(200, {"campaigns": self._srv.campaigns(self._scope)})

    def central_campaigns_post(self, query):
        corpo = self._body()
        tipo, carico, destinatari = self._central_job(corpo)
        if tipo == "relocate":
            raise ApiError(400, "Moving the server is not a campaign.")
        self._json(201, self._wrap(self._srv.create_campaign, corpo.get("name"), str(corpo.get("deadline") or ""), destinatari, tipo, carico,
                                   (self.user or {}).get("username", "local")))

    def central_batch_get(self, query, lotto):
        self._json(200, {"jobs": self._srv.batch(lotto, self._scope)})

    def central_job_delete(self, query, ident):
        self._wrap(self._srv.cancel_job, int(ident), self._scope)
        self._json(200, {"ok": True})

    def central_groups_post(self, query):
        self._shared_change()
        self._json(200, self._wrap(self._srv.save_group, self._body()))

    def central_group_delete(self, query):
        self._shared_change()
        self._srv.delete_group(str(self._body().get("name", "")))
        self._json(200, {"ok": True})

    def central_software(self, query):
        self._json(200, {"software": self._srv.software_search(query.get("q", ""), self._scope)})

    def central_inventory_csv(self, query):
        self._send(200, ("\ufeff" + self._srv.inventory_csv(self._scope)).encode("utf-8"), "text/csv; charset=utf-8",
                   {"Content-Disposition": 'attachment; filename="wmm-inventory.csv"'})

    def central_catalog_post(self, query):
        self._shared_change()
        self._json(200, self._wrap(self._srv.save_catalog, self._body()))

    def central_catalog_delete(self, query, ident):
        self._shared_change()
        self._srv.delete_catalog(ident)
        self._json(200, {"ok": True})

    def central_rings_post(self, query):
        self._shared_change()
        self._json(200, self._wrap(self._srv.save_ring, self._body()))

    def central_ring_delete(self, query, ident):
        self._shared_change()
        self._srv.delete_ring(ident)
        self._json(200, {"ok": True})

    def central_rings_assign(self, query):
        corpo = self._body()
        ambito = self._scope
        self._json(200, {"assigned": self._wrap(self._srv.assign_ring, self._srv.targets(corpo.get("agents"), str(corpo.get("group", "")), ambito),
                                                str(corpo.get("ring", "")), ambito)})

    # ---------- backup, restore and move (2.11) ----------

    def _bundle(self) -> tuple:
        corpo = self._body()
        try:
            blob = base64.b64decode(str(corpo.get("bundle", "")), validate=True)
        except ValueError:
            raise ApiError(400, "Choose the backup file.") from None
        return blob, str(corpo.get("password", ""))

    def central_backup(self, query):
        self._shared_change()
        corpo = self._body()
        blob = self._wrap(centralmove.export, self.agent.data_dir, str(corpo.get("password", "")), self.agent.central_server_settings()["port"])
        nome = f"wmm-central-{datetime.now().strftime('%Y%m%d-%H%M')}.wmmcentral"
        self._send(200, blob, "application/octet-stream", {"Content-Disposition": f'attachment; filename="{nome}"'})

    def central_inspect(self, query):
        self._shared_change()
        blob, password = self._bundle()
        self._json(200, self._wrap(centralmove.inspect, blob, password))

    def central_restore(self, query):
        """Replaces the central server of this PC with a backup (moving the server to this PC)."""
        self._shared_change()
        blob, password = self._bundle()
        if self._body().get("confirm") is not True:
            raise ApiError(400, "Confirm that the central server of this PC is replaced.")
        vecchio = getattr(self.agent, "_central_http", None)
        if vecchio is not None:
            vecchio.shutdown()
            vecchio.server_close()
            self.agent._central_http = None
        esito = self._wrap(centralmove.restore, self.agent.data_dir, blob, password)
        self.agent._central_server = central.Server(self.agent.data_dir)
        governance.save_settings(self.agent.data_dir, "central_server", {"enabled": True, "port": int(esito["port"])})
        self.agent.start_central_server()
        self._json(200, esito)

    # ---------- clients (tenants, 2.11) ----------

    def central_tenants_get(self, query):
        ambito = self._scope
        self._json(200, {"tenants": [dict(t, users=t["users"] if ambito is None else []) for t in self._srv.tenants() if ambito is None or t["id"] in ambito],
                         "limited": ambito is not None})

    def central_tenants_post(self, query):
        self._shared_change()
        self._json(200, self._wrap(self._srv.save_tenant, self._body()))

    def central_tenant_delete(self, query, ident):
        self._shared_change()
        self._wrap(self._srv.delete_tenant, ident)
        self._json(200, {"ok": True})

    def central_tenants_move(self, query):
        self._shared_change()
        corpo = self._body()
        agenti = corpo.get("agents") if isinstance(corpo.get("agents"), list) else []
        self._json(200, {"moved": self._wrap(self._srv.move_to_tenant, agenti, str(corpo.get("tenant", "") or ""))})

    def central_tenants_access(self, query):
        """Which clients a console user may see: none = every client."""
        self._shared_change()
        corpo = self._body()
        nome = str(corpo.get("username", "")).strip()
        if not re.fullmatch(r"[\w.\-@]{1,64}", nome):
            raise ApiError(400, "User name.")
        self._json(200, {"username": nome, "tenants": self._wrap(self._srv.set_access, nome, corpo.get("tenants"))})

    # ---------- this PC as an agent ----------

    def client_get(self, query):
        self._json(200, central.client_settings(self.agent.data_dir))

    def client_enroll(self, query):
        self.agent._guard_changes()
        self._json(200, self._wrap(central.enroll, self.agent.data_dir, str(self._body().get("code", "")), self.agent.hostname, self.agent.machine_id))

    def client_put(self, query):
        corpo = self._body()
        self._json(200, self._wrap(central.set_client, self.agent.data_dir, corpo.get("interval"), corpo.get("level")))

    def client_leave(self, query):
        central.leave(self.agent.data_dir)
        self._json(200, central.client_settings(self.agent.data_dir))

    def client_contact(self, query):
        self._wrap(self.agent.central_client.contact)
        self._json(200, central.client_settings(self.agent.data_dir))

    # ---------- software, updates, baselines on this PC ----------

    def winget_post(self, query):
        corpo = self._body()
        self.agent._guard_changes()
        esito = self._wrap(deploy.run, str(corpo.get("op", "install")), str(corpo.get("id", "")), preview=self.agent.preview)
        self.agent.accounts.audit((self.user or {}).get("username", "local"), "software." + str(corpo.get("op")), str(corpo.get("id"))[:120],
                                  "ok" if esito["ok"] else str(esito.get("output", ""))[-200:], ok=esito["ok"])
        self._json(200, esito)

    def updates_compliance(self, query):
        self._json(200, self._wrap(updatepolicy.compliance))

    def updates_ring_apply(self, query):
        self.agent._guard_changes()
        self._json(200, self._wrap(updatepolicy.apply_ring, self._wrap(updatepolicy.clean_ring, self._body().get("ring") or {}), self.agent.preview))

    def baselines_get(self, query):
        self._json(200, {"baselines": baselines.baselines(self.agent.data_dir), "checks": baselines.available_checks()})

    def baseline_post(self, query):
        self._json(201, self._wrap(baselines.save, self.agent.data_dir, self._body()))

    def baseline_put(self, query, ident):
        self._json(200, self._wrap(baselines.save, self.agent.data_dir, self._body(), ident))

    def baseline_delete(self, query, ident):
        self._wrap(baselines.delete, self.agent.data_dir, ident)
        self._json(200, {"ok": True})

    def baseline_run(self, query, ident):
        self._json(200, self._wrap(baselines.run, self.agent.data_dir, ident))

    def baseline_fix(self, query, ident):
        corpo = self._body()
        esito = self._wrap(baselines.run, self.agent.data_dir, ident)
        if not esito["failing"]:
            self._json(200, {"nothing": True})
            return
        self._check_tools(esito["failing"], corpo)
        self._json(202, {"id": self.agent.start_run(esito["failing"], True, origin="baseline"), "actions": esito["failing"]})

    def executive_pdf(self, query):
        lingua = query.get("lang") if query.get("lang") in ("it", "en") else "it"
        try:
            giorni = max(7, min(366, int(query.get("days", 30))))
        except ValueError:
            giorni = 30
        ambito = self._scope
        srv = _ScopedServer(self._srv, ambito) if self._srv.agents(scope=ambito) else None  # only the clients this user sees (2.11)
        dati = pdfreport.collect(self.agent.data_dir, self.agent.store, self.agent.machine_id, srv, appsettings.load(self.agent.data_dir)["org_name"],
                                 lingua, giorni)
        self._send(200, pdfreport.build(dati, lingua), "application/pdf", {"Content-Disposition": 'attachment; filename="wmm-executive-report.pdf"'})


ID_AGENT = r"(a[0-9a-f]{16})"
ENTERPRISE_ROUTES = [
    ("GET", "/auth/sso", HandlerEnterprise.sso_state),
    ("GET", "/auth/oidc/start", HandlerEnterprise.oidc_start),
    ("GET", "/auth/oidc/callback", HandlerEnterprise.oidc_callback),
    ("POST", "/auth/windows", HandlerEnterprise.windows_login),
    ("GET", "/integrations/sso", HandlerEnterprise.sso_get),
    ("PUT", "/integrations/sso", HandlerEnterprise.sso_put),
    ("GET", "/approvals", HandlerEnterprise.approvals_get),
    ("POST", r"/approvals/(\d{1,9})/(approve|reject)", HandlerEnterprise.approval_decide),
    ("GET", "/tokens", HandlerEnterprise.tokens_get),
    ("POST", "/tokens", HandlerEnterprise.token_create),
    ("DELETE", r"/tokens/(t[0-9a-f]{12})", HandlerEnterprise.token_delete),
    ("GET", "/audit/verify", HandlerEnterprise.audit_verify),
    ("GET", "/integrations/siem", HandlerEnterprise.siem_get),
    ("PUT", "/integrations/siem", HandlerEnterprise.siem_put),
    ("POST", "/integrations/siem/test", HandlerEnterprise.siem_test),
    ("GET", "/integrations/tickets", HandlerEnterprise.tickets_get),
    ("PUT", "/integrations/tickets", HandlerEnterprise.tickets_put),
    ("POST", "/integrations/tickets/test", HandlerEnterprise.tickets_test),
    ("GET", "/integrations/escalation", HandlerEnterprise.escalation_get),
    ("PUT", "/integrations/escalation", HandlerEnterprise.escalation_put),
    ("GET", "/incidents", HandlerEnterprise.incidents_get),
    ("POST", r"/incidents/([0-9a-f]{12})/(ack|close|reopen)", HandlerEnterprise.incident_update),
    ("GET", "/security/tls", HandlerEnterprise.tls_get),
    ("PUT", "/security/tls", HandlerEnterprise.tls_put),
    ("POST", "/security/tls/regenerate", HandlerEnterprise.tls_regenerate),
    ("PUT", "/security/encryption", HandlerEnterprise.encryption_put),
    ("GET", "/security/canary", HandlerEnterprise.canary_get),
    ("POST", "/security/canary", HandlerEnterprise.canary_place),
    ("DELETE", "/security/canary", HandlerEnterprise.canary_remove),
    ("PUT", "/security/cfa", HandlerEnterprise.cfa_put),
    ("GET", "/agent/service", HandlerEnterprise.service_get),
    ("POST", "/agent/service", HandlerEnterprise.service_install),
    ("DELETE", "/agent/service", HandlerEnterprise.service_remove),
    ("GET", "/central", HandlerEnterprise.central_get),
    ("GET", "/central/tenants", HandlerEnterprise.central_tenants_get),
    ("GET", "/central/campaigns", HandlerEnterprise.central_campaigns_get),
    ("POST", "/central/campaigns", HandlerEnterprise.central_campaigns_post),
    ("POST", "/central/backup", HandlerEnterprise.central_backup),
    ("POST", "/central/backup/inspect", HandlerEnterprise.central_inspect),
    ("POST", "/central/restore", HandlerEnterprise.central_restore),
    ("POST", "/central/tenants", HandlerEnterprise.central_tenants_post),
    ("DELETE", r"/central/tenants/(k[0-9a-f]{10})", HandlerEnterprise.central_tenant_delete),
    ("POST", "/central/tenants/move", HandlerEnterprise.central_tenants_move),
    ("PUT", "/central/tenants/access", HandlerEnterprise.central_tenants_access),
    ("PUT", "/central/server", HandlerEnterprise.central_server_put),
    ("POST", "/central/enroll-code", HandlerEnterprise.central_code),
    ("GET", f"/central/agents/{ID_AGENT}", HandlerEnterprise.central_agent_get),
    ("DELETE", f"/central/agents/{ID_AGENT}", HandlerEnterprise.central_agent_delete),
    ("PUT", f"/central/agents/{ID_AGENT}/tags", HandlerEnterprise.central_agent_tags),
    ("PUT", f"/central/agents/{ID_AGENT}/asset", HandlerEnterprise.central_agent_asset),
    ("POST", "/central/jobs", HandlerEnterprise.central_jobs_post),
    ("GET", r"/central/batches/([0-9a-f]{12})", HandlerEnterprise.central_batch_get),
    ("DELETE", r"/central/jobs/(\d{1,9})", HandlerEnterprise.central_job_delete),
    ("POST", "/central/groups", HandlerEnterprise.central_groups_post),
    ("POST", "/central/groups/delete", HandlerEnterprise.central_group_delete),
    ("GET", "/central/software", HandlerEnterprise.central_software),
    ("GET", "/central/inventory.csv", HandlerEnterprise.central_inventory_csv),
    ("POST", "/central/catalog", HandlerEnterprise.central_catalog_post),
    ("DELETE", r"/central/catalog/(c[0-9a-f]{10})", HandlerEnterprise.central_catalog_delete),
    ("POST", "/central/rings", HandlerEnterprise.central_rings_post),
    ("DELETE", r"/central/rings/(r[0-9a-f]{10})", HandlerEnterprise.central_ring_delete),
    ("POST", "/central/rings/assign", HandlerEnterprise.central_rings_assign),
    ("GET", "/central/client", HandlerEnterprise.client_get),
    ("POST", "/central/client/enroll", HandlerEnterprise.client_enroll),
    ("PUT", "/central/client", HandlerEnterprise.client_put),
    ("DELETE", "/central/client", HandlerEnterprise.client_leave),
    ("POST", "/central/client/contact", HandlerEnterprise.client_contact),
    ("POST", "/software/winget", HandlerEnterprise.winget_post),
    ("GET", "/updates/compliance", HandlerEnterprise.updates_compliance),
    ("POST", "/updates/ring/apply", HandlerEnterprise.updates_ring_apply),
    ("GET", "/baselines", HandlerEnterprise.baselines_get),
    ("POST", "/baselines", HandlerEnterprise.baseline_post),
    ("PUT", r"/baselines/([a-z0-9]{2,20})", HandlerEnterprise.baseline_put),
    ("DELETE", r"/baselines/([a-z0-9]{2,20})", HandlerEnterprise.baseline_delete),
    ("POST", r"/baselines/([a-z0-9]{2,20})/run", HandlerEnterprise.baseline_run),
    ("POST", r"/baselines/([a-z0-9]{2,20})/fix", HandlerEnterprise.baseline_fix),
    ("GET", "/reports/executive.pdf", HandlerEnterprise.executive_pdf),
]

RULES = {
    "sso_state": (), "sso_get": "integrations.manage", "sso_put": "integrations.manage",
    "approvals_get": (), "approval_decide": "approvals.decide", "tokens_get": "api.tokens", "token_create": "api.tokens", "token_delete": "api.tokens",
    "audit_verify": "audit.view", "siem_get": "integrations.manage", "siem_put": "integrations.manage", "siem_test": "integrations.manage",
    "tickets_get": "integrations.manage", "tickets_put": "integrations.manage", "tickets_test": "integrations.manage",
    "escalation_get": "incidents.manage", "escalation_put": "integrations.manage", "incidents_get": (), "incident_update": "incidents.manage",
    "tls_get": "view.settings", "tls_put": "integrations.manage", "tls_regenerate": "integrations.manage", "encryption_put": "settings.security",
    "canary_get": "view.security", "canary_place": "settings.edit", "canary_remove": "settings.edit", "cfa_put": "settings.edit",
    "service_get": "view.settings", "service_install": "agent.control", "service_remove": "agent.control",
    "central_get": "view.fleet", "central_campaigns_get": "view.fleet", "central_campaigns_post": "central.manage", "central_backup": ("central.manage", "data.backup"), "central_inspect": ("central.manage", "data.backup"),
    "central_restore": ("central.manage", "data.backup"), "central_tenants_get": "view.fleet", "central_tenants_post": "central.manage", "central_tenant_delete": "central.manage",
    "central_tenants_move": "central.manage", "central_tenants_access": ("central.manage", "users.manage"),
    "central_server_put": "central.manage", "central_code": "central.manage", "central_agent_get": "view.fleet",
    "central_agent_delete": "central.manage", "central_agent_tags": "central.manage", "central_agent_asset": "central.manage",
    "central_jobs_post": "central.manage", "central_batch_get": "view.fleet", "central_job_delete": "central.manage",
    "central_groups_post": "central.manage", "central_group_delete": "central.manage", "central_software": "view.fleet",
    "central_inventory_csv": ("view.fleet", "export.data"), "central_catalog_post": "deploy.manage", "central_catalog_delete": "deploy.manage",
    "central_rings_post": "updates.policy", "central_ring_delete": "updates.policy", "central_rings_assign": "updates.policy",
    "client_get": "view.fleet", "client_enroll": "central.manage", "client_put": "central.manage", "client_leave": "central.manage",
    "client_contact": "view.fleet", "winget_post": "deploy.manage", "updates_compliance": "view.updates", "updates_ring_apply": "updates.policy",
    "baselines_get": "view.security", "baseline_post": "compliance.manage", "baseline_put": "compliance.manage", "baseline_delete": "compliance.manage",
    "baseline_run": "view.security", "baseline_fix": "compliance.manage", "executive_pdf": ("view.reports", "export.data"),
}
PUBLIC = {"sso_state", "oidc_start", "oidc_callback", "windows_login"}
