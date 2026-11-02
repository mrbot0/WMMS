"""Tests for the disk management tools and the forced restore point (no command really runs)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import tools


class FakeContext:
    anteprima = False

    def __init__(self, powershell_outputs=()):
        self.calls = []
        self.lines = []
        self.riavvio_necessario = False
        self._outputs = list(powershell_outputs)
        self.scripts = []

    def modifica(self, descrizione):
        self.calls.append(descrizione)
        return not self.anteprima

    def scrivi(self, testo=""):
        self.lines.append(testo)

    def comando(self, comando, validi=(0,)):
        if self.anteprima:
            return tools.Esito(tools.Stato.ANTEPRIMA)
        self.calls.append(comando)
        return tools.Esito(tools.Stato.OK)

    def powershell(self, script, timeout=180):
        self.scripts.append(script)
        return self._outputs.pop(0) if self._outputs else ""


class RestorePoint(unittest.TestCase):
    def test_lifts_the_24_hour_limit_and_puts_it_back(self):
        ctx = FakeContext(["7", "", "8"])
        with mock.patch.object(tools, "read_dword", return_value=1440), mock.patch.object(tools, "write_dword") as scrivi, \
                mock.patch.object(tools, "delete_value") as cancella:
            esito = tools.create_restore_point(ctx)
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertEqual([c[0][3] for c in scrivi.call_args_list], [0, 1440])
        cancella.assert_not_called()
        self.assertIn("Checkpoint-Computer", ctx.scripts[1])

    def test_removes_the_value_when_it_did_not_exist(self):
        ctx = FakeContext(["", "", "1"])
        with mock.patch.object(tools, "read_dword", return_value=None), mock.patch.object(tools, "write_dword"), \
                mock.patch.object(tools, "delete_value") as cancella:
            tools.create_restore_point(ctx)
        cancella.assert_called_once_with("HKEY_LOCAL_MACHINE", tools.SYSTEM_RESTORE_KEY, tools.RESTORE_FREQUENCY)

    def test_error_when_no_new_point_appears(self):
        ctx = FakeContext(["7", "", "7"])
        with mock.patch.object(tools, "read_dword", return_value=None), mock.patch.object(tools, "write_dword"), \
                mock.patch.object(tools, "delete_value"):
            esito = tools.create_restore_point(ctx)
        self.assertEqual(esito.stato, tools.Stato.ERRORE)

    def test_limit_is_restored_when_powershell_fails(self):
        ctx = FakeContext()
        ctx.powershell = mock.Mock(side_effect=["7", OSError("boom")])
        with mock.patch.object(tools, "read_dword", return_value=60), mock.patch.object(tools, "write_dword") as scrivi, \
                mock.patch.object(tools, "delete_value"):
            with self.assertRaises(OSError):
                tools.create_restore_point(ctx)
        self.assertEqual(scrivi.call_args_list[-1][0][3], 60)

    def test_preview_touches_nothing(self):
        ctx = FakeContext()
        ctx.anteprima = True
        with mock.patch.object(tools, "write_dword") as scrivi:
            esito = tools.create_restore_point(ctx)
        scrivi.assert_not_called()
        self.assertEqual(esito.stato, tools.Stato.ANTEPRIMA)


class DiskTools(unittest.TestCase):
    def test_top_folders_sorted_and_read_only(self):
        with tempfile.TemporaryDirectory() as radice:
            for nome, peso in (("small", 10), ("big", 5000), ("medium", 300)):
                cartella = Path(radice) / nome
                cartella.mkdir()
                (cartella / "f.bin").write_bytes(b"x" * peso)
            (Path(radice) / "file.txt").write_bytes(b"x" * 99999)  # files at the root are not folders
            ctx = FakeContext()
            ctx.anteprima = True  # a report runs in preview too
            esito = tools.top_folders(ctx, radice)
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertIn("big", esito.nota)
        righe = [r for r in ctx.lines if r.startswith("  ")]
        self.assertEqual([r.split()[-1] for r in righe], ["big", "medium", "small"])

    def test_commands_are_the_expected_ones(self):
        ctx = FakeContext()
        tools.set_reserved_storage(ctx, False)
        tools.reduce_hiberfile(ctx)
        tools.last_access_off(ctx)
        tools.limit_shadow_storage(ctx)
        self.assertIn(["DISM", "/Online", "/Set-ReservedStorageState", "/State:Disabled"], ctx.calls)
        self.assertIn(["powercfg", "/hibernate", "/type", "reduced"], ctx.calls)
        self.assertIn(["fsutil", "behavior", "set", "disablelastaccess", "1"], ctx.calls)
        self.assertIn(["vssadmin", "resize", "shadowstorage", "/for=C:", "/on=C:", "/maxsize=8%"], ctx.calls)

    def test_pagefile_needs_restart(self):
        ctx = FakeContext()
        tools.pagefile_automatic(ctx)
        self.assertTrue(ctx.riavvio_necessario)

    def test_warning_gets_a_clear_note(self):
        ctx = FakeContext()
        ctx.comando = lambda comando, validi=(0,): tools.Esito(tools.Stato.AVVISO, "exit code 1")
        self.assertIn("back up", tools.smart_prediction(ctx).nota)

    def test_windows_old_removed_with_rd_that_does_not_follow_junctions(self):
        with tempfile.TemporaryDirectory() as radice:
            (Path(radice) / "Windows.old").mkdir()
            ctx = FakeContext()
            with mock.patch.dict(os.environ, {"SystemDrive": radice.rstrip("\\")}):
                tools.delete_windows_old(ctx)
        comandi = [c for c in ctx.calls if isinstance(c, list)]
        self.assertEqual(comandi[-1][:6], ["cmd.exe", "/d", "/c", "rd", "/s", "/q"])
        self.assertTrue(all("/L" in c for c in comandi if c[0] == "icacls"))

    def test_windows_old_missing_is_ok(self):
        with tempfile.TemporaryDirectory() as radice:
            ctx = FakeContext()
            with mock.patch.dict(os.environ, {"SystemDrive": radice.rstrip("\\")}):
                esito = tools.delete_windows_old(ctx)
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertFalse([c for c in ctx.calls if isinstance(c, list)])

    def test_windows_old_preview_runs_nothing(self):
        with tempfile.TemporaryDirectory() as radice:
            (Path(radice) / "Windows.old").mkdir()
            ctx = FakeContext()
            ctx.anteprima = True
            with mock.patch.dict(os.environ, {"SystemDrive": radice.rstrip("\\")}):
                esito = tools.delete_windows_old(ctx)
            self.assertTrue((Path(radice) / "Windows.old").is_dir())
        self.assertEqual(esito.stato, tools.Stato.ANTEPRIMA)


if __name__ == "__main__":
    unittest.main()
