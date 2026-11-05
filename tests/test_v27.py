"""Tests for 2.7: guided diagnosis, the wider undo journal, custom tools, the free-space verdict, connection log, suspicious
changes, known exploited vulnerabilities, disk and battery trends, signed remote runs and the Italian pages dictionary.
PowerShell, registry, powercfg, sc, network and HTTP are replaced by fakes; the fleet test talks to a server on 127.0.0.1."""
import json
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import wmm
from ottimizza_pc import Esito, Stato
from wmm.agent import actions, custom_tools, diagnose, drift, fleet, jobs, kev, notify, trends, undo, verify, watch
from wmm.agent.store import Store
from tests import test_api
from tests.test_disk_tools import FakeContext

ROOT = Path(wmm.ROOT)


class GuidedDiagnosis(unittest.TestCase):
    def test_needed_and_fine_from_the_checks(self):
        def runner(script):
            if "NetConnectionProfile" in script and "NetworkCategory" in script:
                return "Casa: Public"
            if "FirewallRule" in script:
                return "Discovery rules on, FDResPub Stopped"
            return "Internet, DNS ok"
        r = diagnose.diagnose("lan_visibility", runner)
        stati = {p["action_id"]: p["state"] for p in r["steps"]}
        self.assertEqual(stati["network.profile_private"], "needed")
        self.assertEqual(stati["network.discovery_on"], "needed")
        self.assertEqual(stati["network.flush_dns"], "fine")
        self.assertEqual(r["recommended"], ["network.profile_private", "network.discovery_on"])
        self.assertTrue(r["reports"])

    def test_each_script_is_read_once(self):
        letti = []
        diagnose.diagnose("no_internet", lambda s: letti.append(s) or "Internet, DNS ok")
        self.assertEqual(len(letti), len(set(letti)))

    def test_unreadable_and_manual_steps(self):
        r = diagnose.diagnose("start_menu", lambda s: None)
        self.assertTrue(all(p["state"] in ("unknown", "manual") for p in r["steps"]))
        self.assertEqual(r["recommended"], [])
        with self.assertRaises(KeyError):
            diagnose.diagnose("nope")


class WiderUndo(unittest.TestCase):
    ITALIAN = """    Indice impostazione minima possibile: 0x00000000
    Indice impostazione massima possibile: 0x00000064
    Incremento impostazione possibile: 0x00000001
  Indice impostazione corrente alimentazione CA: 0x00000005
  Indice impostazione corrente alimentazione CC: 0x00000032
"""

    def test_power_query_in_any_language(self):
        self.assertEqual(undo.parse_power_query(self.ITALIAN), [5, 50])
        self.assertIsNone(undo.parse_power_query("nothing"))

    def test_power_plan_and_service_round_trip(self):
        stato = {"power": "  Current AC Power Setting Index: 0x00000005\n  Current DC Power Setting Index: 0x00000005\n",
                 "plan": "GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)", "sc": "        START_TYPE         : 2   AUTO_START"}
        comandi = []

        def run(c):
            comandi.append(c)
            if c[:2] == ["powercfg", "/query"]:
                return stato["power"]
            if c[:2] == ["powercfg", "/getactivescheme"]:
                return stato["plan"]
            if c[:2] == ["sc", "qc"]:
                return stato["sc"]
            return ""
        with mock.patch.object(undo, "RUN", side_effect=run):
            giornale = undo.begin()
            undo.before_power("sub", "set")
            undo.before_plan()
            undo.declare("services.search_manual", giornale)
            undo.end()
            stato.update(power="  x: 0x00000064\n  y: 0x00000064\n", plan="GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", sc="START_TYPE : 3   DEMAND_START")
            cambiati = undo.changed(giornale.with_current())
            self.assertEqual({v["kind"] for v in cambiati}, {"power", "plan", "service"})
            fatti, errori = undo.restore(cambiati)
        self.assertEqual((fatti, errori), (3, []))
        self.assertIn(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "sub", "set", "5"], comandi)
        self.assertIn(["powercfg", "/setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"], comandi)
        self.assertIn(["sc", "config", "WSearch", "start=", "auto"], comandi)

    def test_bad_entries_are_refused(self):
        fatti, errori = undo.restore([{"kind": "service", "name": "x & del", "value": "auto", "existed": True},
                                      {"kind": "plan", "value": "not-a-guid", "existed": True}])
        self.assertEqual(fatti, 0)
        self.assertEqual(len(errori), 2)

    def test_power_settings_helper_feeds_the_journal(self):
        from wmm.agent import tools
        ctx = FakeContext()
        with mock.patch.object(undo, "RUN", return_value="a: 0x1\nb: 0x2\n"), mock.patch.object(tools.op, "comandi_in_serie", return_value=Esito(Stato.OK, "")):
            giornale = undo.begin()
            tools.power_settings(ctx, [("sub", "set", 1)])
            undo.end()
        self.assertEqual(giornale.entries[0]["kind"], "power")
        self.assertEqual(giornale.entries[0]["value"], [1, 2])

    def test_declared_services_belong_to_real_fixes(self):
        for action_id in undo.SERVICE_TOUCHES:
            self.assertIn(action_id, actions.CATALOG)


