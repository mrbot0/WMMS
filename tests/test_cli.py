"""Tests for the command line entry point."""
import unittest
from unittest import mock

import wmm as package  # noqa: F401
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("wmm_cli", Path(__file__).resolve().parent.parent / "wmm.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class Startup(unittest.TestCase):
    def test_declined_uac_opens_read_only_console(self):
        with mock.patch.object(cli.core, "is_admin", return_value=False), \
                mock.patch.object(cli, "restart_as_admin", return_value=False), \
                mock.patch.object(cli, "serve", return_value=0) as serve:
            self.assertEqual(cli.main(["--no-browser"]), 0)
        serve.assert_called_once_with(8765, False, False)

    def test_install_requires_administrator(self):
        with mock.patch.object(cli.core, "is_admin", return_value=False), \
                mock.patch.object(cli, "restart_as_admin", return_value=False), \
                mock.patch.object(cli, "install") as install:
            self.assertEqual(cli.main(["--install"]), 1)
        install.assert_not_called()

    def test_install_runs_when_elevated(self):
        with mock.patch.object(cli.core, "is_admin", return_value=True), \
                mock.patch.object(cli, "install", return_value=0) as install, \
                mock.patch.object(cli, "serve") as serve:
            self.assertEqual(cli.main(["--install", "--target", r"D:\WMM"]), 0)
        install.assert_called_once_with(r"D:\WMM")
        serve.assert_not_called()

    def test_auto_install_elevated_installs_then_starts_installed_copy(self):
        destinazione = cli.Path(r"C:\Program Files\WindowsMaintenanceManager")
        with mock.patch.object(cli.core, "is_admin", return_value=True), \
                mock.patch.object(cli, "installed_target", return_value=destinazione), \
                mock.patch.object(cli, "install", return_value=0) as install, \
                mock.patch.object(cli.subprocess, "call", return_value=0) as chiama, \
                mock.patch.object(cli, "serve") as serve:
            self.assertEqual(cli.main(["--auto-install", "--port", "9000"]), 0)
        install.assert_called_once_with(str(destinazione))
        comando = chiama.call_args[0][0]
        self.assertEqual(comando[1], str(destinazione / "wmm.py"))
        self.assertEqual(comando[2:], ["--port", "9000"])
        serve.assert_not_called()

    def test_auto_install_from_installed_copy_just_serves(self):
        with mock.patch.object(cli.core, "is_admin", return_value=True), \
                mock.patch.object(cli, "installed_target", return_value=cli.ROOT), \
                mock.patch.object(cli, "install") as install, \
                mock.patch.object(cli, "serve", return_value=0) as serve:
            self.assertEqual(cli.main(["--auto-install", "--no-browser"]), 0)
        install.assert_not_called()
        serve.assert_called_once_with(8765, False, False)

    def test_auto_install_failure_falls_back_to_this_copy(self):
        with mock.patch.object(cli.core, "is_admin", return_value=True), \
                mock.patch.object(cli, "installed_target", return_value=cli.Path(r"C:\Program Files\WindowsMaintenanceManager")), \
                mock.patch.object(cli, "install", return_value=1), \
                mock.patch.object(cli, "serve", return_value=0) as serve:
            self.assertEqual(cli.main(["--auto-install", "--no-browser"]), 0)
        serve.assert_called_once_with(8765, False, False)

    def test_wait_port_returns_when_free(self):
        import socket
        import time
        prova = socket.socket()
        prova.bind(("127.0.0.1", 0))
        porta = prova.getsockname()[1]
        prova.close()
        inizio = time.monotonic()
        cli.wait_for_port(porta, 5)
        self.assertLess(time.monotonic() - inizio, 1)

    def test_accepted_uac_hands_over_to_elevated_process(self):
        with mock.patch.object(cli.core, "is_admin", return_value=False), \
                mock.patch.object(cli, "restart_as_admin", return_value=True), \
                mock.patch.object(cli, "serve") as serve:
            self.assertEqual(cli.main([]), 0)
        serve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
