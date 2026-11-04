"""Tests for the Wi-Fi and Bluetooth scanners: netsh in English and Italian, security, channels, Bluetooth parsing and the API."""
import json
import unittest
from unittest import mock

from tests import test_api
from wmm.agent import radio

NETSH_EN = """
Interface name : Wi-Fi
There are 3 networks currently visible.

SSID 1 : Home
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 60:1b:52:0e:2d:fc
         Signal             : 81%
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 112
         Bss Load:
             Connected Stations:         6
             Channel Utilization:        11 (4 %)
    BSSID 2                 : 60:1b:52:0e:2d:f8
         Signal             : 80%
         Radio type         : 802.11ax
         Band               : 2.4 GHz
         Channel            : 12

SSID 2 : CoffeeShop
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 40%
         Radio type         : 802.11n
         Channel            : 6

SSID 3 :
    Network type            : Infrastructure
    Authentication          : WPA3-Personal
    Encryption              : GCMP
    BSSID 1                 : aa:bb:cc:dd:ee:02
         Signal             : 30%
         Channel            : 11
"""

NETSH_IT = """
SSID 1 : Casa
    Tipo di rete            : Infrastruttura
    Autenticazione          : WPA2-Personal
    Crittografia            : CCMP
    BSSID 1                 : 60:1b:52:0e:2d:fc
         Segnale            : 75%
         Tipo radio         : 802.11ac
         Banda              : 5 GHz
         Canale             : 36
"""

INTERFACE = """
    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX200 160MHz
    State                  : connected
    SSID                   : Home
    AP BSSID               : 60:1b:52:0e:2d:fc
    Rssi                   : -62
"""


