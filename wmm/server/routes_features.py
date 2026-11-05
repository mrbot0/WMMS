"""The HTTP side of wmm/server/features.py (split out in 2.11): the HandlerFeatures routes and FEATURE_ROUTES, which
wmm/server/api.py mixes into its Handler and appends to its routes. The agent side stays in features.py."""
from __future__ import annotations







class HandlerFeatures:
    # 2.8
    def crashes_get(self, query):
        self._json(200, self.agent.crashes_view())

    def boot_get(self, query):
        self._json(200, self.agent.boot_view())

    def early_warning_get(self, query):
        self._json(200, self.agent.early_warning_view())

    def goodconfig_get(self, query):
        self._json(200, self.agent.goodconfig_view())

    def goodconfig_plan_post(self, query):
        self._json(200, self.agent.goodconfig_plan(self._body().get("day")))

    def goodconfig_apply_post(self, query):
        self._json(200, self.agent.goodconfig_apply(self._body()))

    def goodconfig_revert_post(self, query):
        self._json(200, self.agent.goodconfig_revert())

    def suspicious_get(self, query):
        self._json(200, self.agent.suspicious_view())

    def suspicious_post(self, query):
        self._json(200, self.agent.suspicious_check())

    def suspicious_settings_put(self, query):
        self._json(200, self.agent.suspicious_settings(self._body()))

    def digest_get(self, query):
        self._json(200, self.agent.digest_view())

    def digest_put(self, query):
        self._json(200, self.agent.digest_settings(self._body()))

    def digest_send_post(self, query):
        self._json(200, self.agent.digest_send())

    def assistant_get(self, query):
        self._json(200, self.agent.assistant_view())

    def assistant_key_put(self, query):
        self._json(200, self.agent.assistant_key(self._body()))

    def assistant_install_post(self, query):
        self._json(200, self.agent.assistant_install())

    def assistant_chat_post(self, query):
        self._json(202, self.agent.assistant_chat(self._body(), self.user))

    def assistant_chat_get(self, query, conv_id):
        self._json(200, self.agent.assistant_conversation(conv_id))

    def phone_get(self, query):
        self._json(200, self.agent.phone_view())

    def phone_put(self, query):
        self._json(200, self.agent.phone_configure(self._body()))

    def phone_pair_post(self, query):
        self._json(200, self.agent.phone_pair())

    def phone_firewall_post(self, query):
        self._json(200, self.agent.phone_firewall())

    def phone_remove_delete(self, query, device_id):
        self._json(200, self.agent.phone_remove(device_id))

    def fleet_batch_post(self, query):
        corpo = self._body()
        self._check_tools(corpo.get("actions"), corpo)
        self._json(202, self.agent.fleet_batch(corpo))

    def fleet_batch_get(self, query, batch_id):
        self._json(200, self.agent.fleet_batch_status(batch_id))

    def diagnose_post(self, query, symptom_id):
        self._json(200, self.agent.symptom_diagnose(symptom_id))

    def custom_tools_get(self, query):
        self._json(200, self.agent.custom_tools_view())

    def custom_tools_post(self, query):
        self._json(201, self.agent.custom_tool_save(self._body()))

    def custom_tool_put(self, query, tool_id):
        self._json(200, self.agent.custom_tool_save(self._body(), tool_id))

    def custom_tool_delete(self, query, tool_id):
        self._json(200, self.agent.custom_tool_delete(tool_id))

    def connection_get(self, query):
        self._json(200, self.agent.connection_view())

    def connection_post(self, query):
        self._json(200, self.agent.connection_sample())

    def drift_get(self, query):
        self._json(200, self.agent.drift_view())

    def drift_post(self, query):
        self._json(200, self.agent.drift_check())

    def kev_get(self, query):
        self._json(200, self.agent.kev_view(False))

    def kev_post(self, query):
        self._json(200, self.agent.kev_view(True))

    def trends_get(self, query):
        self._json(200, self.agent.trends_view())

    def trends_post(self, query):
        self._json(200, self.agent.trends_record())

    def fleet_run_post(self, query, pc_id):
        corpo = self._body()
        self._check_tools(corpo.get("actions"), corpo)
        self._json(202, self.agent.fleet_run(pc_id, corpo))

    def fleet_run_get(self, query, pc_id, job_id):
        self._json(200, self.agent.fleet_run_status(pc_id, job_id))

    def symptoms_get(self, query):
        self._json(200, self.agent.symptom_search(query.get("q", "")))

    def run_undo_post(self, query, run_id):
        self._json(200, self.agent.undo_run(int(run_id)))

    def wifi_history_get(self, query):
        self._json(200, self.agent.wifi_history())

    def bluetooth_ignore_post(self, query):
        self._json(200, self.agent.bluetooth_ignore(self._body()))

    def upnp_get(self, query):
        self._json(200, self.agent.upnp_last())

    def upnp_scan_post(self, query):
        self._json(200, self.agent.upnp_scan())

    def radio_get(self, query, tipo):
        self._json(200, self.agent.radio_last(tipo))

    def radio_scan_post(self, query, tipo):
        self._json(200, self.agent.radio_scan(tipo, self._body().get("interface")))

    def scan_interfaces_get(self, query):
        self._json(200, self.agent.scan_interfaces())

    def network_devices(self, query):
        self._json(200, self.agent.network_devices())

    def network_scan(self, query):
        self._json(200, self.agent.network_scan(self._body().get("interface")))

    def fleet_get(self, query):
        self._json(200, self.agent.fleet_view())

    def fleet_share_put(self, query):
        self._json(200, self.agent.fleet_share(self._body()))

    def fleet_key_post(self, query):
        self._json(200, self.agent.fleet_key())

    def fleet_firewall_post(self, query):
        self._json(200, self.agent.fleet_firewall())

    def fleet_add_post(self, query):
        self._json(201, self.agent.fleet_add(self._body()))

    def fleet_remove_delete(self, query, pc_id):
        self._json(200, self.agent.fleet_remove(pc_id))

    def update_check(self, query):
        self._json(200, self.agent.update_check())

    def update_install(self, query):
        self._json(200, self.agent.update_install())

    def notification_get(self, query):
        self._json(200, self.agent.notification_settings())

    def notification_put(self, query):
        self._json(200, self.agent.save_notification_settings(self._body()))

    def notification_test(self, query):
        self._json(200, self.agent.test_notification())

    def app_list(self, query):
        self._json(200, self.agent.apps(refresh=query.get("refresh") == "1"))

    def app_operation(self, query, app_id, operazione):
        if operazione == "uninstall":
            self._json(200, self.agent.app_uninstall(app_id, self._body().get("no_restore_point") is True))
            return
        metodo = {"remove-entry": self.agent.app_remove_entry, "open-folder": self.agent.app_open_folder, "size": self.agent.app_size}[operazione]
        self._json(200, metodo(app_id))

    def uninstall_status(self, query, app_id):
        self._json(200, self.agent.uninstall_status(app_id))

    def clean_leftovers(self, query, app_id):
        self._json(200, self.agent.clean_leftovers(app_id, self._body().get("ids")))

    def store_remove(self, query, app_id):
        self._json(200, self.agent.store_remove(app_id, self._body().get("no_restore_point") is True))

    def restore_list(self, query):
        self._json(200, self.agent.restore_points())

    def restore_open(self, query):
        self._json(200, self.agent.open_system_restore())

    def browser_clean(self, query, browser_id):
        self._json(200, self.agent.browser_clean(browser_id))

    def app_updates(self, query):
        self._json(200, self.agent.app_updates())

    def app_rules(self, query):
        self._json(200, self.agent.app_rules())

    def update_app_rules(self, query):
        self._json(200, self.agent.update_app_rules())

    def app_update(self, query):
        self._json(200, self.agent.app_update(self._body().get("id")))


