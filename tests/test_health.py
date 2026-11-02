"""Tests for the startup health check and dependency verification."""
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wmm.agent import health


class Checks(unittest.TestCase):
    def test_python_version(self):
        vecchio = health.check_python((3, 8, 10))
        self.assertEqual((vecchio["status"], vecchio["critical"]), ("error", True))
        self.assertEqual(health.check_python((3, 12, 1))["status"], "ok")

    def test_missing_windows_tools_are_listed(self):
        voce = health.check_commands(lambda nome: None if nome in ("dism", "sfc") else "C:\\x\\" + nome)
        self.assertEqual(voce["status"], "warning")
        self.assertIn("dism", voce["detail"])
        self.assertIn("sfc", voce["detail"])
        self.assertEqual(health.check_commands(lambda nome: "C:\\x")["status"], "ok")

    def test_data_folder(self):
        with tempfile.TemporaryDirectory() as cartella:
            self.assertEqual(health.check_data_dir(Path(cartella) / "dati")["status"], "ok")
            file = Path(cartella) / "file.txt"
            file.write_text("x")
            voce = health.check_data_dir(file)
            self.assertEqual((voce["status"], voce["critical"]), ("error", True))

    def test_database_integrity(self):
        with tempfile.TemporaryDirectory() as cartella:
            sano = Path(cartella) / "ok.db"
            with sqlite3.connect(sano) as db:
                db.execute("CREATE TABLE t (x)")
            db.close()
            self.assertEqual(health.check_database(sano)["status"], "ok")
            rotto = Path(cartella) / "bad.db"
            rotto.write_bytes(b"this is not a database" * 100)
            self.assertEqual(health.check_database(rotto)["status"], "error")
            self.assertEqual(health.check_database(Path(cartella) / "missing.db")["status"], "ok")

    def test_port_in_use(self):
        occupata = socket.socket()
        occupata.bind(("127.0.0.1", 0))
        occupata.listen(1)
        try:
            voce = health.check_port(occupata.getsockname()[1])
            self.assertEqual(voce["status"], "error")
        finally:
            occupata.close()

    def test_web_assets(self):
        self.assertEqual(health.check_web_assets()["status"], "ok")

    def test_summary(self):
        voci = [{"status": "ok", "critical": False}, {"status": "warning", "critical": False}, {"status": "error", "critical": True}]
        self.assertEqual(health.summary(voci), {"ok": 1, "warning": 1, "error": 1, "blocking": True})


if __name__ == "__main__":
    unittest.main()
