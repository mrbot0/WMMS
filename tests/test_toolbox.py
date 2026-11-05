"""Tests for the toolbox actions (iteration 7). No command really runs."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import actions, tools
from tests.test_disk_tools import FakeContext


class Reports(unittest.TestCase):
    def test_report_warning_gets_the_note(self):
        ctx = FakeContext()
        ctx.comando = lambda comando, validi=(0,): tools.Esito(tools.Stato.AVVISO, "exit code 1")
        self.assertEqual(tools.report(ctx, "x", "check it").nota, "check it")

    def test_report_runs_encoded_powershell(self):
        ctx = FakeContext()
        tools.report(ctx, "Get-Tpm")
        self.assertEqual(ctx.calls[0][:2], ["powershell", "-NoProfile"])

    def test_measured_sums_folders(self):
        with tempfile.TemporaryDirectory() as radice:
            for nome, peso in (("a", 100), ("b", 50)):
                (Path(radice) / nome).mkdir()
                (Path(radice) / nome / "f").write_bytes(b"x" * peso)
            ctx = FakeContext()
            esito = tools.measured(ctx, "test", [os.path.join(radice, "*")])
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertEqual(len([r for r in ctx.lines if r.startswith("  ")]), 2)

    def test_downloads_report_lists_only_old_files(self):
        with tempfile.TemporaryDirectory() as radice:
            vecchio, nuovo = Path(radice) / "old.zip", Path(radice) / "new.zip"
            vecchio.write_bytes(b"x" * 2000)
            nuovo.write_bytes(b"x" * 10)
            passato = time.time() - 200 * 86400
            os.utime(vecchio, (passato, passato))
            ctx = FakeContext()
            esito = tools.downloads_report(ctx, 90, radice)
        self.assertEqual([r.split()[-1] for r in ctx.lines], ["old.zip"])
        self.assertIn("older than 90 days", esito.nota)

    def test_downloads_report_without_folder(self):
        self.assertEqual(tools.downloads_report(FakeContext(), 90, "Z:\\does-not-exist").stato, tools.Stato.OK)

    def test_system_files_report_handles_missing_files(self):
        with tempfile.TemporaryDirectory() as radice:
            (Path(radice) / "pagefile.sys").write_bytes(b"x" * 1024)
            ctx = FakeContext()
            with mock.patch.dict(os.environ, {"SystemDrive": radice.rstrip("\\")}):
                esito = tools.system_files_report(ctx)
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertEqual(sum("absent" in r for r in ctx.lines), 2)

    def test_pending_reboot(self):
        with mock.patch.object(tools, "key_exists", side_effect=lambda r, k: "RebootPending" in k), \
                mock.patch.object(tools, "pending_file_renames", return_value=False):
            esito = tools.pending_reboot(FakeContext())
        self.assertEqual(esito.stato, tools.Stato.AVVISO)
        self.assertIn("Windows servicing", esito.nota)
        with mock.patch.object(tools, "key_exists", return_value=False), mock.patch.object(tools, "pending_file_renames", return_value=False):
            self.assertEqual(tools.pending_reboot(FakeContext()).stato, tools.Stato.OK)


class Changes(unittest.TestCase):
    def test_clean_folders_deletes_files_and_keeps_folders(self):
        with tempfile.TemporaryDirectory() as radice:
            cache = Path(radice) / "cache"
            cache.mkdir()
            (cache / "a.bin").write_bytes(b"x" * 10)
            esito = tools.clean_folders(FakeContext(), "test", [str(cache)])
            self.assertTrue(cache.is_dir())
            self.assertFalse(any(cache.iterdir()))
        self.assertEqual(esito.stato, tools.Stato.OK)

    def test_clean_folders_preview_keeps_files(self):
        with tempfile.TemporaryDirectory() as radice:
            (Path(radice) / "a.bin").write_bytes(b"x")
            ctx = FakeContext()
            ctx.anteprima = True
            esito = tools.clean_folders(ctx, "test", [radice])
            self.assertTrue((Path(radice) / "a.bin").exists())
        self.assertEqual(esito.stato, tools.Stato.ANTEPRIMA)

    def test_registry_tweaks_write_the_expected_values(self):
        with mock.patch.object(tools, "write_dword") as dword, mock.patch.object(tools, "write_string") as stringa:
            for funzione in (tools.menu_delay, tools.startup_delay_off, tools.game_mode_on, tools.edge_boost_off):
                self.assertEqual(funzione(FakeContext()).stato, tools.Stato.OK)
        self.assertEqual(stringa.call_args[0][2:], ("MenuShowDelay", "100"))
        nomi = [c[0][2] for c in dword.call_args_list]
        self.assertEqual(nomi, ["StartupDelayInMSec", "AutoGameModeEnabled", "StartupBoostEnabled", "BackgroundModeEnabled"])

    def test_registry_tweaks_preview_writes_nothing(self):
        ctx = FakeContext()
        ctx.anteprima = True
        with mock.patch.object(tools, "write_dword") as dword:
            self.assertEqual(tools.game_mode_on(ctx).stato, tools.Stato.ANTEPRIMA)
        dword.assert_not_called()

    def test_usb_suspend_sets_ac_and_dc(self):
        ctx = FakeContext()
        tools.usb_suspend_off(ctx)
        self.assertEqual([c[1] for c in ctx.calls if isinstance(c, list)], ["/setacvalueindex", "/setdcvalueindex", "/setactive"])

    def test_battery_report_note(self):
        self.assertIn("wmm-battery-report.html", tools.battery_report(FakeContext()).nota)


class Catalog(unittest.TestCase):
    def test_command_reports_run_with_a_fake_context(self):
        """Reports built on commands are captured by the fake context in preview."""
        # The watch reports (2.6, 2.7) scan the network, Bluetooth and disks themselves: tests/test_v26.py and test_v27.py cover them.
        lenti = {"storage.top_folders", "storage.temp_report", "storage.downloads_report", "storage.system_files_report",
                 *actions.WATCH_26, *actions.WATCH_27}
        for action_id in sorted(actions.REPORTS - lenti):
            ctx = FakeContext()
            ctx.anteprima = True
            with mock.patch.object(tools, "key_exists", return_value=False), mock.patch.object(tools, "pending_file_renames", return_value=False):
                esito = actions.CATALOG[action_id].run(ctx)
            self.assertIn(esito.stato, (tools.Stato.ANTEPRIMA, tools.Stato.OK), action_id)


if __name__ == "__main__":
    unittest.main()
