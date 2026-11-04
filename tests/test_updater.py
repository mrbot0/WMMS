"""Tests for program updates: release parsing, checksum, safe extraction and the install over a copy of the program."""
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

from tests import test_api
from tools import build_release
from wmm.agent import updater

RELEASE = {"tag_name": "v9.9.9", "body": "notes", "html_url": "https://github.com/mrbot0/WMMS/releases/tag/v9.9.9",
           "assets": [{"name": "WindowsMaintenanceManager-9.9.9.zip", "browser_download_url": "https://github.com/x/zip"},
                      {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/x/sums"}]}


class Parsing(unittest.TestCase):
    def test_release_and_versions(self):
        r = updater.parse_release(RELEASE)
        self.assertEqual((r["version"], r["zip_name"]), ("9.9.9", "WindowsMaintenanceManager-9.9.9.zip"))
        self.assertGreater(updater.version_tuple("v2.10.0"), updater.version_tuple("2.9.9"))
        with self.assertRaises(updater.UpdateError):
            updater.version_tuple("latest")

    def test_check(self):
        with mock.patch.object(updater, "_get", return_value=json.dumps(RELEASE).encode()):
            self.assertTrue(updater.check("2.1.0")["available"])
            self.assertFalse(updater.check("9.9.9")["available"])
        nessuna = urllib.error.HTTPError(updater.LATEST_URL, 404, "Not Found", {}, None)
        with mock.patch.object(updater, "_get", side_effect=nessuna):
            self.assertIn("no release", updater.check("2.1.0")["reason"])

    def test_checksum_lookup_and_download_hosts(self):
        h = "a" * 64
        self.assertEqual(updater.expected_hash(f"{h}  x.zip\n{'b' * 64}  y.zip", "x.zip"), h)
        with self.assertRaises(updater.UpdateError):
            updater.expected_hash(f"{h}  other.zip", "x.zip")
        with self.assertRaises(updater.UpdateError):
            updater._get("https://evil.example.com/x.zip", 10)


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.zip = build_release.build(self.base / "release")
        self.version = build_release.version()
        self.rilascio = {"version": self.version, "zip_name": self.zip.name, "zip_url": "https://github.com/zip", "sums_url": "https://github.com/sums"}
        self.target = self.base / "installed"
        (self.target / "dati").mkdir(parents=True)
        (self.target / "dati" / "wmm.db").write_text("history", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, pacchetto: bytes, sums: str):
        return mock.patch.object(updater, "_get", side_effect=lambda url, *a, **k: pacchetto if url.endswith("zip") else sums.encode())

    def test_install_copies_the_program_and_keeps_the_data(self):
        with self.serve(self.zip.read_bytes(), (self.base / "release" / "SHA256SUMS.txt").read_text()):
            esito = updater.install(self.rilascio, self.base / "dati", target=self.target)
        self.assertEqual(esito["installed"], self.version)
        self.assertTrue((self.target / "wmm" / "agent" / "updater.py").exists())
        self.assertEqual((self.target / "dati" / "wmm.db").read_text(encoding="utf-8"), "history")

    def test_wrong_checksum_installs_nothing(self):
        with self.serve(self.zip.read_bytes(), f"{'0' * 64}  {self.zip.name}"):
            with self.assertRaises(updater.UpdateError):
                updater.install(self.rilascio, self.base / "dati", target=self.target)
        self.assertFalse((self.target / "wmm").exists())

    def test_zip_with_paths_outside_its_folder_is_refused(self):
        dati = io.BytesIO()
        with zipfile.ZipFile(dati, "w") as zf:
            zf.writestr("../../evil.txt", "x")
        pacchetto = dati.getvalue()
        with self.serve(pacchetto, f"{hashlib.sha256(pacchetto).hexdigest()}  {self.zip.name}"):
            with self.assertRaises(updater.UpdateError):
                updater.install(self.rilascio, self.base / "dati", target=self.target)
        self.assertFalse((self.base / "evil.txt").exists())

    def test_package_of_another_version_is_refused(self):
        rilascio = dict(self.rilascio, version="9.9.9")
        with self.serve(self.zip.read_bytes(), (self.base / "release" / "SHA256SUMS.txt").read_text()):
            with self.assertRaises(updater.UpdateError):
                updater.install(rilascio, self.base / "dati", target=self.target)


class UpdateApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_check_and_install(self):
        with mock.patch.object(updater, "check", return_value={"available": False, "current": "2.2.0", "latest": "2.2.0", "reason": ""}):
            self.assertEqual(self.request("GET", "/api/v1/update/check")[0], 200)
            self.assertEqual(self.request("POST", "/api/v1/update/install")[0], 409)
        disponibile = dict(updater.parse_release(RELEASE), available=True, current="2.2.0", latest="9.9.9")
        with mock.patch.object(updater, "check", return_value=disponibile), \
                mock.patch.object(updater, "install", return_value={"installed": "9.9.9"}) as installa:
            stato, dati, _ = self.request("POST", "/api/v1/update/install")
        self.assertEqual((stato, dati["installed"], dati["restart"]), (200, "9.9.9", True))
        installa.assert_called_once()
        with mock.patch.object(updater, "check", side_effect=updater.UpdateError("offline")):
            self.assertEqual(self.request("GET", "/api/v1/update/check")[0], 502)


if __name__ == "__main__":
    unittest.main()