class MoreChecks(unittest.TestCase):
    def test_space_verdict(self):
        letture = iter([10 * 1024 ** 3, 10 * 1024 ** 3 + 50 * 1024 ** 2])
        sonda = verify.Probe("cleanup.temp", space=lambda: next(letture))
        self.assertEqual(sonda.finish()["verdict"], "freed")
        letture = iter([5, 5])
        self.assertEqual(verify.Probe("cleanup.temp", space=lambda: next(letture)).finish()["verdict"], "nothing_freed")

    def test_space_fixes_exist_and_coverage_grew(self):
        self.assertEqual([a for a in verify.SPACE_FIXES if a not in actions.CATALOG], [])
        self.assertGreaterEqual(len(verify.CHECKS), 80)


class CustomTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        custom_tools.register(self.dir / "none")  # takes the custom tools out of the shared catalog
        self.tmp.cleanup()

    def test_validation(self):
        for dati in ({}, {"title": "x"}, {"title": "x", "script": "a" * (custom_tools.MAX_SCRIPT + 1)}, {"title": "x" * 81, "script": "a"}):
            with self.assertRaises(custom_tools.CustomToolError):
                custom_tools.validate(dati)
        voce = custom_tools.validate({"title": "Report", "script": "Get-Date", "kind": "report", "risk": "high", "undo": "x"})
        self.assertEqual((voce["risk"], voce["undo"]), ("safe", ""))

    def test_saved_tool_joins_catalog_and_checks(self):
        voce = custom_tools.save(self.dir, {"title": "Mio", "script": "Get-Date", "check": "'ok'", "healthy": "ok", "area": "network", "risk": "safe"})
        azione = actions.CATALOG["custom." + voce["id"]]
        self.assertEqual((azione.area, azione.risk, azione.kind), ("network", "safe", "fix"))
        self.assertTrue(verify.CHECKS["custom." + voce["id"]].ok("ok"))
        custom_tools.save(self.dir, {"title": "Mio 2", "script": "Get-Date"}, voce["id"])
        self.assertEqual(actions.CATALOG["custom." + voce["id"]].title, "Mio 2")
        custom_tools.delete(self.dir, voce["id"])
        self.assertNotIn("custom." + voce["id"], actions.CATALOG)
        with self.assertRaises(KeyError):
            custom_tools.delete(self.dir, voce["id"])

    def test_undo_script_through_the_runner(self):
        voce = custom_tools.save(self.dir, {"title": "Con annullo", "script": "x", "undo": "Write-Output undo", "risk": "safe"})
        store = Store(self.dir / "db.sqlite")
        eseguiti = []
        with mock.patch.object(jobs, "free_bytes", return_value=0), mock.patch.object(jobs.op.Contesto, "registra"), \
                mock.patch.object(custom_tools, "RUN_SCRIPT", side_effect=eseguiti.append), \
                mock.patch("wmm.agent.core.JobContext.comando", return_value=Esito(Stato.OK, "")):
            manager = jobs.JobManager(store, "PC")
            r = manager.run_sync(["custom." + voce["id"]], "manual", True)["results"][0]
            self.assertEqual(r["undo_count"], 1)
            manager.undo_run(r["run_id"])
        self.assertEqual(eseguiti, ["Write-Output undo"])


