"""Tests for the network scanner: which networks, ARP in any language, makers, the device guess, new devices and the API."""
import json
import unittest
from unittest import mock

from tests import test_api
from wmm.agent import netscan

ARP_IT = """
Interfaccia: 192.168.1.5 --- 0x12
  Indirizzo Internet    Indirizzo fisico      Tipo
  192.168.1.1           60-1b-52-0e-2d-f0     dinamico
  192.168.1.8           00-17-88-b0-c7-b8     dinamico
  192.168.1.255         ff-ff-ff-ff-ff-ff     statico
  224.0.0.22            01-00-5e-00-00-16     statico
"""


class Parsing(unittest.TestCase):
    def test_networks_private_only_and_capped(self):
        testo = json.dumps([{"alias": "Wi-Fi", "ip": "192.168.1.5", "prefix": 24, "gateway": "192.168.1.1"},
                            {"alias": "Office", "ip": "10.20.30.40", "prefix": 16, "gateway": "10.20.0.1"},
                            {"alias": "Public", "ip": "8.8.8.8", "prefix": 24, "gateway": "8.8.8.1"},
                            {"alias": "APIPA", "ip": "169.254.10.10", "prefix": 16, "gateway": ""}])
        reti = netscan.parse_networks(testo)
        self.assertEqual([r["network"] for r in reti], ["192.168.1.0/24", "10.20.30.0/24"])
        self.assertEqual(netscan.parse_networks("not json"), [])

    def test_arp_in_any_language(self):
        self.assertEqual(netscan.parse_arp(ARP_IT), {"192.168.1.1": "60:1B:52:0E:2D:F0", "192.168.1.8": "00:17:88:B0:C7:B8"})

    def test_makers_and_random_macs(self):
        self.assertEqual(netscan.vendor("00:17:88:B0:C7:B8"), "Philips Hue (Signify)")
        self.assertIn("Random MAC", netscan.vendor("4E:AC:DE:B5:44:AD"))
        self.assertEqual(netscan.vendor("70:66:2A:C1:F9:BF"), "")

    def test_guess_and_risks(self):
        self.assertEqual(netscan.guess({"gateway": True, "ports": [80]}), "Router / gateway")
        self.assertEqual(netscan.guess({"ports": [9100, 80]}), "Printer")
        self.assertEqual(netscan.guess({"ports": [5000, 5001]}), "NAS")
        self.assertEqual(netscan.guess({"ports": [445, 135]}), "Windows PC")
        self.assertEqual(netscan.guess({"ports": [62078]}), "iPhone / iPad")
        self.assertEqual(netscan.guess({"ports": [], "name": "roborock-vacuum-a168.station"}), "Smart home device")
        self.assertEqual(netscan.guess({"ports": []}), "Unknown")
        self.assertEqual(len(netscan.risks({"ports": [23, 21, 5900, 3389]})), 4)
        self.assertEqual(netscan.risks({"ports": [3389], "this_pc": True}), [])

    def test_new_and_missing_devices(self):
        primo = netscan.merge_history({"scanned": "2026-11-04T10:00:00", "devices": [{"ip": "192.168.1.1", "mac": "AA:00:00:00:00:01", "name": "router"},
                                                                                    {"ip": "192.168.1.9", "mac": "AA:00:00:00:00:09", "name": "tv"}]}, None)
        self.assertFalse(any(d["new"] for d in primo["devices"]))  # the first scan is the baseline
        secondo = netscan.merge_history({"scanned": "2026-11-05T10:00:00", "devices": [{"ip": "192.168.1.1", "mac": "AA:00:00:00:00:01", "name": "router"},
                                                                                      {"ip": "192.168.1.30", "mac": "BB:00:00:00:00:30", "name": ""}]}, primo)
        self.assertEqual([d["new"] for d in secondo["devices"]], [False, True])
        self.assertEqual(secondo["devices"][0]["first_seen"], "2026-11-04T10:00:00")
        self.assertEqual([m["ip"] for m in secondo["missing"]], ["192.168.1.9"])

    def test_scan_marks_this_pc_and_the_gateway(self):
        reti = [{"alias": "LAN", "ip": "192.168.50.5", "gateway": "192.168.50.1", "network": "192.168.50.0/29"}]
        vivi = {"192.168.50.1": 2, "192.168.50.5": 0}
        with mock.patch.object(netscan, "ping", side_effect=lambda ip: vivi.get(ip)), \
                mock.patch.object(netscan, "arp_table", return_value={"192.168.50.1": "00:11:32:00:00:01", "192.168.50.3": "52:54:00:00:00:03"}), \
                mock.patch.object(netscan, "name_of", return_value=""), mock.patch.object(netscan, "open_ports", return_value=[]), \
                mock.patch.object(netscan, "web_title", return_value=""):
            r = netscan.scan(networks=reti)
        per_ip = {d["ip"]: d for d in r["devices"]}
        self.assertEqual(sorted(per_ip), ["192.168.50.1", "192.168.50.3", "192.168.50.5"])  # .3 answered ARP only
        self.assertEqual((per_ip["192.168.50.1"]["type"], per_ip["192.168.50.1"]["vendor"]), ("Router / gateway", "Synology"))
        self.assertEqual(per_ip["192.168.50.5"]["type"], "This PC")
        self.assertIsNone(per_ip["192.168.50.3"]["latency_ms"])


class ScannerApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_devices_scan_and_one_at_a_time(self):
        stato, dati, _ = self.request("GET", "/api/v1/network/devices")
        self.assertEqual((stato, dati["devices"], dati["scanned"]), (200, [], None))
        finto = {"networks": [], "devices": [{"ip": "192.168.1.1", "mac": "", "name": "r", "type": "Router / gateway"}], "scanned": "2026-11-04T10:00:00",
                 "seconds": 1.0, "addresses": 254}
        with mock.patch.object(netscan, "scan", return_value=finto):
            stato, dati, _ = self.request("POST", "/api/v1/network/scan")
        self.assertEqual((stato, len(dati["devices"])), (200, 1))
        self.assertEqual(self.request("GET", "/api/v1/network/devices")[1]["scanned"], "2026-11-04T10:00:00")
        self.agent._netscan_lock.acquire()
        try:
            self.assertEqual(self.request("POST", "/api/v1/network/scan")[0], 409)
        finally:
            self.agent._netscan_lock.release()


if __name__ == "__main__":
    unittest.main()
