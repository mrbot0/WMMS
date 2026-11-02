"""Tests for the performance pack (iteration 8). Nothing is written to the registry or the power plan."""
import unittest
from unittest import mock

from wmm.agent import actions, tools
from tests.test_disk_tools import FakeContext

NEW = ("performance.cpu_report", "performance.memory_report", "performance.gpu_report", "performance.power_plans_report",
       "performance.thermal_report", "performance.disk_latency_report", "performance.handle_leaks_report", "performance.winsat_report",
       "performance.pagefile_report", "performance.nic_power_report", "performance.core_parking_off", "performance.cpu_min_100",
       "performance.cpu_min_default", "performance.cpu_boost_aggressive", "performance.pcie_aspm_off", "performance.disk_timeout_off",
       "performance.sleep_never_ac", "performance.hags_on", "performance.network_throttling_off", "performance.games_priority",
       "performance.foreground_boost", "performance.animations_off", "performance.tips_off", "performance.widgets_off",
       "performance.copilot_off", "performance.search_highlights_off", "performance.hung_app_timeout", "performance.prefetch_default",
       "performance.ntfs_memory", "performance.nic_power_off")


class Catalog(unittest.TestCase):
    def test_thirty_performance_tools(self):
        self.assertEqual(len(set(NEW)), 30)
        for action_id in NEW:
            self.assertEqual(actions.CATALOG[action_id].area, "performance", action_id)
        self.assertEqual(len(actions.CATALOG), 194)
        self.assertEqual(sum(1 for a in NEW if a in actions.REPORTS), 10)

    def test_every_new_tool_runs_in_preview_without_changes(self):
        for action_id in NEW:
            ctx = FakeContext()
            ctx.anteprima = True
            with mock.patch.object(tools, "write_dword") as dword, mock.patch.object(tools, "write_string") as stringa:
                esito = actions.CATALOG[action_id].run(ctx)
            self.assertIn(esito.stato, (tools.Stato.ANTEPRIMA, tools.Stato.OK), action_id)
            dword.assert_not_called()
            stringa.assert_not_called()


class Tweaks(unittest.TestCase):
    def test_registry_values_types(self):
        ctx = FakeContext()
        with mock.patch.object(tools, "write_dword") as dword, mock.patch.object(tools, "write_string") as stringa:
            esito = actions.CATALOG["performance.games_priority"].run(ctx)
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertEqual([c[0][2:] for c in dword.call_args_list], [("GPU Priority", 8), ("Priority", 6)])
        self.assertEqual([c[0][2:] for c in stringa.call_args_list], [("Scheduling Category", "High"), ("SFIO Priority", "High")])

    def test_network_throttling_is_a_full_dword(self):
        with mock.patch.object(tools, "write_dword") as dword:
            actions.CATALOG["performance.network_throttling_off"].run(FakeContext())
        self.assertEqual(dword.call_args_list[0][0][3], 0xFFFFFFFF)

    def test_restart_flag(self):
        for action_id in ("performance.hags_on", "performance.prefetch_default", "performance.ntfs_memory"):
            ctx = FakeContext()
            with mock.patch.object(tools, "write_dword"):
                actions.CATALOG[action_id].run(ctx)
            self.assertTrue(ctx.riavvio_necessario, action_id)

    def test_power_settings_ac_only_and_reapply(self):
        ctx = FakeContext()
        actions.CATALOG["performance.cpu_min_100"].run(ctx)
        comandi = [c for c in ctx.calls if isinstance(c, list)]
        self.assertEqual(comandi[0], ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PROCTHROTTLEMIN", "100"])
        self.assertEqual(comandi[-1], ["powercfg", "/setactive", "SCHEME_CURRENT"])
        self.assertFalse(any("/setdcvalueindex" in c for c in comandi))

    def test_default_restore_covers_battery_too(self):
        ctx = FakeContext()
        actions.CATALOG["performance.cpu_min_default"].run(ctx)
        self.assertTrue(any("/setdcvalueindex" in c for c in ctx.calls if isinstance(c, list)))


if __name__ == "__main__":
    unittest.main()
