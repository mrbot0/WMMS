"""Tests for user scripts and the shutdown timer. The timer never calls the real shutdown.exe."""
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import scripts


class Templates(unittest.TestCase):
    def test_shutdown_minutes_become_seconds(self):
        testo = scripts.render_template("shutdown_in", {"minutes": 45})
        self.assertIn("shutdown /s /t 2700", testo)
        self.assertTrue(testo.startswith("@echo off\r\n"))

    def test_bad_parameters_are_refused(self):
        for tid, params in (("shutdown_in", {"minutes": 0}), ("shutdown_in", {"minutes": "abc"}), ("shutdown_in", {"minutes": 99999}),
                            ("backup_folder", {"source": 'C:\\a" & del C:\\*', "destination": "D:\\b"}), ("backup_folder", {"source": "%PATH%", "destination": "D"}),
                            ("close_program", {"process": "notepad.exe & calc.exe"}), ("nope", {})):
            with self.assertRaises(scripts.ScriptError, msg=(tid, params)):
                scripts.render_template(tid, params)

    def test_every_template_renders_with_its_defaults(self):
        for t in scripts.TEMPLATES:
            params = {p["name"]: p["default"] for p in t["params"]}
            self.assertIn("\r\n", scripts.render_template(t["id"], params), t["id"])
        self.assertNotIn("body", scripts.templates_public()[0])

    def test_normalize(self):
        self.assertEqual(scripts.normalize("echo a\necho b"), "echo a\r\necho b\r\n")
        for bad in ("", "   ", "a\x00b", "x" * (scripts.MAX_BYTES + 1), b"bytes"):
            with self.assertRaises(scripts.ScriptError):
                scripts.normalize(bad)


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = scripts.ScriptLibrary(Path(self.tmp.name) / "scripts", unprotected=lambda paths: [])

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_update_delete(self):
        voce = self.lib.create("Hello", "@echo off\necho hi", "hello.cmd")
        self.assertTrue(voce["file"].endswith(".cmd"))
        self.assertEqual(self.lib.get(voce["id"])["content"], "@echo off\necho hi\n")
        self.assertEqual(self.lib.path(voce).read_bytes(), b"@echo off\r\necho hi\r\n")  # cmd.exe needs CRLF on disk
        self.lib.update(voce["id"], "Renamed", "echo bye")
        self.assertEqual(self.lib.list()[0]["name"], "Renamed")
        self.lib.delete(voce["id"])
        self.assertEqual(self.lib.list(), [])
        with self.assertRaises(scripts.ScriptError):
            self.lib.create("x", "echo", "evil.exe")
        with self.assertRaises(scripts.ScriptError):
            self.lib.get("../../etc")

    def test_template_name_shows_the_minutes(self):
        self.assertEqual(self.lib.from_template("shutdown_in", {"minutes": 90})["name"], "Shut down in 90 minutes")

    def test_accents_survive_in_the_console_code_page(self):
        voce = self.lib.create("Accents", "echo perché è così")
        self.assertIn("perché è così", self.lib.get(voce["id"])["content"])

    def test_run_captures_output_and_exit_code(self):
        voce = self.lib.create("Echo", "@echo off\necho wmm-ok\nexit /b 3")
        finito = threading.Event()
        risultati = []
        self.lib.run(voce["id"], lambda esito: (risultati.append(esito), finito.set()))
        self.assertTrue(finito.wait(30))
        self.assertIn("wmm-ok", risultati[0]["output"])
        self.assertEqual((risultati[0]["exit"], risultati[0]["status"]), (3, "error"))
        self.assertEqual(self.lib.get(voce["id"])["last_run"]["exit"], 3)

    def test_schedule_needs_a_protected_folder(self):
        lib = scripts.ScriptLibrary(Path(self.tmp.name) / "open", unprotected=lambda paths: paths)
        voce = lib.create("x", "echo")
        with self.assertRaises(scripts.ScriptError) as ctx:
            lib.schedule(voce["id"], "daily", "2030-01-01T03:00")
        self.assertIn("SYSTEM", str(ctx.exception))

    def test_schedule_registers_the_task(self):
        voce = self.lib.create("x", "echo")
        ok = subprocess.CompletedProcess([], 0, b"SUCCESS")
        with mock.patch.object(scripts, "_schtasks", return_value=ok) as schtasks:
            self.lib.schedule(voce["id"], "weekly", "2030-01-01T03:00", "MON,FRI")
        self.assertEqual(schtasks.call_args[0][:4], ("/Create", "/F", "/TN", scripts.TASK_PREFIX + voce["id"]))
        self.assertEqual(self.lib.get(voce["id"])["schedule"]["days"], "MON,FRI")
        with self.assertRaises(scripts.ScriptError):
            self.lib.schedule(voce["id"], "hourly", "2030-01-01T03:00")

    def test_task_xml_runs_cmd_as_system(self):
        xml = scripts.task_xml("abcd1234", r"C:\Program Files\WMM\dati\scripts\abcd1234.bat", {"kind": "daily", "at": "2030-01-01T03:00", "days": ""})
        self.assertIn("<UserId>S-1-5-18</UserId>", xml)
        self.assertIn("<Command>cmd.exe</Command>", xml)
        self.assertIn("<DaysInterval>1</DaysInterval>", xml)


class Timer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        self.now = [1000.0]
        self.timer = scripts.ShutdownTimer(Path(self.tmp.name) / "timer.json",
                                           runner=lambda cmd: (self.calls.append(cmd), subprocess.CompletedProcess(cmd, 0, b""))[1],
                                           clock=lambda: self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_change_cancel(self):
        stato = self.timer.start(30, "shutdown")
        self.assertEqual((stato["active"], stato["remaining"], stato["minutes"]), (True, 1800, 30))
        self.assertEqual(self.calls[0], ["shutdown", "/a"])
        self.assertEqual(self.calls[1][:4], ["shutdown", "/s", "/t", "1800"])
        self.now[0] += 600
        self.assertEqual(self.timer.status()["remaining"], 1200)
        self.timer.start(5, "restart")  # changing the time replaces the countdown
        self.assertEqual(self.calls[-1][:4], ["shutdown", "/r", "/t", "300"])
        self.assertFalse(self.timer.cancel()["active"])
        self.assertFalse(self.timer.status()["active"])

    def test_expired_and_invalid(self):
        self.timer.start(1)
        self.now[0] += 61
        self.assertFalse(self.timer.status()["active"])
        for minuti, azione in ((0, "shutdown"), (20000, "shutdown"), (10, "explode")):
            with self.assertRaises(scripts.ScriptError):
                self.timer.start(minuti, azione)


if __name__ == "__main__":
    unittest.main()
