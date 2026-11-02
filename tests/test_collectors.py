"""Tests for the data collectors (no system changes, PowerShell mocked)."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import collectors

RAW_SYSTEM = {
    "admin": True,
    "sistema": {"nome": "Windows 11 Pro", "build": "26300", "cpu": "Ryzen 7", "schedaMadre": "B550", "bios": "2604",
                "dataBios": "2022-02-25", "etaBiosGiorni": 1711, "oreAccensione": 2.2, "vociAvvio": 25},
    "memoria": {"liberaGB": 18.2, "totaleGB": 31.9},
    "processi": [{"nome": "explorer", "MB": 200}],
    "dischi": [{"nome": "SSD 1", "tipo": "SSD", "salute": "Healthy", "temperatura": 40, "usura": 3, "oreAccensione": 100, "erroriLettura": 0}],
    "volumi": {"lettera": "C", "liberoGB": 45.2, "totaleGB": 464.8, "salute": "Healthy"},
    "gpu": {"nome": "RTX", "driver": "1", "stato": ""},
    "stabilita": {"spegnimenti": 6, "whea": 0, "disco": 0, "dump": 0, "dumpGB": 0},
    "sicurezza": {"defender": True, "firmeGiorni": 0, "firewallSpenti": False, "bitlocker": ""},
    "riavvioInSospeso": False,
    "aggiornamenti": "KB1 2026-11-01",
}


class FakeContext:
    def __init__(self, result=None):
        self.result = result

    def powershell_json(self, script, timeout=180):
        return self.result


class Folders(unittest.TestCase):
    def test_measure_folders_counts_only_old_files(self):
        with tempfile.TemporaryDirectory() as cartella:
            vecchio = Path(cartella) / "old.tmp"
            nuovo = Path(cartella) / "new.tmp"
            vecchio.write_bytes(b"x" * 100)
            nuovo.write_bytes(b"x" * 50)
            dieci_giorni = time.time() - 10 * 86400
            os.utime(vecchio, (dieci_giorni, dieci_giorni))
            risultato = collectors.measure_folders({"t": [cartella]}, time.time() - 3 * 86400)
        self.assertEqual(risultato, [{"id": "t", "bytes": 100, "files": 1, "partial": False}])

    def test_scan_matches_cleanup_rules(self):
        with tempfile.TemporaryDirectory() as cartella:
            radice = Path(cartella)
            (radice / "sub").mkdir()
            (radice / "claude").mkdir()
            vecchio = time.time() - 10 * 86400
            for percorso in (radice / "a.tmp", radice / "sub" / "b.tmp", radice / "claude" / "c.tmp"):
                percorso.write_bytes(b"x" * 10)
                os.utime(percorso, (vecchio, vecchio))
            limite = time.time() - 3 * 86400
            attesi = sorted(p for p, _ in collectors.op.file_da_pulire(cartella, limite))
            self.assertEqual(collectors.old_files_size(cartella, limite), (20, 2, True))
            self.assertEqual(len(attesi), 2)

    def test_expired_deadline_marks_partial(self):
        with tempfile.TemporaryDirectory() as cartella:
            Path(cartella, "a.tmp").write_bytes(b"x")
            risultato = collectors.measure_folders({"t": [cartella]}, time.time() + 60, deadline=time.monotonic() - 1)
        self.assertTrue(risultato[0]["partial"])

    def test_budget_is_per_category(self):
        # A huge first folder must not leave the next categories without time.
        with tempfile.TemporaryDirectory() as uno, tempfile.TemporaryDirectory() as due:
            scadenze = []

            def lento(radice, limite, scadenza=None):
                scadenze.append(scadenza)
                return (0, 0, False) if radice == uno else (5, 1, True)

            with mock.patch.object(collectors, "old_files_size", side_effect=lento), \
                    mock.patch.object(collectors.time, "monotonic", side_effect=[100.0, 130.0]):
                risultato = collectors.measure_folders({"a": [uno], "b": [due]}, time.time(), budget=20)
        self.assertEqual(scadenze, [120.0, 150.0])
        self.assertEqual([r["partial"] for r in risultato], [True, False])

    def test_missing_folder_is_zero(self):
        risultato = collectors.measure_folders({"t": [r"C:\does\not\exist\wmm"]}, time.time())
        self.assertEqual(risultato, [{"id": "t", "bytes": 0, "files": 0, "partial": False}])


class System(unittest.TestCase):
    def test_translate_system_keys(self):
        dati = collectors.translate_system(RAW_SYSTEM)
        self.assertEqual(dati["os"]["cpu"], "Ryzen 7")
        self.assertEqual(dati["stability"]["unexpected_shutdowns"], 6)
        self.assertEqual(dati["volumes"][0]["letter"], "C")
        self.assertEqual(dati["updates"], ["KB1 2026-11-01"])
        self.assertEqual(dati["disks"][0]["media"], "SSD")

    def test_empty_powershell_yields_errors(self):
        self.assertTrue(collectors.collect_system(FakeContext(None))["errors"])
        self.assertTrue(collectors.collect_services(FakeContext(None))["errors"])

    def test_timeout_yields_errors(self):
        ctx = FakeContext()
        ctx.powershell_json = mock.Mock(side_effect=collectors.subprocess.TimeoutExpired("powershell", 1))
        self.assertTrue(collectors.collect_services(ctx)["errors"])


class Services(unittest.TestCase):
    def test_summarize_services(self):
        servizi = [
            {"Name": "DiagTrack", "StartMode": "Auto", "State": "Running", "DelayedAutoStart": False},
            {"Name": "Spooler", "StartMode": "Manual", "State": "Stopped", "DelayedAutoStart": False},
            {"Name": "WinDefend", "StartMode": "Auto", "State": "Running", "DelayedAutoStart": True},
            {"Name": "Other", "StartMode": "Disabled", "State": "Stopped", "DelayedAutoStart": False},
        ]
        dati = collectors.summarize_services(servizi, ["OneDrive"])
        self.assertEqual(dati["totals"], {"total": 4, "auto": 2, "manual": 1, "disabled": 1, "running": 2, "stopped": 2})
        gestiti = {s["name"]: s for s in dati["managed"]}
        self.assertEqual(gestiti["DiagTrack"], {"name": "DiagTrack", "group": "safe", "start": "auto", "running": True})
        self.assertEqual(gestiti["Spooler"]["start"], "demand")
        self.assertEqual(dati["protected_present"], 1)
        self.assertEqual(dati["startup"], ["OneDrive"])
        tutti = {s["name"]: s for s in dati["all"]}
        self.assertEqual(len(tutti), 4)
        self.assertEqual(tutti["WinDefend"]["start"], "delayed-auto")
        self.assertTrue(tutti["WinDefend"]["protected"])
        self.assertEqual(tutti["Other"]["state"], "Stopped")


if __name__ == "__main__":
    unittest.main()
