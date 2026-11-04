"""Tests for the PCs of the network: LAN-only addresses, the key kept as a hash, the read-only summary server and the API."""
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests import test_api
from wmm.agent import fleet


class Addresses(unittest.TestCase):
    def test_only_local_network_addresses(self):
        self.assertEqual(fleet.lan_address("127.0.0.1"), "127.0.0.1")
        self.assertEqual(fleet.lan_address("192.168.1.20"), "192.168.1.20")
        for fuori in ("8.8.8.8", "1.1.1.1", "http://192.168.1.2", "192.168.1.2:80", "a b", "", "224.0.0.1"):
            with self.assertRaises(fleet.FleetError, msg=fuori):
                fleet.lan_address(fuori)


class Sharing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = fleet.for_data_dir(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_is_kept_only_as_a_hash(self):
        with self.assertRaises(fleet.FleetError):
            self.f.set_share(True, 8766)  # no key yet
        chiave = self.f.new_key()
        self.assertNotIn(chiave, self.f.path.read_text(encoding="utf-8"))
        self.assertTrue(self.f.accepts(chiave))
        self.assertFalse(self.f.accepts(chiave + "x"))
        self.assertFalse(self.f.accepts(""))
        self.assertTrue(self.f.set_share(True, 9000)["enabled"])
        for porta in (80, 70000, "abc"):
            with self.assertRaises(fleet.FleetError):
                self.f.set_share(True, porta)

    def test_summary_server_answers_only_with_the_key_and_only_reads(self):
        chiave = self.f.new_key()
        server = fleet.summary_server(self.f, 0, lambda: {"hostname": "TEST-PC", "overall": 88, "version": "<img src=x onerror=alert(1)>" * 5,
                                                          "open_issues": "<b>3</b>", "extra": "dropped"})
        porta = server.server_address[1]
        try:
            riassunto = fleet.fetch_summary("127.0.0.1", porta, chiave)
            self.assertEqual((riassunto["hostname"], riassunto["overall"]), ("TEST-PC", 88))
            # Another PC is not trusted: wrong types are dropped, text is cut, unknown fields never pass.
            self.assertIsNone(riassunto["open_issues"])
            self.assertEqual(len(riassunto["version"]), 20)
            self.assertNotIn("extra", riassunto)
            with self.assertRaisesRegex(fleet.FleetError, "wrong key"):
                fleet.fetch_summary("127.0.0.1", porta, "not-the-key-1234567")
            richiesta = urllib.request.Request(f"http://127.0.0.1:{porta}{fleet.SUMMARY_PATH}", data=b"{}", method="POST",
                                               headers={fleet.KEY_HEADER: chiave})
            with self.assertRaises(urllib.error.HTTPError) as errore:
                urllib.request.urlopen(richiesta, timeout=5)
            self.assertEqual(errore.exception.code, 405)
            altro = urllib.request.Request(f"http://127.0.0.1:{porta}/api/v1/agent/info", headers={fleet.KEY_HEADER: chiave})
            with self.assertRaises(urllib.error.HTTPError) as errore:
                urllib.request.urlopen(altro, timeout=5)
            self.assertEqual(errore.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_pcs_list_and_gather(self):
        with self.assertRaises(fleet.FleetError):
            self.f.add("Office", "8.8.8.8", 8766, "k" * 32)
        with self.assertRaises(fleet.FleetError):
            self.f.add("Office", "127.0.0.1", 8766, "short")
        uno = self.f.add("Office", "127.0.0.1", 8766, "k" * 32)
        self.assertNotIn("k" * 32, self.f.path.read_text(encoding="utf-8"))  # the key is encrypted
        self.f.add("Lab", "127.0.0.2", 8766, "j" * 32)

        def finto(indirizzo, porta, chiave):
            if indirizzo == "127.0.0.2":
                raise fleet.FleetError("not reachable")
            return {"hostname": "OFFICE", "key_seen": chiave == "k" * 32}
        righe = {r["name"]: r for r in self.f.gather(finto)}
        self.assertEqual((righe["Office"]["status"], righe["Office"]["summary"]["key_seen"]), ("online", True))
        self.assertEqual((righe["Lab"]["status"], righe["Lab"]["error"]), ("offline", "not reachable"))
        self.assertTrue(self.f.remove(uno["id"]))
        self.assertFalse(self.f.remove(uno["id"]))


class FleetApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    request = test_api.ApiTests.request
    admin = True

    def tearDown(self):
        # Stop the sharing server before the shared tear-down removes the data folder.
        self.agent.fleet.set_share(False, None)
        self.agent.start_fleet_share()
        test_api.ApiTests.tearDown(self)

    def test_view_add_share_and_remove(self):
        stato, dati, _ = self.request("GET", "/api/v1/fleet")
        self.assertEqual((stato, dati["pcs"], dati["share"]["enabled"]), (200, [], False))
        self.assertIn("overall", dati["this_pc"])
        self.assertEqual(self.request("POST", "/api/v1/fleet/pcs", {"name": "X", "address": "8.8.8.8", "key": "k" * 32})[0], 400)
        stato, pc, _ = self.request("POST", "/api/v1/fleet/pcs", {"name": "X", "address": "127.0.0.1", "port": 1, "key": "k" * 32})
        self.assertEqual(stato, 201)
        stato, chiave, _ = self.request("POST", "/api/v1/fleet/share/key")
        self.assertEqual(stato, 200)
        stato, condivisione, _ = self.request("PUT", "/api/v1/fleet/share", {"enabled": True, "port": 18766})
        self.assertEqual((stato, condivisione["running"]), (200, True))
        riassunto = fleet.fetch_summary("127.0.0.1", 18766, chiave["key"])
        self.assertEqual(riassunto["machine_id"], self.agent.machine_id)
        self.assertNotIn("token", json.dumps(riassunto).lower())
        self.assertEqual(self.request("DELETE", f"/api/v1/fleet/pcs/{pc['id']}")[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/v1/fleet/pcs/{pc['id']}")[0], 404)

    def test_sharing_is_refused_in_preview(self):
        self.agent.preview = True
        self.assertEqual(self.request("PUT", "/api/v1/fleet/share", {"enabled": True, "port": 18767})[0], 409)

    def test_firewall_rule_is_a_logged_change(self):
        with mock.patch.object(fleet, "firewall_rule", return_value={"rule": "x", "port": 8766}) as regola:
            self.assertEqual(self.request("POST", "/api/v1/fleet/share/firewall")[0], 200)
            regola.assert_called_once_with(8766)


if __name__ == "__main__":
    unittest.main()
