"""Routes of accounts, users, roles, the audit log and the app settings (2.9). Mixed into Handler like HandlerFeatures;
wmm/server/permissions.py says which permission each route needs, and Handler._authorize checks it before these run."""
from __future__ import annotations

import json
import re

from ..agent import accounts, actions, appsettings, notify
from .errors import ApiError

ID_USER = r"(u[0-9a-f]{12})"
ID_ROLE = r"([a-z][a-z0-9]{1,20})"


def _err(e: Exception) -> ApiError:
    return ApiError(getattr(e, "status", 400), str(e))


class AccountsHandler:
    # ---------- helpers ----------

    @property
    def _acc(self) -> accounts.Accounts:
        return self.agent.accounts

    def _by(self) -> str:
        return (self.user or {}).get("username", "local")

    def _call(self, funzione, *a, **k):
        try:
            return funzione(*a, **k)
        except (accounts.AccountError, appsettings.SettingsError, notify.NotifyError) as e:
            raise _err(e) from None

    def _csv(self, testo: str, nome: str) -> None:
        self._send(200, ("\ufeff" + testo).encode("utf-8"), "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="{nome}"'})

    def _me_required(self) -> dict:
        if self.user is None:
            raise ApiError(409, "Accounts are off: turn them on in Settings › Accounts.")
        return self.user

    # ---------- sign-in and my account ----------

    def auth_state(self, query):
        pol = self._acc.policy()
        self._json(200, {"enabled": pol["enabled"], "min_length": pol["min_length"], "classes": pol["classes"],
                         "org_name": appsettings.load(self.agent.data_dir)["org_name"], "hostname": self.agent.hostname})

    def auth_setup(self, query):
        corpo = self._body()
        utente = self._call(self._acc.setup, str(corpo.get("username", "")), corpo.get("password") or "x", str(corpo.get("display", "")))
        esito = self._call(self._acc.login, utente["username"], corpo.get("password") or "", "", self.client_address[0],
                           self.headers.get("User-Agent", ""))
        self._json(200, esito)

    def auth_login(self, query):
        corpo = self._body()
        self._json(200, self._call(self._acc.login, str(corpo.get("username", "")), str(corpo.get("password", "")), str(corpo.get("code", "")),
                                   self.client_address[0], self.headers.get("User-Agent", "")))

    def auth_logout(self, query):
        self._acc.logout(self.headers.get("X-WMM-Session", ""))
        if self.user:
            self._acc.audit(self.user["username"], "logout")
        self._json(200, {"ok": True})

    def auth_me(self, query):
        if self.user is None:
            self._json(200, {"accounts": False})
            return
        u = {k: v for k, v in self.user.items() if k != "session"}
        pol = self._acc.policy()
        self._json(200, dict(u, accounts=True, policy={"min_length": pol["min_length"], "classes": pol["classes"], "history": pol["history"],
                                                     "idle_minutes": pol["idle_minutes"]}))

    def auth_password(self, query):
        corpo = self._body()
        self._json(200, self._call(self._acc.change_password, self._me_required(), str(corpo.get("old", "")), str(corpo.get("new", ""))))

    def auth_profile(self, query):
        self._json(200, self._call(self._acc.update_profile, self._me_required(), self._body()))

    def auth_2fa_begin(self, query):
        self._json(200, self._call(self._acc.totp_begin, self._me_required(), str(self._body().get("password", ""))))

    def auth_2fa_confirm(self, query):
        self._json(200, self._call(self._acc.totp_confirm, self._me_required(), str(self._body().get("code", ""))))

    def auth_2fa_disable(self, query):
        self._json(200, self._call(self._acc.totp_disable, self._me_required(), str(self._body().get("password", ""))))

    def auth_sessions(self, query):
        u = self._me_required()
        self._json(200, {"sessions": [dict(s, current=u["session"].startswith(s["id"])) for s in self._acc.sessions(u["id"])]})

    def auth_signout_others(self, query):
        u = self._me_required()
        self._json(200, {"signed_out": self._acc.revoke_user_sessions(u["id"], u["username"], keep=u["session"])})

    def auth_disable(self, query):
        self._call(self._acc.disable, self._me_required(), str(self._body().get("password", "")))
        self._json(200, {"enabled": False})

    # ---------- users ----------

    def users_overview(self, query):
        self._json(200, self._acc.overview())

    def users_get(self, query):
        self._json(200, {"users": self._acc.users(query.get("q", ""), query.get("role", ""), query.get("status", "")), "roles": self._acc.roles()})

    def user_get(self, query, user_id):
        u = self._call(self._acc.get_user, user_id)
        self._json(200, dict(u, sessions=self._acc.sessions(user_id), logins=self._acc.login_history(u["username"], 20)))

    def user_activity(self, query, user_id):
        u = self._call(self._acc.get_user, user_id)
        self._json(200, self._acc.audit_list(user=u["username"], limit=200))

    def user_create(self, query):
        corpo = self._body()
        if not corpo.get("lang"):
            corpo["lang"] = appsettings.load(self.agent.data_dir)["default_user_lang"]
        self._json(201, self._call(self._acc.create_user, corpo, self._by(), self.user))

    def user_update(self, query, user_id):
        self._json(200, self._call(self._acc.update_user, user_id, self._body(), self._by(), self.user))

    def user_delete(self, query, user_id):
        self._json(200, self._call(self._acc.delete_user, user_id, self._by(), (self.user or {}).get("id", "")))

    def user_copy(self, query, user_id):
        corpo = self._body()
        self._json(201, self._call(self._acc.copy_user, user_id, str(corpo.get("username", "")), str(corpo.get("display", "")), self._by(), self.user))

    def user_reset_password(self, query, user_id):
        self._json(200, self._call(self._acc.reset_password, user_id, self._by()))

    def user_unlock(self, query, user_id):
        self._json(200, self._call(self._acc.unlock, user_id, self._by()))

    def user_reset_2fa(self, query, user_id):
        self._json(200, self._call(self._acc.reset_2fa, user_id, self._by()))

    def user_signout(self, query, user_id):
        self._json(200, {"signed_out": self._call(self._acc.revoke_user_sessions, user_id, self._by())})

    def users_bulk(self, query):
        corpo = self._body()
        self._json(200, self._call(self._acc.bulk, corpo.get("ids"), str(corpo.get("action", "")), corpo.get("value"), self._by(),
                                   (self.user or {}).get("id", ""), self.user))

    def users_export(self, query):
        self._csv(self._acc.export_users(), "wmm-users.csv")

    def users_import(self, query):
        self._json(200, self._call(self._acc.import_users, self._body().get("csv", ""), self._by(), self.user))

    def sessions_get(self, query):
        self._json(200, {"sessions": self._acc.sessions()})

    def session_revoke(self, query, prefix):
        self._json(200, {"revoked": self._call(self._acc.revoke_session, prefix, self._by())})

    # ---------- roles ----------

    def permissions_get(self, query):
        self._json(200, {"permissions": accounts.catalog(), "areas": [{"id": a, "title": t} for a, t in accounts.AREAS],
                         "levels": [{"id": l, "title": t} for l, t in accounts.LEVELS], "colors": list(accounts.COLORS)})

    def role_templates(self, query):
        self._json(200, {"templates": self._acc.templates()})

    def roles_get(self, query):
        self._json(200, {"roles": self._acc.roles()})

    def role_get(self, query, role_id):
        r = self._call(self._acc.get_role, role_id)
        self._json(200, dict(r, members=[{"id": u["id"], "username": u["username"], "display": u["display"], "status": u["status"]}
                                         for u in self._acc.users(role=role_id)]))

    def role_create(self, query):
        self._json(201, self._call(self._acc.create_role, self._body(), self._by(), self.user))

    def role_update(self, query, role_id):
        self._json(200, self._call(self._acc.update_role, role_id, self._body(), self._by(), self.user))

    def role_delete(self, query, role_id):
        self._json(200, self._call(self._acc.delete_role, role_id, query.get("reassign") or None, self._by(), self.user))

    def role_copy(self, query, role_id):
        self._json(201, self._call(self._acc.copy_role, role_id, str(self._body().get("name", "")), self._by(), self.user))

    def role_reset(self, query, role_id):
        self._json(200, self._call(self._acc.reset_role, role_id, self._by(), self.user))

    def roles_compare(self, query):
        self._json(200, self._call(self._acc.compare_roles, query.get("a", ""), query.get("b", "")))

    def role_export(self, query, role_id):
        self._json(200, self._call(self._acc.export_role, role_id))

    def role_import(self, query):
        self._json(201, self._call(self._acc.import_role, self._body().get("role"), self._by(), self.user))

    # ---------- policy and audit ----------

    def policy_get(self, query):
        self._json(200, self._acc.policy())

    def policy_put(self, query):
        self._json(200, self._call(self._acc.set_policy, self._body(), self._by()))

    def _audit_filters(self, query) -> dict:
        return {k: query.get(k, "") for k in ("user", "action", "since", "until", "q")} | {"failed": query.get("failed") == "1"}

    def audit_get(self, query):
        try:
            limite, inizio = int(query.get("limit", 200)), int(query.get("offset", 0))
        except ValueError:
            raise ApiError(400, "Invalid limit.") from None
        self._json(200, self._acc.audit_list(limit=limite, offset=inizio, **self._audit_filters(query)))

    def audit_export(self, query):
        self._csv(self._acc.audit_csv(**self._audit_filters(query)), "wmm-audit.csv")

    def audit_prune(self, query):
        self._json(200, {"deleted": self._acc.audit_prune()})

    # ---------- app settings ----------

    def app_settings_get(self, query):
        from ..agent import notify as _n
        self._json(200, {"values": appsettings.load(self.agent.data_dir), "sections": appsettings.SECTIONS, "presets": appsettings.SMTP_PRESETS,
                         "channels": list(appsettings.CHANNELS), "events": _n.EVENTS, "webhook_kinds": list(appsettings.WEBHOOK_KINDS),
                         "roles": [{"id": r["id"], "name": r["name"]} for r in self._acc.roles()], "hostname": self.agent.hostname})

    def app_settings_put(self, query):
        self._json(200, {"values": self._call(appsettings.save, self.agent.data_dir, self._body(), self._acc)})

    def app_settings_reset(self, query):
        self._json(200, {"values": self._call(appsettings.reset, self.agent.data_dir, str(self._body().get("section", "")))})

    def smtp_presets(self, query):
        self._json(200, {"presets": appsettings.SMTP_PRESETS})

    def _bot_token(self) -> str:
        token = str(self._body().get("token") or "").strip()
        if not token:
            salvati = notify.for_data_dir(self.agent.data_dir)._read()
            token = notify.unprotect(salvati.get("telegram_token", "")) if salvati.get("telegram_token") else ""
        if not appsettings.allowed(self.agent.data_dir, "telegram"):
            raise ApiError(409, "Telegram is turned off (Settings › Connections).")
        return token

    def telegram_bot(self, query):
        self._json(200, self._call(appsettings.telegram_bot, self._bot_token()))

    def telegram_detect(self, query):
        self._json(200, {"chats": self._call(appsettings.telegram_chats, self._bot_token())})

    def notify_test_channel(self, query, canale):
        n = notify.for_data_dir(self.agent.data_dir)
        if canale not in n.all_channels():
            raise ApiError(409, f"The {canale} channel is not set up.")
        esiti = n.send("Test from Windows Maintenance Manager", f"This {canale} channel works.", solo=[canale], evento="test")
        self._json(200, {"results": esiti, "ok": esiti.get(canale) == "ok"})

    def webhook_test(self, query):
        corpo = self._body()
        s = appsettings.load(self.agent.data_dir)
        url, tipo = str(corpo.get("url") or s["webhook_url"]), str(corpo.get("kind") or s["webhook_kind"])
        if tipo not in appsettings.WEBHOOK_KINDS:
            raise ApiError(400, "Unknown webhook kind.")
        if not appsettings.allowed(self.agent.data_dir, "webhook"):
            raise ApiError(409, "Webhooks are turned off (Settings › Connections).")
        esito = appsettings.webhook_send(url, tipo, "Test from Windows Maintenance Manager", "The webhook works.")
        self._json(200, {"result": esito, "ok": esito == "ok"})

    def notify_log_get(self, query):
        self._json(200, {"entries": appsettings.alert_log(self.agent.data_dir)[:300]})

    def notify_log_clear(self, query):
        appsettings.clear_alert_log(self.agent.data_dir)
        self._json(200, {"ok": True})

    def db_info(self, query):
        self._json(200, appsettings.data_info(self.agent.data_dir))

    def db_maintenance(self, query):
        self._json(200, {"results": self._call(appsettings.db_maintenance, self.agent.data_dir, str(self._body().get("action", "")))})

    def retention_run(self, query):
        self._json(200, {"deleted": appsettings.retention_run(self.agent.data_dir, self.agent.store, self.agent.machine_id, self._acc)})

    def config_export(self, query):
        dati = appsettings.export_config(self.agent.data_dir, self.agent.store, self._acc)
        self._send(200, json.dumps(dati, indent=1, ensure_ascii=False).encode("utf-8"), "application/json",
                   {"Content-Disposition": 'attachment; filename="wmm-config.json"'})

    def config_import(self, query):
        self._json(200, self._call(appsettings.import_config, self.agent.data_dir, self._body().get("data"), self.agent.store, self._acc, self._by(), self.user))

    def agent_log(self, query):
        self._json(200, appsettings.diagnostics(self.agent.data_dir, getattr(self.agent, "_health", None), self.agent.info()))


ACCOUNT_ROUTES = [
    ("GET", "/auth/state", AccountsHandler.auth_state),
    ("POST", "/auth/setup", AccountsHandler.auth_setup),
    ("POST", "/auth/login", AccountsHandler.auth_login),
    ("POST", "/auth/logout", AccountsHandler.auth_logout),
    ("GET", "/auth/me", AccountsHandler.auth_me),
    ("POST", "/auth/password", AccountsHandler.auth_password),
    ("PUT", "/auth/profile", AccountsHandler.auth_profile),
    ("POST", "/auth/2fa/begin", AccountsHandler.auth_2fa_begin),
    ("POST", "/auth/2fa/confirm", AccountsHandler.auth_2fa_confirm),
    ("POST", "/auth/2fa/disable", AccountsHandler.auth_2fa_disable),
    ("GET", "/auth/sessions", AccountsHandler.auth_sessions),
    ("POST", "/auth/sessions/signout-others", AccountsHandler.auth_signout_others),
    ("POST", "/auth/disable", AccountsHandler.auth_disable),
    ("GET", "/auth/policy", AccountsHandler.policy_get),
    ("PUT", "/auth/policy", AccountsHandler.policy_put),
    ("GET", "/users/overview", AccountsHandler.users_overview),
    ("GET", "/users/export.csv", AccountsHandler.users_export),
    ("POST", "/users/import", AccountsHandler.users_import),
    ("POST", "/users/bulk", AccountsHandler.users_bulk),
    ("GET", "/users", AccountsHandler.users_get),
    ("POST", "/users", AccountsHandler.user_create),
    ("GET", f"/users/{ID_USER}", AccountsHandler.user_get),
    ("PUT", f"/users/{ID_USER}", AccountsHandler.user_update),
    ("DELETE", f"/users/{ID_USER}", AccountsHandler.user_delete),
    ("GET", f"/users/{ID_USER}/activity", AccountsHandler.user_activity),
    ("POST", f"/users/{ID_USER}/copy", AccountsHandler.user_copy),
    ("POST", f"/users/{ID_USER}/password", AccountsHandler.user_reset_password),
    ("POST", f"/users/{ID_USER}/unlock", AccountsHandler.user_unlock),
    ("POST", f"/users/{ID_USER}/2fa-reset", AccountsHandler.user_reset_2fa),
    ("POST", f"/users/{ID_USER}/signout", AccountsHandler.user_signout),
    ("GET", "/sessions", AccountsHandler.sessions_get),
    ("DELETE", r"/sessions/([0-9a-f]{16})", AccountsHandler.session_revoke),
    ("GET", "/permissions", AccountsHandler.permissions_get),
    ("GET", "/roles/templates", AccountsHandler.role_templates),
    ("GET", "/roles/compare", AccountsHandler.roles_compare),
    ("POST", "/roles/import", AccountsHandler.role_import),
    ("GET", "/roles", AccountsHandler.roles_get),
    ("POST", "/roles", AccountsHandler.role_create),
    ("GET", f"/roles/{ID_ROLE}", AccountsHandler.role_get),
    ("PUT", f"/roles/{ID_ROLE}", AccountsHandler.role_update),
    ("DELETE", f"/roles/{ID_ROLE}", AccountsHandler.role_delete),
    ("POST", f"/roles/{ID_ROLE}/copy", AccountsHandler.role_copy),
    ("POST", f"/roles/{ID_ROLE}/reset", AccountsHandler.role_reset),
    ("GET", f"/roles/{ID_ROLE}/export", AccountsHandler.role_export),
    ("GET", "/audit/export.csv", AccountsHandler.audit_export),
    ("GET", "/audit", AccountsHandler.audit_get),
    ("POST", "/audit/prune", AccountsHandler.audit_prune),
    ("GET", "/app-settings", AccountsHandler.app_settings_get),
    ("PUT", "/app-settings", AccountsHandler.app_settings_put),
    ("POST", "/app-settings/reset", AccountsHandler.app_settings_reset),
    ("GET", "/app-settings/smtp-presets", AccountsHandler.smtp_presets),
    ("POST", "/notifications/telegram/bot", AccountsHandler.telegram_bot),
    ("POST", "/notifications/telegram/chats", AccountsHandler.telegram_detect),
    ("POST", r"/notifications/test/(email|telegram|webhook)", AccountsHandler.notify_test_channel),
    ("POST", "/notifications/webhook/test", AccountsHandler.webhook_test),
    ("GET", "/notifications/log", AccountsHandler.notify_log_get),
    ("DELETE", "/notifications/log", AccountsHandler.notify_log_clear),
    ("GET", "/data/info", AccountsHandler.db_info),
    ("POST", "/data/maintenance", AccountsHandler.db_maintenance),
    ("POST", "/data/retention", AccountsHandler.retention_run),
    ("GET", "/config/export", AccountsHandler.config_export),
    ("POST", "/config/import", AccountsHandler.config_import),
    ("GET", "/diagnostics", AccountsHandler.agent_log),
]
