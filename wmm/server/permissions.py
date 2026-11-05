"""Which permission every API route needs when accounts are on (2.9). Keyed by the name of the Handler method, so a new
route cannot slip through: a write that is not listed here needs the permissions of an administrator (users.manage and
roles.manage), a read that is not listed only a signed-in user. Runs of tools are also checked one by one against the
area and risk of each tool (accounts.can_run)."""
from __future__ import annotations

from typing import Callable, Dict, List, Sequence, Union

# Reachable without a session: what the sign-in screen needs.
PUBLIC = {"info", "pair", "changelog", "auth_state", "auth_login", "auth_setup"}
# Reachable with a limited session (password to change, two-step to set up).
LIMITED_OK = {"info", "changelog", "auth_state", "auth_me", "auth_logout", "auth_password", "auth_2fa_begin", "auth_2fa_confirm", "token_check", "actions_list_noop"}
ADMIN = ("users.manage", "roles.manage")

Rule = Union[str, Sequence[str], Callable[[tuple], Union[str, Sequence[str]]]]


def _area(gruppi: tuple) -> str:
    return f"view.{gruppi[0]}" if gruppi else "view.dashboard"


def _script(gruppi: tuple) -> str:
    return "scripts.run" if gruppi and gruppi[-1] == "run" else "scripts.manage"