# (method, path pattern under /api/v1, handler)
FEATURE_ROUTES = [
    ("GET", "/integrity/crashes", HandlerFeatures.crashes_get),
    ("GET", "/startup/boot", HandlerFeatures.boot_get),
    ("GET", "/integrity/early-warning", HandlerFeatures.early_warning_get),
    ("GET", "/security/good-config", HandlerFeatures.goodconfig_get),
    ("POST", "/security/good-config/plan", HandlerFeatures.goodconfig_plan_post),
    ("POST", "/security/good-config/apply", HandlerFeatures.goodconfig_apply_post),
    ("POST", "/security/good-config/revert", HandlerFeatures.goodconfig_revert_post),
    ("GET", "/security/suspicious", HandlerFeatures.suspicious_get),
    ("POST", "/security/suspicious", HandlerFeatures.suspicious_post),
    ("PUT", "/security/suspicious/settings", HandlerFeatures.suspicious_settings_put),
    ("GET", "/digest", HandlerFeatures.digest_get),
    ("PUT", "/digest", HandlerFeatures.digest_put),
    ("POST", "/digest/send", HandlerFeatures.digest_send_post),
    ("GET", "/assistant", HandlerFeatures.assistant_get),
    ("PUT", "/assistant/key", HandlerFeatures.assistant_key_put),
    ("POST", "/assistant/install", HandlerFeatures.assistant_install_post),
    ("POST", "/assistant/chat", HandlerFeatures.assistant_chat_post),
    ("GET", r"/assistant/chat/([0-9a-f]{16})", HandlerFeatures.assistant_chat_get),
    ("GET", "/phone", HandlerFeatures.phone_get),
    ("PUT", "/phone", HandlerFeatures.phone_put),
    ("POST", "/phone/pair", HandlerFeatures.phone_pair_post),
    ("POST", "/phone/firewall", HandlerFeatures.phone_firewall_post),
    ("DELETE", r"/phone/devices/([0-9a-f]{16,32})", HandlerFeatures.phone_remove_delete),
    ("POST", "/fleet/batch", HandlerFeatures.fleet_batch_post),
    ("GET", r"/fleet/batch/([0-9a-f]{16})", HandlerFeatures.fleet_batch_get),
    ("POST", r"/symptoms/([a-z_]{2,40})/diagnose", HandlerFeatures.diagnose_post),
    ("GET", "/custom-tools", HandlerFeatures.custom_tools_get),
    ("POST", "/custom-tools", HandlerFeatures.custom_tools_post),
    ("PUT", r"/custom-tools/([0-9a-f]{8})", HandlerFeatures.custom_tool_put),
    ("DELETE", r"/custom-tools/([0-9a-f]{8})", HandlerFeatures.custom_tool_delete),
    ("GET", "/network/connection", HandlerFeatures.connection_get),
    ("POST", "/network/connection", HandlerFeatures.connection_post),
    ("GET", "/security/drift", HandlerFeatures.drift_get),
    ("POST", "/security/drift", HandlerFeatures.drift_post),
    ("GET", "/network/kev", HandlerFeatures.kev_get),
    ("POST", "/network/kev", HandlerFeatures.kev_post),
    ("GET", "/hardware/trends", HandlerFeatures.trends_get),
    ("POST", "/hardware/trends", HandlerFeatures.trends_post),
    ("POST", r"/fleet/pcs/([0-9a-f]{12})/run", HandlerFeatures.fleet_run_post),
    ("GET", r"/fleet/pcs/([0-9a-f]{12})/runs/([0-9a-f]{32})", HandlerFeatures.fleet_run_get),
    ("GET", "/symptoms", HandlerFeatures.symptoms_get),
    ("POST", r"/history/runs/(\d{1,10})/undo", HandlerFeatures.run_undo_post),
    ("GET", "/network/wifi/history", HandlerFeatures.wifi_history_get),
    ("POST", "/network/bluetooth/ignore", HandlerFeatures.bluetooth_ignore_post),
    ("GET", "/network/upnp", HandlerFeatures.upnp_get),
    ("POST", "/network/upnp/scan", HandlerFeatures.upnp_scan_post),
    ("GET", "/network/interfaces", HandlerFeatures.scan_interfaces_get),
    ("GET", r"/network/(wifi|bluetooth)", HandlerFeatures.radio_get),
    ("POST", r"/network/(wifi|bluetooth)/scan", HandlerFeatures.radio_scan_post),
    ("GET", "/network/devices", HandlerFeatures.network_devices),
    ("POST", "/network/scan", HandlerFeatures.network_scan),
    ("GET", "/fleet", HandlerFeatures.fleet_get),
    ("PUT", "/fleet/share", HandlerFeatures.fleet_share_put),
    ("POST", "/fleet/share/key", HandlerFeatures.fleet_key_post),
    ("POST", "/fleet/share/firewall", HandlerFeatures.fleet_firewall_post),
    ("POST", "/fleet/pcs", HandlerFeatures.fleet_add_post),
    ("DELETE", r"/fleet/pcs/([0-9a-f]{12})", HandlerFeatures.fleet_remove_delete),
    ("GET", "/update/check", HandlerFeatures.update_check),
    ("POST", "/update/install", HandlerFeatures.update_install),
    ("GET", "/notifications", HandlerFeatures.notification_get),
    ("PUT", "/notifications", HandlerFeatures.notification_put),
    ("POST", "/notifications/test", HandlerFeatures.notification_test),
    ("GET", "/restore-points", HandlerFeatures.restore_list),
    ("POST", "/restore-points/open", HandlerFeatures.restore_open),
    ("GET", "/apps", HandlerFeatures.app_list),
    ("GET", "/apps/updates", HandlerFeatures.app_updates),
    ("GET", "/apps/rules", HandlerFeatures.app_rules),
    ("POST", "/apps/rules/update", HandlerFeatures.update_app_rules),
    ("POST", "/apps/update", HandlerFeatures.app_update),
    ("POST", r"/apps/([0-9a-f]{16})/(uninstall|remove-entry|open-folder|size)", HandlerFeatures.app_operation),
    ("GET", r"/apps/([0-9a-f]{16})/uninstall-status", HandlerFeatures.uninstall_status),
    ("POST", r"/apps/([0-9a-f]{16})/leftovers", HandlerFeatures.clean_leftovers),
    ("POST", r"/apps/store/([0-9a-f]{16})/remove", HandlerFeatures.store_remove),
    ("POST", r"/apps/browsers/([a-z]{3,10})/clean", HandlerFeatures.browser_clean),
]
