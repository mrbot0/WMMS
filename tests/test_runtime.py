"""Tests for the protected Python used by schedules (nothing is installed: installers are fakes)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wmm import runtime


def tmp():
    """%TEMP% is under AppData, which counts as per-user: test folders live next to the tests."""
    return tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(__file__)))


def fake_python(folder: Path, name: str) -> str:
    cartella = folder / name
    cartella.mkdir(parents=True)
    eseguibile = cartella / "python.exe"
    eseguibile.write_bytes(b"")
    return str(eseguibile)


class Candidates(unittest.TestCase):
    def test_per_user_pythons_are_never_candidates(self):
        self.assertTrue(runtime.per_user(r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe"))
        self.assertTrue(runtime.per_user(r"C:\Users\x\AppData\Local\Programs\Python\Python39\python.exe"))
        self.assertTrue(runtime.per_user(r"C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12\python.exe"))
        self.assertFalse(runtime.per_user(r"C:\Program Files\Python312\python.exe"))

    def test_machine_pythons_newest_first(self):
        with tmp() as radice:
            vecchio = fake_python(Path(radice), "Python39")
            nuovo = fake_python(Path(radice), "Python312")
            with mock.patch.object(runtime, "registry_pythons", return_value=[]):
                elenco = runtime.candidates({"ProgramFiles": radice, "ProgramFiles(x86)": radice + "-none"})
        self.assertEqual(elenco, [nuovo, vecchio])

    def test_find_protected_skips_writable_and_old_pythons(self):
        with tmp() as radice:
            aperto = fake_python(Path(radice), "Python313")
            buono = fake_python(Path(radice), "Python312")
            with mock.patch.object(runtime, "registry_pythons", return_value=[]), \
                    mock.patch.object(runtime, "version_ok", return_value=True):
                trovato = runtime.find_protected(lambda paths: [p for p in paths if "Python313" in p],
                                                 {"ProgramFiles": radice, "ProgramFiles(x86)": radice + "-none"})
        self.assertEqual(trovato, buono)
        self.assertNotEqual(trovato, aperto)


class Ensure(unittest.TestCase):
    def test_found_python_needs_no_install(self):
        installa = mock.Mock(return_value=True)
        with mock.patch.object(runtime, "find_protected", return_value=r"C:\Program Files\Python312\python.exe"):
            self.assertTrue(runtime.ensure_protected_python(lambda p: [], lambda s: None, [installa]))
        installa.assert_not_called()

    def test_falls_back_to_the_next_installer(self):
        primo, secondo = mock.Mock(return_value=False), mock.Mock(return_value=True)
        with mock.patch.object(runtime, "find_protected", side_effect=[None, r"C:\Program Files\Python312\python.exe"]):
            python = runtime.ensure_protected_python(lambda p: [], lambda s: None, [primo, secondo])
        self.assertEqual(python, r"C:\Program Files\Python312\python.exe")
        primo.assert_called_once()
        secondo.assert_called_once()

    def test_none_when_every_installer_fails(self):
        with mock.patch.object(runtime, "find_protected", return_value=None):
            self.assertIsNone(runtime.ensure_protected_python(lambda p: [], lambda s: None, [mock.Mock(return_value=False)]))

    def test_unsigned_installer_is_not_run(self):
        with mock.patch("urllib.request.urlopen") as apri, mock.patch.object(runtime, "signature_ok", return_value=False), \
                mock.patch.object(runtime, "_run") as esegui:
            apri.return_value.__enter__.return_value.read.side_effect = [b"MZ", b""]
            self.assertFalse(runtime.install_from_python_org(lambda s: None))
        esegui.assert_not_called()

    def test_winget_installs_for_the_whole_machine(self):
        with mock.patch("shutil.which", return_value="winget.exe"), mock.patch.object(runtime, "_run", return_value=0) as esegui:
            self.assertTrue(runtime.install_with_winget(lambda s: None))
        comando = esegui.call_args[0][0]
        self.assertEqual(comando[comando.index("--scope") + 1], "machine")


class Record(unittest.TestCase):
    def test_record_and_read_back(self):
        with tmp() as radice:
            python = fake_python(Path(radice), "Python312")
            runtime.record(Path(radice), python)
            self.assertEqual(runtime.configured(Path(radice)), python)

    def test_missing_python_is_ignored(self):
        with tmp() as radice:
            self.assertIsNone(runtime.configured(Path(radice)))
            runtime.record(Path(radice), os.path.join(radice, "gone", "python.exe"))
            self.assertIsNone(runtime.configured(Path(radice)))


if __name__ == "__main__":
    unittest.main()
