"""Tests for the thirty toolbox fixes of iteration 14 (tools_extra3)."""
import re
import unittest
from unittest import mock

from wmm.agent import actions, tools_extra3

VSS_FAILED = r"\[(?:[6-9]|1[0-5])\]"


class ToolboxV3(unittest.TestCase):
    def test_thirty_new_fixes(self):
        self.assertEqual(len(actions.FIXES_14), 30)
        ids = [a.id for a in actions._ACTIONS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(actions.CATALOG), 351)

    def test_fixes_ask_first_and_say_what_they_do(self):
        # "Apply safe actions" runs every safe fix in bulk: these change the PC, so none of them may be safe.
        for action_id in actions.FIXES_14:
            action = actions.CATALOG[action_id]
            self.assertEqual(action.kind, "fix", action_id)
            self.assertIn(action.risk, ("moderate", "high"), action_id)
            self.assertNotIn(action, actions.safe())
            self.assertTrue(action.title and len(action.description) > 30, action_id)
            self.assertEqual(action.id.split(".")[0], action.area, action_id)
        for action_id in ("updates.remove_wu_policies", "integrity.reset_group_policy", "cleanup.upgrade_leftovers", "cleanup.old_driver_packages"):
            self.assertEqual(actions.CATALOG[action_id].risk, "high", action_id)

    def test_every_script_is_used_and_plain_printable_ascii(self):
        scripts = {name: getattr(tools_extra3, name) for name in dir(tools_extra3) if name.startswith("SCRIPT_")}
        self.assertEqual(len(scripts), 30)
        for name, text in scripts.items():
            self.assertTrue(text.strip(), name)
            # Base64 keeps any ASCII, but a stray control character (a backspace from an escape) silently breaks a regex.
            self.assertTrue(all(c in "\n\t" or 32 <= ord(c) < 127 for c in text), name)
        usati = set()
        for action_id in actions.FIXES_14:
            with mock.patch.object(tools_extra3, "ps", return_value="done") as ps:
                self.assertEqual(actions.CATALOG[action_id].run(object()), "done")
            usati.add(ps.call_args[0][1])
        self.assertEqual(usati, set(scripts.values()))  # each fix runs its own script

    def test_fixes_go_through_the_preview_aware_runner(self):
        class Ctx:
            def __init__(self):
                self.comandi = []

            def comando(self, argomenti):
                self.comandi.append(argomenti)
                return "simulated"
        ctx = Ctx()
        self.assertEqual(actions.CATALOG["security.show_extensions"].run(ctx), "simulated")
        self.assertIn("powershell", " ".join(ctx.comandi[0]).lower())

    def test_company_pcs_are_left_alone(self):
        for script in (tools_extra3.SCRIPT_REMOVE_WU_POLICIES, tools_extra3.SCRIPT_RESET_GROUP_POLICY):
            self.assertIn("PartOfDomain", script)
            self.assertIn("backup", script.lower())

    def test_language_independent_names(self):
        # Firewall groups and the Administrators group by resource name and SID: display names are translated.
        self.assertIn("@FirewallAPI.dll,-32752", tools_extra3.SCRIPT_DISCOVERY_ON)
        self.assertIn("@FirewallAPI.dll,-33002", tools_extra3.SCRIPT_REMOTE_ASSISTANCE_OFF)
        self.assertIn("*S-1-5-32-544", tools_extra3.SCRIPT_UPGRADE_LEFTOVERS)
        self.assertNotRegex(tools_extra3.SCRIPT_UPGRADE_LEFTOVERS, r"takeown|/D Y")
        # VSS writer states are numbers in every language: 6 to 15 are failures.
        self.assertIn("'" + VSS_FAILED + "'", tools_extra3.SCRIPT_RESTART_VSS)
        self.assertTrue(re.search(VSS_FAILED, "State: [7] Failed"))
        self.assertTrue(re.search(VSS_FAILED, "Stato: [12] Non riuscito"))
        self.assertFalse(re.search(VSS_FAILED, "Stato: [1] Stabile"))

    def test_driver_cleanup_never_forces(self):
        self.assertIn("pnputil /delete-driver", tools_extra3.SCRIPT_OLD_DRIVER_PACKAGES)
        comandi = [r for r in tools_extra3.SCRIPT_OLD_DRIVER_PACKAGES.splitlines() if "pnputil" in r and not r.lstrip().startswith("#")]
        self.assertTrue(comandi)
        self.assertFalse(any("/force" in r or "/uninstall" in r for r in comandi))

    def test_connectivity_fix_restarts_the_service_in_use(self):
        # Windows 11 24H2 stopped NlaSvc: the test lives in netprofm there.
        self.assertIn("netprofm", tools_extra3.SCRIPT_NCSI_RESET)


if __name__ == "__main__":
    unittest.main()
