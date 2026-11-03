"""Tests for the hidden console mode (--hidden): log file, no console windows for child programs."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wmm as package  # noqa: F401

SPEC = importlib.util.spec_from_file_location("wmm_cli_hidden", Path(__file__).resolve().parent.parent / "wmm.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class Hidden(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.data = Path(self.tmp.name)
        self.saved = (sys.stdout, sys.stderr, subprocess.Popen.__init__)
        self.seen = {}
        seen = self.seen

        def fake_init(self_, *args, **kwargs):
            seen.update(kwargs)
        subprocess.Popen.__init__ = fake_init

    def tearDown(self):
        log = sys.stdout
        sys.stdout, sys.stderr, subprocess.Popen.__init__ = self.saved
        if log is not self.saved[0] and hasattr(log, "close"):
            log.close()
        self.tmp.cleanup()

    def hide(self, console_window):
        with mock.patch.object(cli, "DATA_DIR", self.data), mock.patch.object(cli, "CONSOLE_LOG", self.data / "wmm-console.log"), \
                mock.patch.object(cli.ctypes, "windll", create=True) as windll:
            windll.kernel32.GetConsoleWindow.return_value = console_window
            cli.go_hidden()
            return windll

    def test_output_goes_to_the_log_and_children_get_no_window(self):
        windll = self.hide(1234)
        windll.user32.ShowWindow.assert_called_once_with(1234, 0)
        print("hello from the hidden console")
        subprocess.Popen(["cmd", "/c", "echo"])
        self.assertEqual(self.seen.get("creationflags"), cli.CREATE_NO_WINDOW)
        sys.stdout.flush()
        self.assertIn("hello from the hidden console", (self.data / "wmm-console.log").read_text(encoding="utf-8"))

    def test_explicit_creation_flags_are_kept(self):
        self.hide(0)
        subprocess.Popen(["notepad"], creationflags=0x10)  # CREATE_NEW_CONSOLE: "Start new process" stays visible
        self.assertEqual(self.seen.get("creationflags"), 0x10)

    def test_windowless_python(self):
        with mock.patch.object(cli.Path, "is_file", return_value=True):
            self.assertTrue(cli.windowless_python(r"C:\Python313\python.exe").endswith("pythonw.exe"))
        with mock.patch.object(cli.Path, "is_file", return_value=False):
            self.assertTrue(cli.windowless_python(r"C:\Python313\python.exe").endswith("python.exe"))


if __name__ == "__main__":
    unittest.main()
