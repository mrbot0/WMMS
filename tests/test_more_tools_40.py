"""Tests for the forty tools of iteration 9. Nothing is written to the system."""
import unittest
from collections import Counter
from unittest import mock

from wmm.agent import actions, tools
from tests.test_disk_tools import FakeContext

NEW = ("cleanup.font_cache", "cleanup.installer_report", "cleanup.java_cache", "cleanup.chat_music_caches", "cleanup.game_launcher_caches",
       "cleanup.editor_caches", "startup.run_keys_report", "startup.startup_folders_report", "startup.winlogon_report",
       "startup.wmi_persistence_report", "startup.ifeo_report", "startup.onedrive_autostart_off", "updates.wu_services_report",
       "updates.pause_status_report", "updates.resume_updates", "updates.driver_updates_off", "updates.driver_updates_on",
       "updates.windows_version_report", "services.clear_print_queue", "services.restart_network_location", "services.restart_cryptsvc",
       "services.disabled_report", "services.delayed_start_report", "network.arp_report", "network.routes_report", "network.dns_cache_report",
       "network.wifi_profiles_report", "network.dns_adguard", "network.winsock_reset", "integrity.restore_points_report",
       "integrity.crash_settings_report", "integrity.app_crashes_report", "integrity.small_memory_dumps", "integrity.memory_diagnostic",
       "security.firewall_rules_report", "security.shares_report", "security.password_policy_report", "security.autologon_report",
       "security.wdigest_off", "security.powershell_logging_on")


class Catalog(unittest.TestCase):
    def test_forty_new_tools(self):
        self.assertEqual(len(set(NEW)), 40)
        self.assertTrue(set(NEW) <= set(actions.CATALOG))
        self.assertGreaterEqual(len(actions.CATALOG), 234)  # later iterations add more tools
        self.assertEqual(sum(1 for a in NEW if a in actions.REPORTS), 22)
        self.assertEqual(Counter(a.split(".")[0] for a in NEW),
                         Counter(cleanup=6, startup=6, updates=6, services=5, network=6, integrity=5, security=6))

    def test_every_new_tool_runs_in_preview_without_changes(self):
        for action_id in NEW:
            ctx = FakeContext()
            ctx.anteprima = True
            with mock.patch.object(tools, "write_dword") as dword, mock.patch.object(tools, "delete_value") as cancella, \
                    mock.patch.object(tools, "read_string", return_value=r"C:\OneDrive.exe"):
                esito = actions.CATALOG[action_id].run(ctx)
            self.assertIn(esito.stato, (tools.Stato.ANTEPRIMA, tools.Stato.OK), action_id)
            dword.assert_not_called()
            cancella.assert_not_called()


class Fixes(unittest.TestCase):
    def test_onedrive_absent_is_ok_and_present_is_removed(self):
        with mock.patch.object(tools, "read_string", return_value=None), mock.patch.object(tools, "delete_value") as cancella:
            self.assertEqual(tools.onedrive_autostart_off(FakeContext()).stato, tools.Stato.OK)
        cancella.assert_not_called()
        with mock.patch.object(tools, "read_string", return_value=r"C:\OneDrive.exe"), mock.patch.object(tools, "delete_value") as cancella:
            tools.onedrive_autostart_off(FakeContext())
        cancella.assert_called_once_with(tools.HKCU, r"Software\Microsoft\Windows\CurrentVersion\Run", "OneDrive")

    def test_memory_diagnostic_schedules_one_boot_and_asks_for_restart(self):
        ctx = FakeContext()
        tools.memory_diagnostic(ctx)
        self.assertIn(["bcdedit", "/bootsequence", "{memdiag}"], ctx.calls)
        self.assertTrue(ctx.riavvio_necessario)

    def test_driver_updates_toggle(self):
        with mock.patch.object(tools, "write_dword") as dword:
            actions.CATALOG["updates.driver_updates_off"].run(FakeContext())
            actions.CATALOG["updates.driver_updates_on"].run(FakeContext())
        self.assertEqual([c[0][2:] for c in dword.call_args_list], [("ExcludeWUDriversInQualityUpdate", 1), ("ExcludeWUDriversInQualityUpdate", 0)])

    def test_autologon_report_never_prints_the_password(self):
        self.assertNotIn("DefaultPassword)", tools.SCRIPT_AUTOLOGON.replace("if ($w.DefaultPassword)", ""))


if __name__ == "__main__":
    unittest.main()