class ConnectionLog(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(watch.classify({"gateway": "192.168.1.1", "gateway_ms": None, "internet_ms": None, "dns_ms": None}), "local")
        self.assertEqual(watch.classify({"gateway": "192.168.1.1", "gateway_ms": 1, "internet_ms": None, "dns_ms": 5}), "provider")
        self.assertEqual(watch.classify({"gateway": "g", "gateway_ms": 1, "internet_ms": 8, "dns_ms": None}), "dns")
        self.assertEqual(watch.classify({"gateway": "g", "gateway_ms": 1, "internet_ms": 300, "dns_ms": 5}), "slow")
        self.assertEqual(watch.classify({"gateway": "g", "gateway_ms": 1, "internet_ms": 8, "dns_ms": 5}), "ok")

    def test_outages_are_grouped_and_alerted_when_back(self):
        with tempfile.TemporaryDirectory() as cartella:
            d = Path(cartella)
            base = datetime(2026, 11, 5, 10, 0)

            def campione(minuti, gw=1, net=8):
                return {"t": (base + timedelta(minutes=minuti)).isoformat(), "gateway": "g", "gateway_ms": gw, "internet_ms": net, "dns_ms": 4 if net else None}
            for i, ms in enumerate((8, None, None, 9)):
                watch.record_connection(d, campione(5 * i, net=ms))
            storia = watch.connection_history(d)
            self.assertEqual(len(storia["outages"]), 1)
            self.assertEqual((storia["outages"][0]["cause"], storia["outages"][0]["samples"]), ("provider", 2))
            with mock.patch.object(watch, "connection_sample", return_value=campione(20)), mock.patch.object(notify, "safe_event") as evento:
                watch.connection_watch(FakeContext(), d)
            self.assertFalse(evento.called)  # that outage ended two readings ago
            watch.record_connection(d, campione(25, gw=None, net=None))
            with mock.patch.object(watch, "connection_sample", return_value=campione(30)), mock.patch.object(notify, "safe_event") as evento:
                watch.connection_watch(FakeContext(), d)
            self.assertEqual(evento.call_args[0][1], "connection_down")


class SuspiciousChanges(unittest.TestCase):
    def snap(self, **voci):
        base = {c: {} for c in drift.CATEGORIES}
        base.update(voci)
        return lambda: json.dumps(base)

    def test_baseline_then_changes(self):
        with tempfile.TemporaryDirectory() as cartella:
            d = Path(cartella)
            primo = drift.check(d, self.snap(run_keys={"HKCU\\Run\\A": "a.exe"}, admins={"PC\\me": "Local"}))
            self.assertTrue(primo["first"])
            secondo = drift.check(d, self.snap(run_keys={"HKCU\\Run\\A": "a2.exe", "HKCU\\Run\\Evil": "x.exe"}, admins={"PC\\me": "Local"}))
            self.assertEqual([v["item"] for v in secondo["added"]], ["HKCU\\Run\\Evil"])
            self.assertEqual([v["item"] for v in secondo["changed"]], ["HKCU\\Run\\A"])
            # A category that comes back empty (could not be read) is not "everything removed", and keeps its content.
            terzo = drift.check(d, self.snap(run_keys={"HKCU\\Run\\A": "a2.exe", "HKCU\\Run\\Evil": "x.exe"}))
            self.assertEqual(terzo["total"], 0)
            self.assertEqual(drift.last(d)["counts"]["admins"], 1)

    def test_watch_alerts_on_new_items(self):
        with tempfile.TemporaryDirectory() as cartella:
            d = Path(cartella)
            drift.check(d, self.snap(tasks={"\\A": "a"}))
            with mock.patch.object(drift, "snapshot", return_value=drift.snapshot(self.snap(tasks={"\\A": "a", "\\B": "b"}))), \
                    mock.patch.object(notify, "safe_event") as evento:
                esito = drift.drift_watch(FakeContext(), d)
        self.assertEqual(esito.stato, Stato.AVVISO)
        self.assertEqual(evento.call_args[0][1], "config_changed")

    def test_snapshot_script_parses(self):
        with tempfile.TemporaryDirectory() as cartella:
            sorgente = Path(cartella) / "snapshot.ps1"
            sorgente.write_text(drift.SCRIPT, encoding="utf-8-sig")
            script = Path(cartella) / "p.ps1"
            script.write_text(f"$x=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{sorgente}', [ref]$null, [ref]$x); "
                              "if ($x) { $x | ForEach-Object { $_.Message } }", encoding="utf-8-sig")
            uscita = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(uscita.stdout.strip(), "")


class KnownExploited(unittest.TestCase):
    FEED = {"catalogVersion": "2026.11.04", "vulnerabilities": [
        {"cveID": "CVE-2024-1", "vendorProject": "TP-Link", "product": "Archer C5", "vulnerabilityName": "TP-Link Archer C5 RCE", "knownRansomwareCampaignUse": "Known"},
        {"cveID": "CVE-2024-2", "vendorProject": "Synology", "product": "DiskStation Manager (DSM)", "vulnerabilityName": "DSM flaw"},
        {"cveID": "CVE-2024-3", "vendorProject": "Microsoft", "product": "Windows", "vulnerabilityName": "Windows flaw"}]}

    def test_maker_and_product_must_both_match(self):
        dispositivi = [{"ip": "192.168.1.1", "vendor": "TP-LINK TECHNOLOGIES", "title": "Archer C5 v4"},
                       {"ip": "192.168.1.2", "vendor": "TP-LINK TECHNOLOGIES", "title": "Deco M4"},
                       {"ip": "192.168.1.3", "vendor": "Synology Incorporated", "name": "nas", "title": "Synology DiskStation"}]
        trovati = kev.match(dispositivi, self.FEED["vulnerabilities"])
        self.assertEqual([t["ip"] for t in trovati], ["192.168.1.1"])
        self.assertTrue(trovati[0]["ransomware"])

    def test_catalog_is_cached(self):
        chiamate = []
        with tempfile.TemporaryDirectory() as cartella:
            def fetch():
                chiamate.append(1)
                return json.dumps(self.FEED).encode()
            kev.catalog(Path(cartella), fetch)
            kev.catalog(Path(cartella), fetch)
            self.assertEqual(len(chiamate), 1)
            esito = kev.check(Path(cartella), [{"ip": "x", "vendor": "TP-Link", "model": "Archer C5"}], fetch)
        self.assertEqual(esito["catalog_entries"], 3)
        self.assertEqual(len(esito["found"]), 1)


class Trends(unittest.TestCase):
    def test_one_reading_a_day_and_forecasts(self):
        with tempfile.TemporaryDirectory() as cartella:
            d = Path(cartella)
            inizio = datetime(2026, 1, 1, 9)
            for giorno in range(0, 60, 6):
                trends.record(d, {"disks": [{"id": "S1", "name": "SSD", "media": "SSD", "health": "Healthy", "wear": 10 + giorno / 6, "temperature": 40,
                                             "read_errors": 0, "write_errors": 0, "hours": 1000}],
                                  "batteries": [{"id": "battery0", "name": "B", "full": 50 - giorno / 6, "design": 50, "capacity_pct": 100 - giorno / 3}]},
                              inizio + timedelta(days=giorno))
            trends.record(d, {"disks": [], "batteries": []}, inizio + timedelta(days=54, hours=3))  # the same day: replaces that reading
            self.assertEqual(len(trends.history(d)), 10)
            trends.record(d, {"disks": [{"id": "S1", "name": "SSD", "media": "SSD", "health": "Healthy", "wear": 20, "temperature": 40, "read_errors": 3,
                                         "write_errors": 0, "hours": 1100}],
                              "batteries": [{"id": "battery0", "name": "B", "full": 40, "design": 50, "capacity_pct": 80}]}, inizio + timedelta(days=60))
            t = trends.trends(d)
        disco, batteria = t["disks"][0], t["batteries"][0]
        self.assertGreater(disco["wear_per_month"], 0)
        self.assertTrue(disco["worn_out"])
        self.assertEqual(disco["new_errors"], 3)
        self.assertTrue(batteria["below_limit"])

    def test_read_parses_powershell_output(self):
        uscita = json.dumps({"disks": {"id": "X", "name": "Disk", "wear": 3, "temperature": 35}, "batteries": [{"id": "battery0", "full": 40000, "design": 50000}]})
        dati = trends.read(lambda: uscita)
        self.assertEqual(dati["disks"][0]["wear"], 3.0)
        self.assertEqual(dati["batteries"][0]["capacity_pct"], 80.0)


class RemoteRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sharing = fleet.Fleet(Path(self.tmp.name) / "a.json")
        self.key = self.sharing.new_key()
        self.sharing.set_share(True, 8766, "safe")
        self.started = []
        risultati = [{"action_id": "network.flush_dns", "status": "ok", "note": "<b>x</b>", "verify": None}]
        self.server = fleet.summary_server(self.sharing, 0, lambda: {"hostname": "A"},
                                           {"start": lambda ids: self.started.append(ids) or "ab" * 16,
                                            "status": lambda job: {"id": job, "active": False, "done": 1, "total": 1, "results": risultati}})
        self.port = self.server.server_address[1]
        self.console = fleet.Fleet(Path(self.tmp.name) / "b.json")
        self.pc = self.console.add("A", "127.0.0.1", self.port, self.key)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_allowed_levels(self):
        sicuro, rischioso, report = actions.CATALOG["network.flush_dns"], actions.CATALOG["network.reset"], actions.CATALOG["network.speed_test"]
        self.assertFalse(fleet.allowed("off", report))
        self.assertTrue(fleet.allowed("reports", report))
        self.assertFalse(fleet.allowed("reports", sicuro))
        self.assertTrue(fleet.allowed("safe", sicuro))
        self.assertFalse(fleet.allowed("safe", rischioso))

    def test_signed_run_and_status(self):
        risposta = self.console.run_remote(self.pc["id"], ["network.flush_dns", "network.speed_test"])
        self.assertEqual(self.started, [["network.flush_dns", "network.speed_test"]])
        stato = self.console.run_status(self.pc["id"], risposta["id"])
        self.assertEqual(stato["results"][0]["status"], "ok")

    def test_risky_tools_and_off_level_are_refused(self):
        with self.assertRaises(fleet.FleetError):
            self.console.run_remote(self.pc["id"], ["network.reset"])
        self.sharing.set_share(True, 8766, "off")
        with self.assertRaises(fleet.FleetError):
            self.console.run_remote(self.pc["id"], ["network.flush_dns"])
        self.assertEqual(self.started, [])

    def test_replay_wrong_key_and_old_requests_are_refused(self):
        segreto = fleet.key_hash(self.key)
        adesso = str(int(time.time()))
        firma = fleet.signature(segreto, "POST", fleet.RUN_PATH, adesso, "n" * 16, b"{}")
        self.assertTrue(self.sharing.accepts_signed("POST", fleet.RUN_PATH, adesso, "n" * 16, b"{}", firma))
        self.assertFalse(self.sharing.accepts_signed("POST", fleet.RUN_PATH, adesso, "n" * 16, b"{}", firma))  # replay
        vecchio = str(int(time.time()) - 600)
        self.assertFalse(self.sharing.accepts_signed("POST", fleet.RUN_PATH, vecchio, "m" * 16, b"{}",
                                                     fleet.signature(segreto, "POST", fleet.RUN_PATH, vecchio, "m" * 16, b"{}")))
        altra = fleet.signature(fleet.key_hash("wrong-key-wrong-key"), "POST", fleet.RUN_PATH, adesso, "k" * 16, b"{}")
        self.assertFalse(self.sharing.accepts_signed("POST", fleet.RUN_PATH, adesso, "k" * 16, b"{}", altra))

    def test_summary_is_signed_and_the_clear_key_only_works_with_remote_runs_off(self):
        import urllib.error
        import urllib.request
        self.assertEqual(fleet.fetch_summary("127.0.0.1", self.port, self.key)["hostname"], "A")
        richiesta = urllib.request.Request(f"http://127.0.0.1:{self.port}{fleet.SUMMARY_PATH}", headers={fleet.KEY_HEADER: self.key})
        with self.assertRaises(urllib.error.HTTPError):  # remote runs are on: a key seen on the network is not enough
            urllib.request.urlopen(richiesta, timeout=5)
        self.sharing.set_share(True, 8766, "off")
        with urllib.request.urlopen(richiesta, timeout=5) as risposta:  # consoles before 2.7, read-only
            self.assertEqual(risposta.status, 200)

    def test_custom_tools_never_run_remotely(self):
        finto = actions.Action("custom.abcd1234", "network", "Mine", "", "safe", 0.1, lambda ctx: None, "", "report")
        self.assertFalse(fleet.allowed("safe", finto))

    def test_remote_results_are_cleaned(self):
        pulito = fleet.clean_run({"id": "x" * 100, "active": "yes", "results": [{"action_id": 5, "status": "ok", "verify": "bad", "extra": 1}] * 80})
        self.assertEqual(len(pulito["id"]), 40)
        self.assertEqual(len(pulito["results"]), 50)
        self.assertIsNone(pulito["results"][0]["verify"])


class ItalianPages(unittest.TestCase):
    def pages(self):
        testo = (ROOT / "wmm/web/js/i18n_pages.js").read_text(encoding="utf-8")
        return json.loads(testo.split("window.I18N_PAGES = ", 1)[1].rstrip().rstrip(";"))

    def test_dictionary_loads_before_i18n(self):
        html = (ROOT / "wmm/web/index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("i18n_pages.js"), html.index("/i18n.js"))
        voci = self.pages()
        self.assertGreater(len(voci), 1000)
        self.assertEqual([k for k, v in voci.items() if not v.strip()], [])

    def test_check_labels_are_translated(self):
        self.assertEqual(sorted({c.label for c in verify.CHECKS.values()} - set(self.pages())), [])


class V27Api(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_diagnose_route(self):
        with mock.patch.object(verify, "run_script", return_value="Internet, DNS ok"):
            stato, dati, _ = self.request("POST", "/api/v1/symptoms/no_internet/diagnose")
        self.assertEqual(stato, 200)
        self.assertTrue(all(p["state"] == "fine" for p in dati["steps"]))
        stato, _, _ = self.request("POST", "/api/v1/symptoms/nope_nope/diagnose")
        self.assertEqual(stato, 404)

    def test_custom_tools_routes(self):
        stato, voce, _ = self.request("POST", "/api/v1/custom-tools", {"title": "T", "script": "Get-Date"})
        self.assertEqual(stato, 201)
        _, elenco, _ = self.request("GET", "/api/v1/actions")
        self.assertIn("custom." + voce["id"], {a["id"] for a in elenco["actions"]})
        stato, _, _ = self.request("POST", "/api/v1/custom-tools", {"title": ""})
        self.assertEqual(stato, 400)
        stato, _, _ = self.request("DELETE", "/api/v1/custom-tools/" + voce["id"])
        self.assertEqual(stato, 200)

    def test_read_routes_start_empty(self):
        for path, chiave in (("/api/v1/network/connection", "samples"), ("/api/v1/security/drift", "history"), ("/api/v1/hardware/trends", "disks")):
            stato, dati, _ = self.request("GET", path)
            self.assertEqual(stato, 200, path)
            self.assertEqual(dati[chiave], [], path)

    def test_fleet_share_accepts_the_remote_level(self):
        self.request("POST", "/api/v1/fleet/share/key")
        with mock.patch.object(fleet, "summary_server"):
            stato, dati, _ = self.request("PUT", "/api/v1/fleet/share", {"enabled": True, "port": 8799, "remote_runs": "reports"})
            self.assertEqual((stato, dati["remote_runs"]), (200, "reports"))
            stato, _, _ = self.request("PUT", "/api/v1/fleet/share", {"enabled": True, "port": 8799, "remote_runs": "everything"})
        self.assertEqual(stato, 400)


if __name__ == "__main__":
    unittest.main()
