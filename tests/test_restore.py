"""Tests for restore points around manual changes and the way back from History."""
import unittest
from datetime import datetime
from unittest import mock

from tests import test_api
from tests.test_apps import INSTALLED
from wmm.agent import apps, restore

POINTS = '[{"seq":12,"description":"WMM: x","created":"2026-11-03T10:30:00"},{"seq":11,"description":"Windows Update","created":"2026-10-30T08:00:00"}]'


class Points(unittest.TestCase):
    def test_parse_and_order(self):
        punti = restore.parse_points(POINTS)
        self.assertEqual([p["seq"] for p in punti], [12, 11])
        self.assertEqual(restore.parse_points('{"seq":3,"description":"a","created":"2026-01-01T00:00:00"}')[0]["seq"], 3)
        self.assertEqual(restore.parse_points("not json"), [])

    def test_recent_point_is_reused(self):
        punti = restore.parse_points(POINTS)
        self.assertEqual(restore.recent(punti, datetime(2026, 11, 3, 11, 0))["seq"], 12)
        self.assertIsNone(restore.recent(punti, datetime(2026, 11, 3, 12, 0)))

    def test_point_before_a_change(self):
        punti = restore.parse_points(POINTS)
        self.assertEqual(restore.before(punti, "2026-11-03T10:31:05")["seq"], 12)
        self.assertEqual(restore.before(punti, "2026-11-01T00:00:00")["seq"], 11)
        self.assertIsNone(restore.before(punti, "2026-01-01T00:00:00"))

    def test_ensure_point_reuses_without_creating(self):
        with mock.patch.object(restore, "points", return_value=[{"seq": 5, "description": "", "created": datetime.now().isoformat(timespec="seconds")}]), \
                mock.patch.object(restore, "_powershell") as ps:
            self.assertEqual(restore.ensure_point("test"), {"seq": 5, "description": "", "created": mock.ANY, "new": False})
            ps.assert_not_called()

    def test_ensure_point_fails_when_windows_makes_none(self):
        with mock.patch.object(restore, "points", return_value=[]), \
                mock.patch.object(restore, "_powershell", return_value=mock.Mock(stderr="System Restore is off", stdout="")):
            with self.assertRaises(restore.RestoreError):
                restore.ensure_point("test")


class RestoreApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_uninstall_records_the_restore_point(self):
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), mock.patch.object(apps, "run_uninstaller", return_value={"started": "x"}):
            stato, dati, _ = self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")
        self.assertEqual((stato, dati["restore_point"]), (200, 7))
        self.assertIn("restore point #7", str(self.request("GET", "/api/v1/history")[1]))

    def test_no_point_stops_the_change_unless_the_user_agrees(self):
        with mock.patch.object(restore, "ensure_point", side_effect=restore.RestoreError("off")), \
                mock.patch.object(apps, "read_installed", return_value=INSTALLED), mock.patch.object(apps, "run_uninstaller", return_value={}) as run:
            self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")[0], 412)
            run.assert_not_called()
            self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall", {"no_restore_point": True})[0], 200)
            run.assert_called_once()

    def test_setting_turns_the_point_off(self):
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"restore_before_changes": "0"})[0], 200)
        with mock.patch.object(restore, "ensure_point") as punto, mock.patch.object(apps, "read_installed", return_value=INSTALLED), \
                mock.patch.object(apps, "run_uninstaller", return_value={}):
            self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")[0], 200)
            punto.assert_not_called()

    def test_list_and_open(self):
        with mock.patch.object(restore, "points", return_value=restore.parse_points(POINTS)):
            stato, dati, _ = self.request("GET", "/api/v1/restore-points")
        self.assertEqual((stato, len(dati["points"])), (200, 2))
        with mock.patch.object(restore, "open_wizard") as apri:
            self.assertEqual(self.request("POST", "/api/v1/restore-points/open")[0], 200)
            apri.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class Leftovers(unittest.TestCase):
    def test_names_skip_the_publisher_and_shared_words(self):
        self.assertEqual(apps._names({"name": "VLC media player", "publisher": "VideoLAN"}), ["vlc media player", "vlc"])
        self.assertEqual(apps._names({"name": "CPUID CPU-Z 2.05", "publisher": "CPUID, Inc."}), ["cpuid cpu z"])
        self.assertEqual(apps._names({"name": "Microsoft Teams", "publisher": "Microsoft"}), ["microsoft teams"])
        self.assertEqual(apps._names({"name": "Java 8 Update 481", "publisher": "Oracle"}), [])

    def test_folders_of_other_programs_are_never_offered(self):
        gone = {"id": "a", "name": "WinRAR 6.02 (32-bit)", "publisher": "win.rar GmbH", "folder": ""}
        other = {"id": "b", "name": "WinRAR 6.21 (64-bit)", "publisher": "win.rar GmbH", "folder": r"C:\Program Files\WinRAR"}
        with mock.patch.object(apps, "leftover_folders", return_value=[r"C:\Program Files\WinRAR", r"C:\Program Files (x86)\WinRAR"]), \
                mock.patch.object(apps, "leftover_keys", return_value=[r"HKCU\Software\winrar"]), mock.patch.object(apps, "folder_size", return_value=1.0):
            trovati = apps.leftovers(gone, [gone, other])
        self.assertEqual([l["path"] for l in trovati], [r"C:\Program Files (x86)\WinRAR"])  # the key name is shared with the 64-bit one

    def test_only_folders_inside_program_roots(self):
        self.assertFalse(apps.safe_leftover(r"C:\Windows\System32"))
        self.assertFalse(apps.safe_leftover(apps.os.path.expandvars("%ProgramFiles%")))
        self.assertFalse(apps.safe_leftover(apps.os.path.expandvars(r"%ProgramFiles%\Common Files")))
        with self.assertRaises(ValueError):
            apps.recycle(r"C:\Users")


class UninstallFlow(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_status_then_leftovers_cleanup(self):
        rimasti = [{"id": "aaaaaaaaaaaa", "kind": "folder", "path": r"C:\Program Files\Tool", "size_mb": 3.0},
                   {"id": "bbbbbbbbbbbb", "kind": "key", "path": r"HKCU\Software\Tool", "size_mb": None}]
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), mock.patch.object(apps, "run_uninstaller", return_value={"pid": 42}):
            self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")
        with mock.patch.object(apps, "is_running", return_value=True), mock.patch.object(apps, "read_installed", return_value=INSTALLED):
            dati = self.request("GET", "/api/v1/apps/0123456789abcdef/uninstall-status")[1]
        self.assertEqual((dati["running"], dati["removed"], "leftovers" in dati), (True, False, False))
        self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/leftovers", {"ids": ["aaaaaaaaaaaa"]})[0], 409)
        with mock.patch.object(apps, "is_running", return_value=False), mock.patch.object(apps, "read_installed", return_value=INSTALLED[1:]), \
                mock.patch.object(apps, "leftovers", return_value=[dict(l) for l in rimasti]):
            dati = self.request("GET", "/api/v1/apps/0123456789abcdef/uninstall-status")[1]
        self.assertEqual(len(dati["leftovers"]), 2)
        with mock.patch.object(apps, "recycle") as cestino, mock.patch.object(self.agent.registry, "delete_key", return_value={"backup": "x.reg"}) as chiave:
            stato, dati, _ = self.request("POST", "/api/v1/apps/0123456789abcdef/leftovers", {"ids": ["aaaaaaaaaaaa", "bbbbbbbbbbbb", "zzz"]})
        self.assertEqual((stato, len(dati["removed"])), (200, 2))
        cestino.assert_called_once_with(r"C:\Program Files\Tool")
        chiave.assert_called_once_with(r"HKCU\Software\Tool")
        self.assertEqual(self.request("GET", "/api/v1/apps/fedcba9876543210/uninstall-status")[0], 404)
