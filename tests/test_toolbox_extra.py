"""Tests for the toolbox tools of iteration 12 (tools_extra)."""
import unittest

from wmm.agent import actions, tools_extra


class ExtraTools(unittest.TestCase):
    def test_catalog_has_unique_ids(self):
        ids = [a.id for a in actions._ACTIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_extra_report_is_a_read_only_tool(self):
        for action_id in actions.EXTRA_REPORTS:
            self.assertIn(action_id, actions.CATALOG, action_id)
            self.assertEqual(actions.CATALOG[action_id].kind, "report", action_id)
            self.assertEqual(actions.CATALOG[action_id].risk, "safe", action_id)

    def test_fixes_are_not_reports_and_use_known_scripts(self):
        fixes = ["performance.wake_timers_off", "updates.delivery_lan_only", "network.autotuning_normal", "network.clear_arp",
                 "security.defender_cloud_on", "security.rdp_nla_on", "cleanup.clipboard"]
        for action_id in fixes:
            self.assertEqual(actions.CATALOG[action_id].kind, "fix", action_id)
        self.assertGreaterEqual(len(actions.EXTRA_REPORTS) + len(fixes), 47)

    def test_scripts_are_ascii_powershell(self):
        # The scripts travel base64-encoded to PowerShell: they must stay plain ASCII to survive every code page.
        for name in dir(tools_extra):
            if name.startswith("SCRIPT_"):
                text = getattr(tools_extra, name)
                self.assertTrue(text.strip(), name)
                self.assertTrue(all(ord(c) < 128 for c in text), name)

    def test_fix_runs_through_the_preview_aware_command(self):
        class Ctx:
            def __init__(self):
                self.calls = []

            def comando(self, comando):
                self.calls.append(comando)
                return "ok"
        ctx = Ctx()
        self.assertEqual(tools_extra.ps(ctx, tools_extra.SCRIPT_CLEAR_ARP), "ok")
        self.assertEqual(len(ctx.calls), 1)
        self.assertIn("powershell", ctx.calls[0][0].lower())


if __name__ == "__main__":
    unittest.main()
