"""Tests for the extended inventory (pure parsing, filesystem helpers on temporary folders)."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import inventory, tools


class Startup(unittest.TestCase):
    def test_approved_state(self):
        self.assertTrue(inventory.approved_enabled(None))
        self.assertTrue(inventory.approved_enabled(bytes([2] + [0] * 11)))
        self.assertTrue(inventory.approved_enabled(bytes([6] + [0] * 11)))
        self.assertFalse(inventory.approved_enabled(bytes([3] + [0] * 11)))
        self.assertTrue(inventory.approved_enabled(b""))

    def test_approved_value_roundtrip(self):
        acceso = inventory.approved_value(True, 0)
        spento = inventory.approved_value(False, 133000000000000000)
        self.assertEqual(len(acceso), 12)
        self.assertEqual(len(spento), 12)
        self.assertTrue(inventory.approved_enabled(acceso))
        self.assertFalse(inventory.approved_enabled(spento))
        self.assertEqual(int.from_bytes(spento[4:], "little"), 133000000000000000)

    def test_startup_id_is_stable_and_url_safe(self):
        uno = inventory.startup_id("HKCU", "Run", "OneDrive")
        self.assertEqual(uno, inventory.startup_id("HKCU", "Run", "OneDrive"))
        self.assertNotEqual(uno, inventory.startup_id("HKLM", "Run", "OneDrive"))
        self.assertRegex(uno, r"^[0-9a-f]{16}$")


def item(name, command="", enabled=True):
    return {"id": inventory.startup_id("HKCU", "Run", name), "name": name, "command": command, "enabled": enabled,
            "scope": "HKCU", "kind": "Run", "location": "Registry (current user)"}


class OptimizeStartup(unittest.TestCase):
    def test_essential_entries(self):
        for nome, comando in (("SecurityHealth", r"%windir%\system32\SecurityHealthSystray.exe"), ("RtkAudUService", r"C:\Windows\RtkAudUService64.exe"),
                              ("Avast", r"C:\Program Files\Avast Software\Avast\AvLaunch.exe"), ("ETDCtrl", r"C:\Program Files\Elantech\ETDCtrl.exe"),
                              ("FortiClient", r"C:\Program Files\Fortinet\FortiClient\FortiTray.exe"), ("Bitwarden", "x"),
                              ("Riot Vanguard", r"C:\Program Files\Riot Vanguard\vgtray.exe"), ("Stream Deck", r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe"),
                              ("Wave Link", r"C:\Program Files\Elgato\WaveLink\WaveLink.exe"), ("RazerAppEngine", r"C:\Program Files\Razer\RazerAppEngine\RazerAppEngine.exe"),
                              ("Volume Controller SD plugin", "x"), ("LGHUB", r"C:\Program Files\LGHUB\lghub.exe")):
            self.assertTrue(inventory.is_essential_startup(item(nome, comando)), nome)

    def test_non_essential_entries(self):
        for nome, comando in (("Spotify", r"C:\Users\x\AppData\Roaming\Spotify\Spotify.exe /minimized"), ("Discord", "Update.exe --processStart Discord.exe"),
                              ("Steam", r"C:\Program Files (x86)\Steam\steam.exe -silent"), ("OneDrive", r"C:\Program Files\Microsoft OneDrive\OneDrive.exe /background"),
                              ("Teams", r"C:\Users\x\AppData\Local\Microsoft\Teams\Update.exe --processStart Teams.exe"),
                              ("SunJavaUpdateSched", r"C:\Program Files (x86)\Common Files\Java\Java Update\jusched.exe"),
                              ("Logi Download Assistant", r"C:\Windows\system32\rundll32.exe C:\Windows\System32\LogiLDA.dll,LogiFetch"),
                              ("MicrosoftEdgeAutoLaunch_B6AF", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe --no-startup-window")):
            self.assertFalse(inventory.is_essential_startup(item(nome, comando)), nome)

    def test_optimize_disables_only_non_essential_enabled_entries(self):
        voci = [item("SecurityHealth", "SecurityHealthSystray.exe"), item("Spotify", "Spotify.exe"), item("Steam", "steam.exe", enabled=False)]
        cambiate = []
        ctx = FakeContext()
        with mock.patch.object(inventory, "startup_items", return_value=voci), \
                mock.patch.object(inventory, "set_startup_enabled", side_effect=lambda v, on: cambiate.append((v["name"], on))):
            esito = tools.optimize_startup(ctx)
        self.assertEqual(cambiate, [("Spotify", False)])
        self.assertEqual(esito.stato, tools.Stato.OK)
        self.assertIn("1 disabled", esito.nota)

    def test_optimize_preview_changes_nothing(self):
        ctx = FakeContext()
        ctx.anteprima = True
        with mock.patch.object(inventory, "startup_items", return_value=[item("Spotify", "Spotify.exe")]), \
                mock.patch.object(inventory, "set_startup_enabled") as imposta:
            esito = tools.optimize_startup(ctx)
        imposta.assert_not_called()
        self.assertEqual(esito.stato, tools.Stato.ANTEPRIMA)


class Apps(unittest.TestCase):
    def test_parse_uninstall_entry(self):
        app = inventory.parse_uninstall_entry({
            "DisplayName": "7-Zip 23.01", "Publisher": "Igor Pavlov", "DisplayVersion": "23.01",
            "InstallDate": "20240115", "EstimatedSize": 5 * 1024,
        })
        self.assertEqual(app, {"name": "7-Zip 23.01", "publisher": "Igor Pavlov", "version": "23.01",
                               "installed": "2024-01-15", "size_mb": 5.0})

    def test_hidden_entries_are_skipped(self):
        self.assertIsNone(inventory.parse_uninstall_entry({"DisplayName": "x", "SystemComponent": 1}))
        self.assertIsNone(inventory.parse_uninstall_entry({"DisplayName": "KB1", "ParentKeyName": "Office"}))
        self.assertIsNone(inventory.parse_uninstall_entry({"Publisher": "no name"}))

    def test_bad_date_and_size(self):
        app = inventory.parse_uninstall_entry({"DisplayName": "x", "InstallDate": "2024", "EstimatedSize": "?"})
        self.assertIsNone(app["installed"])
        self.assertIsNone(app["size_mb"])


class Power(unittest.TestCase):
    def test_parse_power_scheme(self):
        testo = "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"
        self.assertEqual(inventory.parse_power_scheme(testo),
                         {"guid": "381b4222-f694-41f0-9685-ff5bb260df2e", "name": "Balanced", "plan": "balanced"})
        testo = "GUID combinazione per il risparmio di energia: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (Prestazioni elevate)"
        self.assertEqual(inventory.parse_power_scheme(testo)["plan"], "high")
        self.assertEqual(inventory.parse_power_scheme("12345678-1234-1234-1234-123456789abc (Mine)")["plan"], "custom")
        self.assertIsNone(inventory.parse_power_scheme("error"))


class Network(unittest.TestCase):
    def test_summarize_network(self):
        raw = {"adapters": {"name": "Ethernet", "status": "Up", "speed": "1 Gbps", "ipv4": "192.168.1.2", "dns": ["1.1.1.1"]},
               "router": [1, 2, 1, 2], "cloudflare": [10, 12], "google": [], "routerAddress": "192.168.1.1",
               "dnsMs": 40, "dnsOk": True, "connections": 55}
        dati = inventory.summarize_network(raw)
        self.assertEqual(dati["adapters"][0]["ipv4"], ["192.168.1.2"])
        destinazioni = {t["name"]: t for t in dati["targets"]}
        self.assertEqual(destinazioni["Router"]["lost"], 0)
        self.assertEqual(destinazioni["Cloudflare"]["lost"], 2)
        self.assertEqual(destinazioni["Google"]["lost"], 4)
        self.assertEqual(dati["dns_ms"], 40)

    def test_link_speed_parsing(self):
        self.assertEqual(inventory.link_speed_mbps("360 Mbps"), 360)
        self.assertEqual(inventory.link_speed_mbps("1 Gbps"), 1000)
        self.assertEqual(inventory.link_speed_mbps("2.5 Gbps"), 2500)
        self.assertIsNone(inventory.link_speed_mbps(""))


class Events(unittest.TestCase):
    def test_summarize_events(self):
        raw = [{"source": "disk", "log": "System", "count": 3, "level": 2, "last": "2026-11-01T10:00:00", "message": "x" * 400},
               {"source": "App", "log": "Application", "count": 9, "level": 2, "last": "2026-11-02T10:00:00", "message": "boom"}]
        dati = inventory.summarize_events(raw)
        self.assertEqual(dati["total"], 12)
        self.assertEqual(dati["top"][0]["source"], "App")
        self.assertEqual(len(dati["top"][1]["message"]), 200)
        self.assertEqual(inventory.summarize_events(None), {"total": 0, "top": []})


class Extras(unittest.TestCase):
    def test_parse_hosts_ignores_comments_and_localhost(self):
        testo = "# comment\n127.0.0.1 localhost\n::1 localhost\n\n10.0.0.5   intranet.local   # office\n0.0.0.0 ads.example\n"
        self.assertEqual(inventory.parse_hosts(testo), ["10.0.0.5 intranet.local", "0.0.0.0 ads.example"])
        self.assertEqual(inventory.parse_hosts(""), [])

    def test_extras_for_area_reads_only_its_keys(self):
        valori = {("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyEnable"): 1,
                  ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyServer"): "proxy:8080"}
        with mock.patch.object(inventory, "_reg", side_effect=lambda h, k, n: valori.get((h, k, n))), \
                mock.patch.object(inventory, "_read_hosts", return_value=["10.0.0.5 intranet"]):
            dati = inventory.extras_for("network")
        self.assertEqual(dati["proxy"], {"enabled": True, "server": "proxy:8080"})
        self.assertEqual(dati["hosts_entries"], ["10.0.0.5 intranet"])
        self.assertEqual(inventory.extras_for("cleanup"), {})

    def test_security_privacy_extras(self):
        valori = {
            ("HKLM", r"SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters", "AllowInsecureGuestAuth"): 1,
            ("HKLM", r"SYSTEM\CurrentControlSet\Control\Lsa", "RunAsPPL"): 1,
            ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient", "EnableMulticast"): 0,
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled"): 1,
        }
        with mock.patch.object(inventory, "_reg", side_effect=lambda h, k, n: valori.get((h, k, n))), \
                mock.patch.object(inventory, "_count_files", return_value=42):
            dati = inventory.extras_for("security")
        self.assertEqual((dati["smb_insecure_guest"], dati["lsa_protection"], dati["llmnr_disabled"]), (True, True, True))
        self.assertTrue(dati["advertising_id"])
        self.assertIsNone(dati["telemetry_level"])
        self.assertEqual(dati["recent_items"], 42)


class Battery(unittest.TestCase):
    def test_battery_health(self):
        self.assertEqual(inventory.battery_health(50000, 40000), 80)
        self.assertIsNone(inventory.battery_health(0, 40000))
        self.assertIsNone(inventory.battery_health(None, None))
        self.assertEqual(inventory.battery_health(50000, 60000), 100)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Big").mkdir()
        (self.root / "Big" / "sub").mkdir()
        (self.root / "Small").mkdir()
        (self.root / "Big" / "a.bin").write_bytes(b"x" * 1000)
        (self.root / "Big" / "sub" / "b.bin").write_bytes(b"x" * 3000)
        (self.root / "Small" / "c.bin").write_bytes(b"x" * 10)
        (self.root / "root.bin").write_bytes(b"x" * 50)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_tree(self):
        risultato = inventory.scan_tree(str(self.root), time.monotonic() + 30, top_n=2)
        cartelle = {c["name"]: c["bytes"] for c in risultato["folders"]}
        self.assertEqual(cartelle, {"Big": 4000, "Small": 10})
        self.assertEqual([Path(f["path"]).name for f in risultato["files"]], ["b.bin", "a.bin"])
        self.assertTrue(risultato["complete"])
        self.assertEqual(risultato["folders"][0]["name"], "Big")

    def test_scan_tree_deadline(self):
        self.assertFalse(inventory.scan_tree(str(self.root), time.monotonic() - 1)["complete"])

    def test_wipe_preview_changes_nothing(self):
        totale, file, saltati = tools.wipe([(str(self.root / "Big"), None)], preview=True)
        self.assertEqual((totale, file, saltati), (4000, 2, 0))
        self.assertTrue((self.root / "Big" / "a.bin").exists())

    def test_wipe_recursive_and_pattern(self):
        (self.root / "thumbcache_1.db").write_bytes(b"x" * 7)
        (self.root / "keep.db").write_bytes(b"x")
        totale, file, _ = tools.wipe([(str(self.root / "Big"), None), (str(self.root), "thumbcache_*.db")], preview=False)
        self.assertEqual((totale, file), (4007, 3))
        self.assertFalse((self.root / "Big" / "sub" / "b.bin").exists())
        self.assertTrue((self.root / "Big" / "sub").is_dir())
        self.assertTrue((self.root / "keep.db").exists())
        self.assertTrue((self.root / "root.bin").exists())

    def test_wipe_respects_age_and_exclusions(self):
        vecchio = time.time() - 10 * 86400
        (self.root / "claude").mkdir()
        for percorso in (self.root / "Big" / "a.bin", self.root / "claude" / "keep.bin"):
            if not percorso.exists():
                percorso.write_bytes(b"x" * 100)
            os.utime(percorso, (vecchio, vecchio))
        limite = time.time() - 3 * 86400
        totale, file, _ = tools.wipe([(str(self.root), None)], preview=False, older_than=limite, exclude=("claude",))
        self.assertEqual((totale, file), (1000, 1))
        self.assertFalse((self.root / "Big" / "a.bin").exists())
        self.assertTrue((self.root / "Big" / "sub" / "b.bin").exists())
        self.assertTrue((self.root / "claude" / "keep.bin").exists())

    def test_wipe_missing_folder(self):
        self.assertEqual(tools.wipe([(str(self.root / "nope"), None)], preview=False), (0, 0, 0))

    def test_expand_globs(self):
        (self.root / "User Data" / "Default" / "Cache").mkdir(parents=True)
        (self.root / "User Data" / "Profile 1" / "Cache").mkdir(parents=True)
        trovati = tools.expand([str(self.root / "User Data" / "*" / "Cache")])
        self.assertEqual(len(trovati), 2)


class FakeContext:
    anteprima = False

    def __init__(self):
        self.calls = []

    def modifica(self, descrizione):
        self.calls.append(descrizione)
        return not self.anteprima

    def scrivi(self, testo=""):
        pass

    def registra(self, testo):
        pass

    def comando(self, comando, validi=(0,)):
        self.calls.append(comando)
        return tools.Esito(tools.Stato.OK)

    @staticmethod
    def powershell(script, timeout=180):
        return ""


class Actions(unittest.TestCase):
    def test_power_plan_uses_known_guid(self):
        ctx = FakeContext()
        tools.set_power_plan(ctx, "high")
        self.assertIn(["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"], ctx.calls)

    def test_visual_effects_writes_registry(self):
        ctx = FakeContext()
        with mock.patch.object(tools, "write_dword") as scrivi:
            esito = tools.set_visual_effects(ctx, best_performance=True)
        scrivi.assert_called_once()
        self.assertEqual(scrivi.call_args[0][3], 2)
        self.assertEqual(esito.stato, tools.Stato.OK)

    def test_preview_writes_nothing(self):
        ctx = FakeContext()
        ctx.anteprima = True
        with mock.patch.object(tools, "write_dword") as scrivi:
            esito = tools.set_visual_effects(ctx, best_performance=True)
        scrivi.assert_not_called()
        self.assertEqual(esito.stato, tools.Stato.ANTEPRIMA)


if __name__ == "__main__":
    unittest.main()