RULES: Dict[str, Rule] = {
    # pages: what a role sees
    "dashboard": "view.dashboard", "recommendations": "view.recommendations", "area": _area,
    "event_list": "view.events", "event_meta": "view.events",
    "hardware_inventory": "view.hardware", "hardware_sensors": "view.hardware", "trends_get": "view.hardware", "trends_post": "view.hardware",
    "hardware_monitor_tool": "view.hardware",
    "process_list": "view.processes", "service_list": "view.processes",
    "registry_key": "view.registry", "registry_search": "view.registry", "registry_export": ("view.registry", "export.data"), "registry_backups": "view.registry",
    "script_list": "view.scripts", "script_get": "view.scripts",
    "history": "view.history", "run_log": "view.history", "export": "export.data",
    "get_settings": (), "get_autostart": "view.settings",  # report branding: read by the dashboard and reports
    "protection_status": "view.settings", "notification_get": "view.settings",
    "digest_get": "view.settings", "update_check": "view.settings", "app_settings_get": "view.settings", "notify_log_get": "view.settings",
    "list_schedules": "view.schedules", "list_routines": "view.schedules",
    "crashes_get": "view.integrity", "early_warning_get": "view.integrity", "boot_get": "view.startup",
    "goodconfig_get": "view.security", "goodconfig_plan_post": "view.security", "suspicious_get": "view.security", "suspicious_post": "view.security",
    "drift_get": "view.security", "drift_post": "view.security", "restore_list": "view.security", "restore_open": "view.security",
    "phone_get": "view.fleet", "fleet_get": "view.fleet", "fleet_batch_get": "view.fleet", "fleet_run_get": "view.fleet",
    "custom_tools_get": "view.toolbox", "symptoms_get": "view.toolbox", "diagnose_post": "view.toolbox",
    "connection_get": "view.netscan", "connection_post": "view.netscan", "kev_get": "view.netscan", "kev_post": "view.netscan",
    "wifi_history_get": "view.netscan", "upnp_get": "view.netscan", "scan_interfaces_get": "view.netscan", "radio_get": "view.netscan",
    "network_devices": "view.netscan",
    "app_list": "view.apps", "app_updates": "view.apps", "app_rules": "view.apps", "uninstall_status": "view.apps",
    # things a role may do
    "elevate": "agent.control", "stop_all": "agent.control", "protect": "agent.control", "update_install": "agent.control", "put_autostart": "agent.control",
    "process_operation": "processes.control", "process_start": "processes.control", "service_control": "services.control",
    "script_create": "scripts.manage", "script_operation": _script, "timer_start": "scripts.run", "timer_cancel": "scripts.run",
    "registry_change": "registry.edit", "scan_all": "scan.run", "scan_area": "scan.run",
    "start_run": (), "start_safe": (),  # checked tool by tool
    "prune_history": "history.prune", "run_undo_post": "history.undo",
    "put_settings": "settings.edit", "toggle_startup": "startup.toggle",
    "create_schedule": "schedules.manage", "update_schedule": "schedules.manage", "delete_schedule": "schedules.manage",
    "resync_schedule": "schedules.manage", "test_schedule": "schedules.manage",
    "goodconfig_apply_post": "goodconfig.apply", "goodconfig_revert_post": "goodconfig.apply",
    "suspicious_settings_put": "settings.edit", "digest_put": "notifications.manage", "digest_send_post": "notifications.manage",
    "assistant_get": "assistant.use", "assistant_chat_post": "assistant.use", "assistant_chat_get": "assistant.use",
    "assistant_key_put": "settings.edit", "assistant_install_post": "settings.edit",
    "phone_put": "phone.manage", "phone_pair_post": "phone.manage", "phone_firewall_post": "phone.manage", "phone_remove_delete": "phone.manage",
    "fleet_batch_post": "fleet.run", "fleet_run_post": "fleet.run",
    "fleet_share_put": "fleet.manage", "fleet_key_post": "fleet.manage", "fleet_firewall_post": "fleet.manage", "fleet_add_post": "fleet.manage",
    "fleet_remove_delete": "fleet.manage",
    "custom_tools_post": "custom_tools.manage", "custom_tool_put": "custom_tools.manage", "custom_tool_delete": "custom_tools.manage",
    "bluetooth_ignore_post": "network.scan", "upnp_scan_post": "network.scan", "radio_scan_post": "network.scan", "network_scan": "network.scan",
    "notification_put": "notifications.manage", "notification_test": "notifications.manage",
    "update_app_rules": "apps.manage", "app_update": "apps.manage", "app_operation": "apps.manage", "clean_leftovers": "apps.manage",
    "store_remove": "apps.manage", "browser_clean": "apps.manage",
    # 2.9: accounts
    "auth_me": (), "auth_logout": (), "auth_password": (), "auth_profile": (), "auth_2fa_begin": (), "auth_2fa_confirm": (), "auth_2fa_disable": (),
    "auth_sessions": (), "auth_signout_others": (), "auth_disable": ADMIN, "token_check": (),
    "users_get": "users.view", "user_get": "users.view", "user_activity": ("users.view", "audit.view"), "users_export": ("users.view", "export.data"),
    "users_overview": "users.view", "sessions_get": "users.view", "roles_get": "users.view", "role_get": "users.view", "roles_compare": "users.view",
    "role_export": "users.view", "permissions_get": "users.view", "role_templates": "users.view",
    "user_create": "users.manage", "user_update": "users.manage", "user_delete": "users.manage", "user_copy": "users.manage",
    "user_reset_password": "users.manage", "user_unlock": "users.manage", "user_reset_2fa": "users.manage", "users_bulk": "users.manage",
    "users_import": "users.manage", "user_signout": "sessions.manage", "session_revoke": "sessions.manage",
    "role_create": "roles.manage", "role_update": "roles.manage", "role_delete": "roles.manage", "role_copy": "roles.manage", "role_reset": "roles.manage",
    "role_import": "roles.manage",
    "policy_get": "users.view", "policy_put": "settings.security",
    "audit_get": "audit.view", "audit_export": ("audit.view", "export.data"), "audit_prune": "settings.security",
    # 2.9: settings
    "app_settings_put": "settings.edit", "app_settings_reset": "settings.edit", "config_export": "data.backup", "config_import": "data.backup",
    "db_maintenance": "settings.edit", "db_info": "view.settings", "agent_log": "view.settings",
    "notify_test_channel": "notifications.manage", "telegram_detect": "notifications.manage", "telegram_bot": "notifications.manage",
    "webhook_test": "notifications.manage", "notify_log_clear": "notifications.manage", "smtp_presets": "view.settings",
    "retention_run": "settings.edit",
}


def required(nome: str, metodo: str, gruppi: tuple) -> List[str]:
    """The permissions a request needs: [] for any signed-in user."""
    if nome in RULES:
        regola = RULES[nome]
        if callable(regola):
            regola = regola(gruppi)
        return [regola] if isinstance(regola, str) else list(regola)
    return [] if metodo in ("GET", "HEAD") else list(ADMIN)


# 2.10: the routes of wmm/server/enterprise_api.py
from .enterprise_api import PUBLIC as _ENTERPRISE_PUBLIC, RULES as _ENTERPRISE_RULES  # noqa: E402

RULES.update(_ENTERPRISE_RULES)
PUBLIC |= _ENTERPRISE_PUBLIC
