"""Tests for the protected installation used by scheduled actions."""
import tempfile
import unittest
from pathlib import Path

from wmm import installer


def make_source(radice: Path) -> None:
    (radice / "wmm" / "agent" / "__pycache__").mkdir(parents=True)
    (radice / "wmm" / "web" / "js").mkdir(parents=True)
    (radice / "dati").mkdir()
    for nome in ("wmm.py", "ottimizza_pc.py", "start_wmm.bat", "test_ottimizza_pc.py"):
        (radice / nome).write_text(nome)
    (radice / "wmm" / "__init__.py").write_text("")
    (radice / "wmm" / "agent" / "core.py").write_text("core")
    (radice / "wmm" / "agent" / "__pycache__" / "core.cpython-312.pyc").write_bytes(b"x")
    (radice / "wmm" / "web" / "js" / "app.js").write_text("js")
    (radice / "dati" / "wmm.db").write_bytes(b"db")
    (radice / "dati" / "servizi-backup.json").write_text("{}")
    (radice / "dati" / "wmm.lock").write_bytes(b"")


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "src"
        self.target = Path(self.tmp.name) / "Program Files" / "WindowsMaintenanceManager"
        self.source.mkdir()
        make_source(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_program_and_data(self):
        risultato = installer.copy_program(self.source, self.target)
        for relativo in ("wmm.py", "ottimizza_pc.py", "start_wmm.bat", "wmm/__init__.py", "wmm/agent/core.py",
                         "wmm/web/js/app.js", "dati/wmm.db", "dati/servizi-backup.json"):
            self.assertTrue((self.target / relativo).is_file(), relativo)
        self.assertFalse((self.target / "wmm" / "agent" / "__pycache__").exists())
        self.assertFalse((self.target / "dati" / "wmm.lock").exists())
        self.assertFalse((self.target / "test_ottimizza_pc.py").exists())
        self.assertTrue(risultato["data_copied"])

    def test_update_keeps_existing_data(self):
        installer.copy_program(self.source, self.target)
        (self.target / "dati" / "wmm.db").write_bytes(b"installed history")
        (self.source / "wmm" / "agent" / "core.py").write_text("core v2")
        risultato = installer.copy_program(self.source, self.target)
        self.assertEqual((self.target / "dati" / "wmm.db").read_bytes(), b"installed history")
        self.assertEqual((self.target / "wmm" / "agent" / "core.py").read_text(), "core v2")
        self.assertFalse(risultato["data_copied"])

    def test_update_removes_stale_program_files(self):
        installer.copy_program(self.source, self.target)
        (self.target / "wmm" / "agent" / "old_module.py").write_text("old")
        installer.copy_program(self.source, self.target)
        self.assertFalse((self.target / "wmm" / "agent" / "old_module.py").exists())

    def test_refuses_target_inside_source_or_same_folder(self):
        with self.assertRaises(ValueError):
            installer.copy_program(self.source, self.source / "install")
        with self.assertRaises(ValueError):
            installer.copy_program(self.source, self.source)

    def test_installed_schedules_point_to_new_location(self):
        self.assertEqual(installer.default_target({"ProgramFiles": r"D:\Apps"}), Path(r"D:\Apps\WindowsMaintenanceManager"))
        self.assertEqual(installer.default_target({}), Path(r"C:\Program Files\WindowsMaintenanceManager"))


if __name__ == "__main__":
    unittest.main()