class Wifi(unittest.TestCase):
    def test_parse_english_and_italian(self):
        reti = radio.parse_wifi(NETSH_EN)
        self.assertEqual([(r["ssid"], r["bssid"], r["band"], r["channel"]) for r in reti],
                         [("Home", "60:1B:52:0E:2D:FC", "5 GHz", 112), ("Home", "60:1B:52:0E:2D:F8", "2.4 GHz", 12),
                          ("CoffeeShop", "AA:BB:CC:DD:EE:01", "2.4 GHz", 6), ("", "AA:BB:CC:DD:EE:02", "2.4 GHz", 11)])
        self.assertEqual((reti[0]["signal"], reti[0]["stations"], reti[0]["utilization"], reti[0]["auth"]), (81, 6, 4, "WPA2-Personal"))
        it = radio.parse_wifi(NETSH_IT)[0]
        self.assertEqual((it["ssid"], it["signal"], it["channel"], it["auth"], it["radio"]), ("Casa", 75, 36, "WPA2-Personal", "802.11ac"))

    def test_interface_and_security(self):
        self.assertEqual(radio.parse_interface(INTERFACE), {"adapter": "Intel(R) Wi-Fi 6 AX200 160MHz", "ssid": "Home", "bssid": "60:1B:52:0E:2D:FC", "rssi": -62})
        self.assertEqual(radio.security("Open", "None")["level"], "risk")
        self.assertEqual(radio.security("Aperta", "Nessuna")["level"], "risk")
        self.assertEqual(radio.security("WPA-Personal", "TKIP")["level"], "review")
        self.assertEqual(radio.security("WPA3-Personal", "GCMP")["label"], "WPA3")
        self.assertEqual(radio.security("WPA2-Personal", "CCMP")["level"], "ok")
        self.assertEqual(radio.dbm(80), -60)

    def test_best_channel(self):
        reti = [{"band": "2.4 GHz", "channel": 1, "signal": 90}, {"band": "2.4 GHz", "channel": 2, "signal": 80}, {"band": "2.4 GHz", "channel": 11, "signal": 70},
                {"band": "5 GHz", "channel": 36, "signal": 50}, {"band": "5 GHz", "channel": 40, "signal": 50}]
        self.assertEqual(radio.best_channel(reti, "2.4 GHz"), 6)
        self.assertEqual(radio.best_channel(reti, "5 GHz"), 44)

    def test_full_scan_with_advice(self):
        uscite = {"networks": NETSH_EN, "interfaces": INTERFACE}
        finto = lambda argomenti, **k: mock.Mock(stdout=uscite[argomenti[3]])  # noqa: E731
        with mock.patch.object(radio, "trigger_wifi_scan", return_value=1), mock.patch.object(radio.subprocess, "run", side_effect=finto):
            r = radio.wifi_scan()
        self.assertTrue(r["networks"][0]["connected"])
        self.assertTrue(all(n["own"] for n in r["networks"][:2]))
        self.assertTrue(r["networks"][3]["hidden"])
        testi = " ".join(a["text"] for a in r["advice"])
        self.assertIn("channel 12 overlaps", testi)  # 2.4 GHz channel 12 is not 1, 6 or 11
        self.assertIn("CoffeeShop", testi)  # open network nearby

    def test_location_permission_is_explained(self):
        finto = lambda argomenti, **k: mock.Mock(stdout="Network shell commands need location permission to access WLAN information.")  # noqa: E731
        with mock.patch.object(radio, "trigger_wifi_scan", return_value=1), mock.patch.object(radio.subprocess, "run", side_effect=finto):
            r = radio.wifi_scan()
        self.assertIn("Location", r["error"])
        self.assertEqual(r["settings"], "ms-settings:privacy-location")


    def test_several_adapters_and_the_chosen_one(self):
        due = INTERFACE + """
    Name                   : Wi-Fi 2
    Description            : TP-Link USB
    State                  : disconnected
"""
        adattatori = radio.parse_interfaces(due)
        self.assertEqual([(a["name"], a["connected"], a["default"]) for a in adattatori], [("Wi-Fi", True, True), ("Wi-Fi 2", False, False)])
        self.assertEqual(adattatori[1]["adapter"], "TP-Link USB")
        comandi = []

        def finto(argomenti, **k):
            comandi.append(argomenti)
            return mock.Mock(stdout=NETSH_EN if argomenti[3] == "networks" else due)
        with mock.patch.object(radio, "trigger_wifi_scan", return_value=1) as scansione, mock.patch.object(radio.subprocess, "run", side_effect=finto):
            r = radio.wifi_scan(nome="Wi-Fi 2")
            self.assertEqual(scansione.call_args.kwargs["descrizione"], "TP-Link USB")
            self.assertEqual((r["interface"], r["connected"]), ("Wi-Fi 2", {"adapter": "TP-Link USB"}))
            self.assertIn("interface=Wi-Fi 2", comandi[-1])
            self.assertFalse(any(n["connected"] for n in r["networks"]))  # that adapter is not on a network
            self.assertEqual(radio.wifi_scan()["interface"], "Wi-Fi")  # the connected one by default
            with self.assertRaises(ValueError):
                radio.wifi_scan(nome="Gone")

    def test_bluetooth_radios_active_first(self):
        radio_ = radio.parse_radios(json.dumps([{"name": "Old dongle", "status": "Error"}, {"name": "Intel(R) Wireless Bluetooth(R)", "status": "OK"}]))
        self.assertEqual([(v["name"], v["active"], v["default"]) for v in radio_], [("Intel(R) Wireless Bluetooth(R)", True, True), ("Old dongle", False, False)])
        self.assertEqual(radio.parse_radios(json.dumps({"name": "Solo", "status": "OK"}))[0]["name"], "Solo")
        self.assertEqual(radio.parse_radios("not json"), [])


