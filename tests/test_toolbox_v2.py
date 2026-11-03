"""Tests for the toolbox tools of iteration 13 (tools_extra2)."""
import unittest
from unittest import mock

from wmm.agent import actions, tools_extra2

FIXES_13 = [
    "network.reset_tcpip", "network.restart_adapters", "network.prefer_ipv4", "network.ipv6_default",
    "performance.rebuild_perf_counters", "performance.reset_power_plans", "services.rebuild_search_index",
    "updates.winget_source_reset", "cleanup.component_resetbase", "integrity.verifier_off", "security.ps_policy_remotesigned",
]


class ToolboxV2(unittest.TestCase):
    def test_forty_new_tools(self):
        self.assertEqual(len(actions.REPORTS_13) + len(FIXES_13), 40)
        ids = [a.id for a in actions._ACTIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reports_are_safe_and_read_only(self):
        for action_id in actions.REPORTS_13:
            self.assertEqual(actions.CATALOG[action_id].kind, "report", action_id)
            self.assertEqual(actions.CATALOG[action_id].risk, "safe", action_id)

    def test_fixes_ask_first(self):
        # "Apply safe actions" runs every safe fix in bulk: these change settings, so none of them may be safe.
        for action_id in FIXES_13:
            action = actions.CATALOG[action_id]
            self.assertEqual(action.kind, "fix", action_id)
            self.assertNotEqual(action.risk, "safe", action_id)
            self.assertNotIn(action, actions.safe())
        self.assertEqual(actions.CATALOG["cleanup.component_resetbase"].risk, "high")

    def test_scripts_are_plain_printable_ascii(self):
        # Base64 keeps any ASCII, but a stray control character (a backspace from an escape) silently breaks a regex.
        for name in dir(tools_extra2):
            if name.startswith("SCRIPT_"):
                text = getattr(tools_extra2, name)
                self.assertTrue(text.strip(), name)
                self.assertTrue(all(c in "\n\t" or 32 <= ord(c) < 127 for c in text), name)

    def test_reports_end_with_exit_zero(self):
        # Only an explicit "exit 1" (something found) may turn a report into a warning.
        with mock.patch.object(actions, "_R", return_value="done") as report:
            self.assertEqual(actions.CATALOG["security.usb_history"].run(object()), "done")
        script = report.call_args[0][1]
        self.assertTrue(script.rstrip().endswith("exit 0"))
        self.assertIn(tools_extra2.SCRIPT_USB_HISTORY.strip(), script)

    def test_windows_support_table_covers_current_builds(self):
        for build in ("19045", "22631", "26100", "26200"):
            self.assertIn(build, tools_extra2.SCRIPT_WINDOWS_SUPPORT)


if __name__ == "__main__":
    unittest.main()
