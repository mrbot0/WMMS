"""Tests for the rules file of the Applications page: validation, newest copy wins, download."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_api
from wmm.agent import apps


def bundled():
    return json.loads(apps.BUNDLED_RULES.read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    def tearDown(self):
        apps.RULES_OVERRIDE = None
        apps.load_rules()

    def test_bundled_rules_are_valid_and_loaded(self):
        regole = apps.validate_rules(bundled())
        self.assertGreaterEqual(len(regole["end_of_life"]), 15)
        self.assertIn((3, 9), regole["python_eol"])
        self.assertEqual(apps.RULES_INFO["source"], "built-in")

    def test_invalid_files_are_refused(self):
        for rotto in ({}, {"version": "yesterday"}, dict(bundled(), unwanted="(unclosed"), dict(bundled(), min_versions=[["x", "abc", "t"]]),
                      dict(bundled(), end_of_life=[["x", "2020-13", "t"]]), dict(bundled(), node_eol={"x": "2020-01-01"})):
            with self.assertRaises(ValueError):
                apps.validate_rules(rotto)

    def test_newer_download_wins_older_is_ignored(self):
        with tempfile.TemporaryDirectory() as cartella:
            apps.RULES_OVERRIDE = Path(cartella) / "app_rules.json"
            vecchie = dict(bundled(), version="2000-01-01", unwanted="old-adware")
            apps.RULES_OVERRIDE.write_text(json.dumps(vecchie), encoding="utf-8")
            self.assertEqual(apps.load_rules()["source"], "built-in")
            nuove = dict(bundled(), version="2999-01-01", unwanted="brand new adware")
            apps.RULES_OVERRIDE.write_text(json.dumps(nuove), encoding="utf-8")
            self.assertEqual(apps.load_rules()["source"], "downloaded")
            self.assertEqual(apps.category({"name": "Brand New Adware"}), "unwanted")

    def test_update_downloads_validates_and_saves(self):
        nuove = json.dumps(dict(bundled(), version="2999-01-01")).encode()
        with tempfile.TemporaryDirectory() as cartella:
            apps.RULES_OVERRIDE = Path(cartella) / "app_rules.json"
            with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(nuove)):
                esito = apps.update_rules()
            self.assertTrue(esito["updated"])
            self.assertTrue(apps.RULES_OVERRIDE.exists())
            with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(nuove)):
                self.assertFalse(apps.update_rules()["updated"])
            with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"version": "2999-02-01"}')):
                with self.assertRaises(ValueError):
                    apps.update_rules()
            self.assertEqual(apps.RULES_INFO["version"], "2999-01-01")


class RulesApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_info_and_failed_update(self):
        stato, dati, _ = self.request("GET", "/api/v1/apps/rules")
        self.assertEqual(stato, 200)
        self.assertIn("version", dati)
        with mock.patch.object(apps, "update_rules", side_effect=OSError("offline")):
            self.assertEqual(self.request("POST", "/api/v1/apps/rules/update")[0], 502)


if __name__ == "__main__":
    unittest.main()
