"""Tests for the Applications page: rules, last use, suggestions, winget parsing and the API routes."""
import codecs
import unittest
from datetime import date
from unittest import mock

from tests import test_api
from wmm.agent import apps

TODAY = date(2026, 11, 3)


def app(name, version="1.0", publisher="Acme", **extra):
    voce = {"id": name.lower().replace(" ", "")[:16].ljust(16, "0"), "name": name, "version": version, "publisher": publisher,
            "installed": "2026-01-01", "size_mb": 100.0, "uninstall": "C:\\x\\uninstall.exe", "broken": False, "folder": "C:\\x"}
    voce.update(extra)
    voce["category"] = apps.category(voce)
    voce["issues"] = apps.assess(voce, TODAY)
    voce["status"] = apps.status(voce["issues"])
    voce.update(apps.usage(voce, TODAY))
    voce["removable"] = apps.removable(voce)
    return voce


class Rules(unittest.TestCase):
    def test_end_of_life_products_are_risky(self):
        for nome in ("Microsoft Office Professional Plus 2019 - it-it", "Adobe Flash Player 32 NPAPI", "Microsoft Windows Desktop Runtime - 6.0.11 (x64)",
                     "Microsoft Office Professional Plus 2021"):
            self.assertEqual(app(nome)["status"], "risk", nome)
        self.assertEqual(app("Microsoft Office LTSC Professional Plus 2024")["status"], "ok")

    def test_support_ending_within_three_months_is_a_review(self):
        voce = app("Microsoft Windows Desktop Runtime - 8.0.10 (x64)")
        self.assertEqual(voce["status"], "review")
        self.assertEqual(voce["issues"][0]["kind"], "eol_soon")

    def test_python_and_node_versions(self):
        self.assertEqual(app("Python 3.9.4 (64-bit)")["status"], "risk")
        self.assertEqual(app("Python 3.12.1 (64-bit)")["status"], "ok")
        self.assertEqual(app("Node.js", "18.20.1")["status"], "risk")
        self.assertEqual(app("Node.js", "22.11.0")["status"], "ok")

    def test_minimum_safe_versions(self):
        self.assertEqual(app("WinRAR 6.21 (64-bit)", "6.21.0")["status"], "risk")
        self.assertEqual(app("WinRAR 7.13 (64-bit)", "7.13.0")["status"], "ok")
        self.assertEqual(app("7-Zip 24.08 (x64)", "24.08")["status"], "risk")
        self.assertEqual(app("VLC media player", "3.0.21")["status"], "ok")

    def test_categories_and_their_advice(self):
        self.assertEqual(app("OneLaunch")["status"], "risk")
        self.assertEqual(app("AnyDesk")["issues"][0]["kind"], "remote")
        self.assertEqual(app("Driver Booster 11")["issues"][0]["kind"], "optimizer")
        self.assertEqual(app("Unknown Tool", publisher="")["issues"][0]["kind"], "publisher")
        self.assertEqual(app("Microsoft Windows Application Compatibility Fix Database", publisher="")["status"], "ok")
        # Drivers and runtimes are never offered for removal.
        self.assertFalse(app("Realtek Audio Driver")["removable"])
        self.assertFalse(app("Microsoft Visual C++ 2015-2022 Redistributable (x64)")["removable"])
        self.assertTrue(app("Some Game")["removable"])

    def test_usage(self):
        self.assertEqual(app("A", last_used="2026-10-30")["usage"], "recent")
        self.assertEqual(app("A", last_used="2026-01-30")["usage"], "unused")
        # Without a recorded run, an old program is unused only when Prefetch could be read.
        voce = {"installed": "2024-01-01"}
        self.assertEqual(apps.usage(voce, TODAY, completo=True)["usage"], "unused")
        self.assertEqual(apps.usage(voce, TODAY, completo=False)["usage"], "unknown")

    def test_suggestions(self):
        elenco = [app("Avast Free Antivirus"), app("Bitdefender Total Security"), app("TeamViewer"), app("Python 3.9.4 (64-bit)"),
                  app("Python 3.12.1 (64-bit)", "3.12.1"), app("Old Game", installed="2020-01-01", last_used="2025-01-01"),
                  app("Gone", broken=True)]
        browsers = [{"id": "chrome", "cache_mb": 900.0}]
        store = [{"id": "s1", "bloat": True}]
        titoli = [s["title"] for s in apps.suggestions(elenco, store, browsers)]
        self.assertIn("More than one antivirus", titoli)
        self.assertIn("Remote access programs", titoli)
        self.assertTrue(any("not used for months" in t for t in titoli))
        self.assertTrue(any("2 versions installed" in t for t in titoli))
        self.assertTrue(any("leftover" in t for t in titoli))
        self.assertIn("1 preinstalled Store app", titoli)
        self.assertIn("1 leftover entry", titoli)
        self.assertTrue(any("Browser caches" in t for t in titoli))