class Bluetooth(unittest.TestCase):
    def test_parse_kinds_distance_and_duplicates(self):
        dati = {"devices": [
            {"kind": "Classic", "name": "DualSense Wireless Controller", "address": "e8:47:3a:61:79:db", "paired": True, "connected": False, "rssi": -44, "category": "Input.Gaming"},
            {"kind": "Low Energy", "name": "Govee_H6046_1E7C", "address": "ce:f8:05:06:1e:7c", "paired": False, "connected": False, "rssi": -89, "category": ""},
            {"kind": "Low Energy", "name": "", "address": "6d:d1:72:26:ee:43", "paired": False, "connected": False, "rssi": -68, "category": ""},
            {"kind": "Low Energy", "name": "", "address": "6d:d1:72:26:ee:43", "paired": False, "connected": False, "rssi": -60, "category": ""},
            {"kind": "Classic", "name": "bad", "address": "", "paired": False, "connected": False, "rssi": None, "category": ""},
            {"kind": "Classic", "name": "Phone", "address": "3c:cd:40:73:03:06", "paired": True, "connected": True, "rssi": "<b>", "category": "Communication.Phone"}],
            "radio": {"name": "Intel(R) Wireless Bluetooth(R)", "status": "OK"}}
        r = radio.parse_bluetooth(json.dumps(dati))
        per = {d["address"]: d for d in r["devices"]}
        self.assertEqual(len(per), 4)  # no address: dropped; the same device twice: the stronger reading
        self.assertEqual(per["E8:47:3A:61:79:DB"]["kind"], "Game controller")
        self.assertEqual(per["CE:F8:05:06:1E:7C"]["kind"], "Smart light")
        self.assertEqual((per["6D:D1:72:26:EE:43"]["rssi"], per["6D:D1:72:26:EE:43"]["kind"]), (-60, "Unnamed device"))
        self.assertIsNone(per["3C:CD:40:73:03:06"]["rssi"])  # not a number: dropped
        self.assertEqual(r["devices"][0]["address"], "3C:CD:40:73:03:06")  # connected first
        self.assertEqual(radio.distance(-44), "very close (< 1 m)")
        self.assertEqual(radio.distance(-95), "far")

    def test_new_devices_after_the_first_scan(self):
        primo = radio.mark_new({"scanned": "2026-11-04T10:00:00", "devices": [{"address": "AA:00:00:00:00:01", "paired": False}]}, None)
        self.assertFalse(primo["devices"][0]["new"])
        secondo = radio.mark_new({"scanned": "2026-11-04T11:00:00", "devices": [{"address": "AA:00:00:00:00:01", "paired": False},
                                                                               {"address": "BB:00:00:00:00:02", "paired": False},
                                                                               {"address": "CC:00:00:00:00:03", "paired": True}]}, primo)
        self.assertEqual([d["new"] for d in secondo["devices"]], [False, True, False])
        self.assertEqual(secondo["devices"][0]["first_seen"], "2026-11-04T10:00:00")


class RadioApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_last_scan_and_new_scan(self):
        self.assertEqual(self.request("GET", "/api/v1/network/wifi")[1]["scanned"], None)
        with mock.patch.object(radio, "wifi_scan", return_value={"networks": [{"ssid": "Home"}], "scanned": "2026-11-04T10:00:00"}):
            stato, dati, _ = self.request("POST", "/api/v1/network/wifi/scan")
        self.assertEqual((stato, dati["networks"][0]["ssid"]), (200, "Home"))
        self.assertEqual(self.request("GET", "/api/v1/network/wifi")[1]["networks"][0]["ssid"], "Home")
        with mock.patch.object(radio, "bluetooth_scan", return_value={"devices": [], "scanned": "2026-11-04T10:00:00", "error": "off"}):
            stato, dati, _ = self.request("POST", "/api/v1/network/bluetooth/scan")
        self.assertEqual((stato, dati["error"]), (200, "off"))
        with mock.patch.object(radio, "wifi_scan", return_value={"networks": [], "scanned": "2026-11-04T10:00:00"}) as fatto:
            self.assertEqual(self.request("POST", "/api/v1/network/wifi/scan", {"interface": "Wi-Fi 2"})[0], 200)
        self.assertEqual(fatto.call_args.kwargs["nome"], "Wi-Fi 2")
        with mock.patch.object(radio, "wifi_scan", side_effect=ValueError("There is no Wi-Fi adapter called Gone.")):
            self.assertEqual(self.request("POST", "/api/v1/network/wifi/scan", {"interface": "Gone"})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/network/zigbee/scan")[0], 404)


if __name__ == "__main__":
    unittest.main()
