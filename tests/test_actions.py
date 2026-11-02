"""Tests for the action catalog and the job context: python -m unittest -v"""
import unittest

from wmm.agent import actions
from wmm.agent.core import JobContext, translate


class Catalog(unittest.TestCase):
    def test_every_action_has_valid_area_and_risk(self):
        for action in actions.CATALOG.values():
            self.assertIn(action.area, actions.AREAS)
            self.assertIn(action.risk, actions.RISKS)
            self.assertTrue(action.id.startswith(action.area + "."))

    def test_non_safe_actions_have_warning(self):
        for action in actions.CATALOG.values():
            if action.risk != "safe":
                self.assertTrue(action.warning, action.id)

    def test_safe_cleanup(self):
        self.assertEqual([a.id for a in actions.safe("cleanup")], ["cleanup.temp"])

    def test_catalog_has_at_least_47_actions(self):
        self.assertGreaterEqual(len(actions.CATALOG), 47)
        for nuova in ("performance.free_memory", "performance.restart_explorer", "storage.delivery_optimization", "network.renew_ip",
                      "security.full_scan", "security.firewall_on", "updates.store_apps", "integrity.wmi_verify", "integrity.reset_wu"):
            self.assertIn(nuova, actions.CATALOG)

    def test_catalog_has_72_actions(self):
        nuove = ("performance.power_ultimate", "performance.hibernation_off", "performance.hibernation_on", "performance.background_off",
                 "performance.background_on", "storage.windows_logs", "storage.compact_os", "network.reset_proxy", "network.reset_firewall",
                 "security.smartscreen_on", "security.disable_autorun", "security.uac_on", "security.disable_guest", "security.rdp_off",
                 "security.enable_restore", "security.pua_protection", "updates.winget_upgrade", "integrity.dism_scan",
                 "integrity.rebuild_icon_cache", "integrity.time_sync", "integrity.store_reset", "services.restart_spooler",
                 "services.restart_audio", "startup.restore_all")
        self.assertEqual(len(nuove), 24)
        for nuova in nuove:
            self.assertIn(nuova, actions.CATALOG)
        self.assertGreaterEqual(len(actions.CATALOG), 72)

    def test_catalog_has_94_actions(self):
        nuove = ("performance.transparency_off", "performance.transparency_on", "performance.mouse_precision_off", "services.search_manual",
                 "storage.delete_oldest_restore_point", "storage.clear_ie_cache", "network.reset_hosts", "network.purge_netbios",
                 "security.offline_scan", "security.block_smb_guest", "security.lsa_protection", "security.disable_llmnr",
                 "security.clear_recent_items", "security.reduce_telemetry", "security.disable_advertising_id",
                 "updates.driver_scan", "updates.office_update", "integrity.chkdsk_all", "integrity.repair_wmi", "integrity.sfc_verify",
                 "services.restart_wu", "services.restart_bluetooth")
        self.assertEqual(len(nuove), 22)
        for nuova in nuove:
            self.assertIn(nuova, actions.CATALOG)
        self.assertGreaterEqual(len(actions.CATALOG), 94)

    def test_catalog_has_20_disk_tools(self):
        nuove = ("storage.disk_health", "storage.smart_prediction", "storage.volume_report", "storage.partition_report",
                 "storage.dirty_check", "storage.disk_speed", "storage.shadow_report", "storage.top_folders", "storage.rescan_disks",
                 "storage.trim_ssd", "storage.defrag_hdd", "storage.disks_online", "storage.limit_restore_storage",
                 "storage.reserved_storage_off", "storage.reserved_storage_on", "storage.hiberfile_reduced", "storage.pagefile_auto",
                 "storage.last_access_off", "storage.disk_cleanup", "storage.delete_windows_old")
        self.assertEqual(len(set(nuove)), 20)
        for nuova in nuove:
            self.assertEqual(actions.CATALOG[nuova].area, "storage")
        self.assertGreaterEqual(len(actions.CATALOG), 114)
        self.assertEqual(actions.CATALOG["storage.delete_windows_old"].risk, "high")

    def test_catalog_has_50_toolbox_actions(self):
        nuove = ("cleanup.shader_cache", "cleanup.teams_cache", "cleanup.user_crash_dumps", "cleanup.office_cache", "cleanup.dev_caches",
                 "integrity.component_store_report", "integrity.boot_config_report", "integrity.reliability_report", "integrity.bsod_report",
                 "integrity.unsigned_drivers", "integrity.recovery_status", "services.stopped_auto_report", "services.restart_wlan",
                 "services.restart_search", "services.restart_time", "services.sysmain_manual", "performance.top_processes",
                 "performance.battery_report", "performance.usb_suspend_off", "performance.menu_delay", "performance.startup_delay_off",
                 "performance.game_mode_on", "storage.temp_report", "storage.downloads_report", "storage.recycle_report",
                 "storage.system_files_report", "storage.trim_status", "storage.trim_enable", "network.connectivity_report",
                 "network.wifi_report", "network.wlan_report", "network.ipconfig_report", "network.open_ports", "network.dns_quad9",
                 "startup.scheduled_tasks_report", "startup.boot_time_report", "startup.third_party_services", "startup.installed_apps_report",
                 "startup.edge_boost_off", "security.bitlocker_status", "security.tpm_status", "security.secure_boot_status",
                 "security.local_admins_report", "security.defender_status", "security.network_protection", "security.ransomware_audit",
                 "updates.history_report", "updates.pending_reboot", "updates.winget_list", "updates.problem_devices")
        self.assertEqual(len(set(nuove)), 50)
        for nuova in nuove:
            self.assertIn(nuova, actions.CATALOG)
        self.assertEqual(len(actions.CATALOG), 164)

    def test_reports_are_safe_and_skipped_by_safe_runs(self):
        self.assertTrue(actions.REPORTS <= set(actions.CATALOG))
        for action in actions.reports():
            self.assertEqual(action.risk, "safe", action.id)
            self.assertEqual(action.as_dict()["kind"], "report")
        self.assertFalse(set(a.id for a in actions.safe()) & actions.REPORTS)
        self.assertIn("cleanup.temp", [a.id for a in actions.safe()])

    def test_playbooks_reference_known_actions(self):
        for playbook in actions.PLAYBOOKS:
            for action_id in playbook["actions"]:
                self.assertIn(action_id, actions.CATALOG, playbook["id"])
            if "integrity.dism" in playbook["actions"] and "integrity.sfc" in playbook["actions"]:
                self.assertLess(playbook["actions"].index("integrity.dism"), playbook["actions"].index("integrity.sfc"))

    def test_as_dict_has_no_callable(self):
        data = actions.CATALOG["cleanup.temp"].as_dict()
        self.assertNotIn("run", data)
        self.assertEqual(data["risk"], "safe")


class Context(unittest.TestCase):
    def test_job_context_captures_output(self):
        log = []
        JobContext(log.append, preview=True).scrivi("x")
        self.assertEqual(log, ["x"])

    def test_preview_lines_are_english(self):
        log = []
        self.assertFalse(JobContext(log.append, preview=True).modifica("defrag C: /L"))
        self.assertEqual(log, ["  [preview] defrag C: /L"])

    def test_translate_known_messages(self):
        casi = {
            "1.2 GB, 3 file in uso lasciati": "1.2 GB, 3 files in use were skipped",
            "  [gia' ok]  DiagTrack": "  [already set]  DiagTrack",
            "  [fatto]    Fax -> disabled": "  [done]    Fax -> disabled",
            "4 modificati, 1 non modificabili": "4 changed, 1 could not be changed",
            "nessun servizio da ripristinare": "no services to restore",
            "punto del 02/11 10:30": "restore point of 02/11 10:30",
            "testo qualsiasi": "testo qualsiasi",
        }
        for testo, atteso in casi.items():
            self.assertEqual(translate(testo), atteso)


if __name__ == "__main__":
    unittest.main()