class Parsing(unittest.TestCase):
    def test_userassist_record(self):
        nome = codecs.encode("{6D809377-6AF0-444B-8957-A3773F02200E}\\VideoLAN\\VLC\\vlc.exe", "rot13")
        filetime = (133_000_000_000_000_000).to_bytes(8, "little")
        percorso, quando = apps.parse_userassist(nome, bytes(60) + filetime + bytes(4))
        self.assertTrue(percorso.endswith("\\videolan\\vlc\\vlc.exe"))
        self.assertRegex(quando, r"^20\d\d-\d\d-\d\d$")
        self.assertIsNone(apps.parse_userassist(nome, b"short"))

    def test_uninstall_command_and_folder(self):
        self.assertEqual(apps.uninstall_command({"UninstallString": "MsiExec.exe /I{12345678-1234-1234-1234-123456789012}"}),
                         "MsiExec.exe /X{12345678-1234-1234-1234-123456789012}")
        self.assertEqual(apps.uninstall_command({"UninstallString": "a", "QuietUninstallString": "b /S"}), "b /S")
        self.assertEqual(apps.install_folder({"DisplayIcon": '"C:\\Program Files\\Foo\\foo.exe",0'}), "C:\\Program Files\\Foo")
        self.assertEqual(apps.install_folder({"UninstallString": "C:\\Windows\\System32\\x.exe"}), "")
        self.assertFalse(apps.is_broken("MsiExec.exe /X{12345678-1234-1234-1234-123456789012}"))
        self.assertTrue(apps.is_broken('"C:\\No\\Such\\Folder\\unins000.exe" /SILENT'))

    def test_last_used_from_shortcuts_and_running_programs(self):
        voce = {"name": "Microsoft Office Professional Plus 2019", "folder": ""}
        self.assertEqual(apps.last_used(voce, {}, {}, {"excel": "2026-11-01"}, [], TODAY), "2026-11-01")
        voce = {"name": "Hue Sync", "folder": "C:\\Program Files\\Hue Sync"}
        self.assertEqual(apps.last_used(voce, {}, {}, {}, ["c:\\program files\\hue sync\\huesync.exe"], TODAY), "2026-11-03")
        self.assertIsNone(apps.last_used({"name": "Other", "folder": "C:\\Other"}, {}, {}, {"steam": "2026-11-01"}, [], TODAY))

    def test_store_names(self):
        self.assertEqual(apps.store_label("Microsoft.WindowsCalculator"), "Windows Calculator")
        self.assertEqual(apps.store_label("Clipchamp.Clipchamp"), "Clipchamp")
        voci = apps.parse_store([{"package": "king.com.CandyCrushSaga_1.0_x86__kgqvnymyfvs32", "family": "king.com.candycrushsaga_kgqvnymyfvs32",
                                  "id_name": "king.com.CandyCrushSaga", "name": "Candy Crush Saga"},
                                 {"package": "bad name; rm", "name": "x"}],
                                {"king.com.candycrushsaga_kgqvnymyfvs32!app": "2026-10-01"})
        self.assertEqual(len(voci), 1)
        self.assertTrue(voci[0]["bloat"])
        self.assertEqual(voci[0]["last_used"], "2026-10-01")

    def test_winget_table_in_any_language(self):
        testo = ("Nome                     ID                       Versione    Disponibile Origine\n"
                 "-------------------------------------------------------------------------------\n"
                 "Mozilla Firefox (x64 it) Mozilla.Firefox.it       127.0       144.0       winget\n"
                 "7-Zip                    7zip.7zip                23.01       25.01       winget\n"
                 "2 aggiornamenti disponibili.\n")
        righe = apps.parse_winget_upgrade(testo)
        self.assertEqual([r["id"] for r in righe], ["Mozilla.Firefox.it", "7zip.7zip"])
        self.assertEqual(righe[1]["available"], "25.01")
        self.assertEqual(apps.parse_winget_upgrade("No installed package found."), [])

    def test_browser_cache_folders_never_include_profile_data(self):
        for browser_id, *_ in apps.BROWSER_PROFILES:
            for cartella in apps.cache_folders(browser_id):
                self.assertNotRegex(cartella.lower(), r"cookies|login data|history|bookmarks|preferences|local storage")


SCAN = {"apps": [], "store": [{"id": "abcdefabcdefabcd", "package": "Microsoft.BingNews_1.0_x64__8wekyb3d8bbwe", "name": "News"}],
        "browsers": [], "installers": {"files": [], "count": 0, "mb": 0}, "suggestions": [], "errors": []}
INSTALLED = [{"id": "0123456789abcdef", "name": "Tool", "version": "1", "uninstall": "C:\\t\\unins.exe", "broken": False,
              "folder": "C:\\t", "key": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Tool"},
             {"id": "fedcba9876543210", "name": "Gone", "version": "1", "uninstall": "C:\\g\\unins.exe", "broken": True,
              "folder": "", "key": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Gone"}]


class AppsApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_list_scans_once_and_refresh_rescans(self):
        with mock.patch.object(apps, "scan", return_value=dict(SCAN)) as scan:
            self.assertEqual(self.request("GET", "/api/v1/apps")[0], 200)
            self.request("GET", "/api/v1/apps")
            self.assertEqual(scan.call_count, 1)
            self.request("GET", "/api/v1/apps?refresh=1")
            self.assertEqual(scan.call_count, 2)

    def test_uninstall_reads_the_command_from_windows(self):
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), \
                mock.patch.object(apps, "run_uninstaller", return_value={"started": "x"}) as run:
            stato, dati, _ = self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall", {"uninstall": "evil.exe"})
            self.assertEqual(stato, 200, dati)
            self.assertEqual(run.call_args[0][0]["uninstall"], "C:\\t\\unins.exe")
            self.assertEqual(self.request("POST", "/api/v1/apps/aaaaaaaaaaaaaaaa/uninstall")[0], 404)
        self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall", token=False)[0], 403)

    def test_remove_entry_only_for_leftovers(self):
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), \
                mock.patch.object(self.agent.registry, "delete_key", return_value={"backup": "b.reg"}) as cancella:
            self.assertEqual(self.request("POST", "/api/v1/apps/0123456789abcdef/remove-entry")[0], 409)
            self.assertEqual(self.request("POST", "/api/v1/apps/fedcba9876543210/remove-entry")[0], 200)
            cancella.assert_called_once_with(INSTALLED[1]["key"])

    def test_store_remove_browser_clean_and_update(self):
        with mock.patch.object(apps, "scan", return_value=dict(SCAN)), \
                mock.patch.object(apps, "remove_store_app", return_value={"removed": "x"}) as rimuovi, \
                mock.patch.object(apps, "clean_browser", return_value={"freed_mb": 5}), mock.patch.object(apps, "browser_caches", return_value=[]), \
                mock.patch.object(apps, "winget_upgrade", return_value={"output": ""}) as aggiorna:
            self.assertEqual(self.request("POST", "/api/v1/apps/store/abcdefabcdefabcd/remove")[0], 200)
            rimuovi.assert_called_once_with(SCAN["store"][0]["package"])
            stato, dati, _ = self.request("POST", "/api/v1/apps/browsers/chrome/clean")
            self.assertEqual((stato, dati["freed_mb"]), (200, 5))
            self.assertEqual(self.request("POST", "/api/v1/apps/browsers/netscape/clean")[0], 404)
            self.assertEqual(self.request("POST", "/api/v1/apps/update", {"id": "7zip.7zip"})[0], 200)
            self.assertEqual(self.request("POST", "/api/v1/apps/update", {"id": "a; del"})[0], 400)
            aggiorna.assert_called_once_with("7zip.7zip")

    def test_changes_are_recorded_in_history(self):
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), \
                mock.patch.object(apps, "run_uninstaller", return_value={"started": "x"}):
            self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")
        stato, dati, _ = self.request("GET", "/api/v1/history")
        self.assertEqual(stato, 200)
        self.assertIn("apps.uninstall", str(dati))


class AppsApiPreview(unittest.TestCase):
    """In preview mode the request succeeds but nothing runs."""
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def setUp(self):
        test_api.ApiTests.setUp(self)
        self.agent.preview = True

    def test_uninstall_does_not_run(self):
        with mock.patch.object(apps, "read_installed", return_value=INSTALLED), mock.patch.object(apps, "run_uninstaller") as run:
            stato, dati, _ = self.request("POST", "/api/v1/apps/0123456789abcdef/uninstall")
        self.assertEqual((stato, dati.get("preview")), (200, True))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
