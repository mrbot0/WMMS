"""Tests for the HTTP API (collectors and schtasks mocked, temporary data folder)."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import collectors, inventory
from wmm.server import api

PERFORMANCE = {"memory": {"total_gb": 16, "load_pct": 40, "commit_pct": 40}, "power": {"plan": "saver"},
               "pagefile": {"automatic": True, "files": []}, "uptime_hours": 3, "errors": []}
STARTUP = {"items": [{"id": "0123456789abcdef", "name": "OneDrive", "command": "x", "location": "Registry (current user)",
                      "scope": "HKCU", "kind": "Run", "enabled": True}], "apps": [], "tasks": [], "errors": []}

SYSTEM = {
    "admin": True, "os": {"name": "Windows 11", "cpu": "CPU", "bios_age_days": 100, "uptime_hours": 3},
    "memory": {"free_gb": 8, "total_gb": 16}, "processes": [], "gpu": {},
    "disks": [{"name": "SSD", "media": "SSD", "health": "Healthy", "wear": 1, "read_errors": 0}],
    "volumes": [{"letter": "C", "free_gb": 200.0, "total_gb": 400.0, "health": "Healthy"}],
    "stability": {"unexpected_shutdowns": 0, "whea": 0, "disk_errors": 0},
    "security": {"defender": True, "firewall_off": False, "signature_age_days": 0},
    "reboot_pending": False, "updates": [], "errors": [],
}
CLEANUP = {"categories": [{"id": "user_temp", "name": "User temp", "bytes": 3 * 1024 ** 3, "files": 10}],
           "recoverable_bytes": 3 * 1024 ** 3, "volumes": SYSTEM["volumes"], "errors": []}
SERVICES = {"totals": {"total": 1, "auto": 1, "manual": 0, "disabled": 0, "running": 1, "stopped": 0},
            "managed": [{"name": "DiagTrack", "group": "safe", "start": "auto", "running": True}],
            "protected_present": 0, "startup": [], "backup_count": 0, "errors": []}


class ApiTests(unittest.TestCase):
    admin = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(collectors, "collect_system", return_value=dict(SYSTEM)),
            mock.patch.object(collectors, "collect_cleanup", return_value=dict(CLEANUP)),
            mock.patch.object(collectors, "collect_services", return_value=dict(SERVICES)),
            mock.patch.object(api.scheduler, "register"),
            mock.patch.object(api.scheduler, "unregister"),
            mock.patch.object(api.scheduler, "sync_state", return_value={}),
            mock.patch.object(api.scheduler, "unprotected_paths", return_value=[r"C:\Users\x\Desktop\wmm.py"]),
            mock.patch.object(inventory, "collect_performance", return_value=dict(PERFORMANCE)),
            mock.patch.object(inventory, "collect_storage", return_value={"categories": [], "volumes": [], "errors": []}),
            mock.patch.object(inventory, "collect_network", side_effect=AssertionError("network must not be scanned")),
            mock.patch.object(inventory, "collect_startup", return_value=dict(STARTUP)),
            mock.patch.object(inventory, "collect_security", return_value={"defender": {}, "restore_points": [], "errors": []}),
            mock.patch.object(inventory, "collect_updates", return_value={"pending": [], "errors": []}),
            mock.patch.object(inventory, "startup_items", return_value=STARTUP["items"]),
            mock.patch.object(inventory, "collect_events", return_value=({"total": 0, "top": []}, [])),
            mock.patch.object(inventory, "set_startup_enabled"),
        ]
        for patch in self.patches:
            patch.start()
        self.agent = api.Agent(Path(self.tmp.name), preview=False, admin=self.admin)
        self.server = api.make_server(self.agent, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def request(self, method, path, body=None, token=True, headers=None):
        connessione = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        intestazioni = {"Content-Type": "application/json"}
        if token:
            intestazioni["X-WMM-Token"] = self.agent.token
        intestazioni.update(headers or {})
        connessione.request(method, path, body=json.dumps(body) if body is not None else None, headers=intestazioni)
        risposta = connessione.getresponse()
        dati = risposta.read()
        connessione.close()
        tipo = risposta.getheader("Content-Type", "")
        return risposta.status, (json.loads(dati) if "json" in tipo else dati.decode("utf-8", "replace")), risposta

    def test_info(self):
        stato, dati, _ = self.request("GET", "/api/v1/agent/info")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["name"], "Windows Maintenance Manager")
        self.assertEqual(dati["machine_id"], self.agent.machine_id)

    def test_post_without_token_403(self):
        stato, _, _ = self.request("POST", "/api/v1/runs", {"actions": ["cleanup.temp"]}, token=False)
        self.assertEqual(stato, 403)

    def test_foreign_host_403(self):
        stato, _, _ = self.request("GET", "/api/v1/agent/info", headers={"Host": "evil.example"})
        self.assertEqual(stato, 403)

    def test_foreign_origin_403(self):
        stato, _, _ = self.request("POST", "/api/v1/runs", {"actions": ["cleanup.temp"]}, headers={"Origin": "http://evil.example"})
        self.assertEqual(stato, 403)

    def test_area_returns_score_and_recommendations(self):
        stato, dati, _ = self.request("GET", "/api/v1/areas/cleanup")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["score"], 94)
        self.assertEqual(dati["recommendations"][0]["action_id"], "cleanup.temp")
        self.assertIn("cleanup.temp", [a["id"] for a in dati["actions"]])

    def test_unread_post_body_does_not_break_keep_alive(self):
        connessione = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connessione.request("POST", "/api/v1/areas/services/scan", body="{}",
                                headers={"X-WMM-Token": self.agent.token, "Content-Type": "application/json"})
            self.assertEqual(connessione.getresponse().read() and 200, 200)
            connessione.request("GET", "/api/v1/agent/info")
            risposta = connessione.getresponse()
            risposta.read()
            self.assertEqual(risposta.status, 200)
        finally:
            connessione.close()

    def test_unknown_area_404(self):
        self.assertEqual(self.request("GET", "/api/v1/areas/nope")[0], 404)

    def test_dashboard(self):
        # The dashboard never starts slow area scans: unscanned areas report None.
        stato, dati, _ = self.request("GET", "/api/v1/dashboard")
        self.assertEqual(stato, 200)
        self.assertEqual(set(dati["scores"]), set(api.actions.AREAS) | {"overall"})
        self.assertIsNone(dati["scores"]["network"])
        self.assertIsNone(dati["scores"]["overall"])
        self.assertEqual(dati["system"]["os"]["cpu"], "CPU")
        self.request("GET", "/api/v1/areas/cleanup")
        self.assertEqual(self.request("GET", "/api/v1/dashboard")[1]["scores"]["overall"], 94)

    def test_new_area_scan(self):
        stato, dati, _ = self.request("GET", "/api/v1/areas/performance")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["score"], 85)
        self.assertIn("performance.power_balanced", [r["action_id"] for r in dati["recommendations"]])

    def test_recommendations_aggregate_areas(self):
        self.request("GET", "/api/v1/areas/cleanup")
        self.request("GET", "/api/v1/areas/performance")
        stato, dati, _ = self.request("GET", "/api/v1/recommendations")
        self.assertEqual(stato, 200)
        self.assertEqual({r["area"] for r in dati["items"]}, {"cleanup", "performance"})
        priorita = [r["priority"] for r in dati["items"]]
        self.assertEqual(priorita, sorted(priorita))

    def test_activity_lists_scans(self):
        self.request("POST", "/api/v1/areas/cleanup/scan")
        stato, dati, _ = self.request("GET", "/api/v1/activity")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["tasks"][0]["title"], "Scan · Cleanup")
        self.assertEqual(dati["tasks"][0]["status"], "ok")
        self.assertEqual(dati["jobs"], [])
        self.assertIn("schedules", dati)

    def test_pairing_approved_on_desktop_returns_token(self):
        with mock.patch.object(self.agent, "_ask_user", return_value=True) as chiedi:
            stato, dati, _ = self.request("POST", "/api/v1/pair", token=False)
        self.assertEqual(stato, 200)
        self.assertEqual(dati["token"], self.agent.token)
        chiedi.assert_called_once()

    def test_pairing_denied_on_desktop(self):
        with mock.patch.object(self.agent, "_ask_user", return_value=False):
            stato, dati, _ = self.request("POST", "/api/v1/pair", token=False)
        self.assertEqual(stato, 403)
        self.assertNotIn("token", dati)

    def test_pairing_still_checks_host_and_origin(self):
        with mock.patch.object(self.agent, "_ask_user", return_value=True) as chiedi:
            self.assertEqual(self.request("POST", "/api/v1/pair", token=False, headers={"Origin": "http://evil.example"})[0], 403)
        chiedi.assert_not_called()

    def test_token_check_endpoint(self):
        self.assertEqual(self.request("POST", "/api/v1/agent/token-check")[0], 200)
        self.assertEqual(self.request("POST", "/api/v1/agent/token-check", token=False)[0], 403)

    def test_elevate(self):
        with mock.patch.object(self.agent, "_launch_elevated", return_value=True) as lancia, \
                mock.patch.object(self.agent, "_schedule_shutdown") as spegni:
            stato, dati, _ = self.request("POST", "/api/v1/agent/elevate")
        if self.admin:
            self.assertEqual(stato, 409)
            lancia.assert_not_called()
        else:
            self.assertEqual(stato, 200)
            self.assertTrue(dati["restarting"])
            lancia.assert_called_once()
            spegni.assert_called_once()

    def test_elevate_declined(self):
        if self.admin:
            return
        with mock.patch.object(self.agent, "_launch_elevated", return_value=False), mock.patch.object(self.agent, "_schedule_shutdown") as spegni:
            stato, dati, _ = self.request("POST", "/api/v1/agent/elevate")
        self.assertEqual(stato, 409)
        self.assertIn("declined", dati["error"])
        spegni.assert_not_called()

    def test_health_endpoint(self):
        voci = [{"id": "python", "name": "Python", "status": "ok", "detail": "3.12", "critical": False},
                {"id": "admin", "name": "Administrator rights", "status": "warning", "detail": "x", "critical": False}]
        with mock.patch.object(api.health, "run_checks", return_value=voci) as esegui:
            stato, dati, _ = self.request("GET", "/api/v1/health")
            self.assertEqual(stato, 200)
            self.assertEqual(dati["summary"], {"ok": 1, "warning": 1, "error": 0, "blocking": False})
            self.request("GET", "/api/v1/health")
            self.assertEqual(esegui.call_count, 1)
            self.request("GET", "/api/v1/health?refresh=1")
            self.assertEqual(esegui.call_count, 2)
            self.assertIsNone(esegui.call_args[0][1])

    def test_playbooks(self):
        stato, dati, _ = self.request("GET", "/api/v1/playbooks")
        self.assertEqual(stato, 200)
        rapido = [p for p in dati["playbooks"] if p["id"] == "quick"][0]
        self.assertEqual(rapido["risk"], "safe")
        self.assertGreater(rapido["minutes"], 0)
        self.assertEqual(rapido["steps"][0]["id"], "cleanup.temp")

    def test_settings_roundtrip(self):
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"company": "Acme IT"})[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/settings")[1]["company"], "Acme IT")
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"evil": "x"})[0], 400)
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"company": ["x"]})[0], 400)
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"company": "x"}, token=False)[0], 403)

    def test_live_samples(self):
        class FakeMonitor:
            last_error = ""

            def request(self, since):
                return [{"t": since + 1, "cpu": 12.5}]

        self.agent.monitor = FakeMonitor()
        stato, dati, _ = self.request("GET", "/api/v1/live?since=100")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["samples"], [{"t": 101, "cpu": 12.5}])
        self.assertEqual(self.request("GET", "/api/v1/live?since=abc")[0], 400)

    def test_startup_toggle(self):
        stato, _, _ = self.request("POST", "/api/v1/startup/0123456789abcdef/toggle", {"enabled": False})
        if self.admin:
            self.assertEqual(stato, 200)
            inventory.set_startup_enabled.assert_called_once()
            self.assertFalse(inventory.set_startup_enabled.call_args[0][1])
            run = self.agent.store.runs(self.agent.machine_id)[0]
            self.assertEqual((run["action_id"], run["status"]), ("startup.toggle", "ok"))
        else:
            self.assertEqual(stato, 409)
        self.assertEqual(self.request("POST", "/api/v1/startup/ffffffffffffffff/toggle", {"enabled": False})[0], 404 if self.admin else 409)
        self.assertEqual(self.request("POST", "/api/v1/startup/0123456789abcdef/toggle", {"enabled": "no"})[0], 400)

    def test_non_safe_run_without_confirmation_400(self):
        stato, dati, _ = self.request("POST", "/api/v1/runs", {"actions": ["integrity.sfc"], "confirmed": False})
        self.assertEqual(stato, 400)

    def test_export_csv_header(self):
        stato, testo, risposta = self.request("GET", "/api/v1/export/all.csv")
        self.assertEqual(stato, 200)
        # The BOM lets Excel open the file as UTF-8.
        self.assertTrue(testo.startswith(chr(0xFEFF) + "date,action,area,origin,status,note,bytes_freed"))
        self.assertIn("attachment", risposta.getheader("Content-Disposition"))

    def test_static_path_traversal_404(self):
        self.assertEqual(self.request("GET", "/static/../../ottimizza_pc.py")[0], 404)
        self.assertEqual(self.request("GET", "/static/..%5C..%5Cottimizza_pc.py")[0], 404)

    def test_index_does_not_contain_token(self):
        # The token reaches the browser only through the URL the agent opens (#k=...).
        stato, testo, _ = self.request("GET", "/")
        self.assertEqual(stato, 200)
        self.assertNotIn(self.agent.token, testo)

    def test_static_unc_path_404(self):
        self.assertEqual(self.request("GET", "/static/%2F%2Fattacker.invalid%2Fshare%2Fx")[0], 404)
        self.assertEqual(self.request("GET", "/static/%5C%5Cattacker.invalid%5Cshare%5Cx")[0], 404)
        self.assertEqual(self.request("GET", "/static/C:%5CWindows%5Cwin.ini")[0], 404)
        self.assertEqual(self.request("GET", "/static/js/app.js")[0], 200)

    def test_malformed_bodies_400(self):
        self.assertEqual(self.request("POST", "/api/v1/runs", {"actions": [["x"]], "confirmed": True})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/runs", {"actions": "cleanup.temp"})[0], 400)
        corpo = {"action_id": "cleanup.temp", "kind": "once", "at": "2026-11-05T3:00", "days": "", "confirmed": False}
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        corpo.update(at="2026-11-05T03:00", kind="weekly", days=["MON"])
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        corpo.update(action_id={"a": 1}, kind="once", days="")
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)

    def test_schedules_report_installation_protection(self):
        stato, dati, _ = self.request("GET", "/api/v1/schedules")
        self.assertEqual(stato, 200)
        self.assertFalse(dati["installation"]["protected"])
        self.assertEqual(dati["installation"]["writable"], [r"C:\Users\x\Desktop\wmm.py"])
        self.assertIn("--install", dati["installation"]["command"])

    def test_safe_run_in_area_without_safe_actions_400(self):
        stato, dati, _ = self.request("POST", "/api/v1/runs/safe", {"area": "services"})
        self.assertEqual(stato, 400)
        self.assertIn("no safe actions", dati["error"].lower())

    def test_failed_collection_is_marked_incomplete(self):
        collectors.collect_services.return_value = {"totals": {"total": 0}, "managed": [], "startup": [], "protected_present": 0,
                                                    "backup_count": 0, "errors": ["Services: timed out"]}
        stato, dati, _ = self.request("GET", "/api/v1/areas/services")
        self.assertEqual(stato, 200)
        self.assertLessEqual(dati["score"], 50)
        self.assertEqual(dati["recommendations"][0]["id"], "services.incomplete")

    def test_non_safe_schedule_without_confirmation_400(self):
        corpo = {"action_id": "integrity.sfc", "kind": "once", "at": "2026-11-05T03:00", "days": "", "confirmed": False}
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        api.scheduler.register.assert_not_called()

    def test_schedule_lifecycle(self):
        corpo = {"action_id": "cleanup.temp", "kind": "weekly", "at": "2026-11-05T03:00", "days": "MON", "confirmed": False}
        stato, dati, _ = self.request("POST", "/api/v1/schedules", corpo)
        self.assertEqual(stato, 201)
        api.scheduler.register.assert_called_once()
        stato, elenco, _ = self.request("GET", "/api/v1/schedules")
        self.assertEqual([s["id"] for s in elenco["schedules"]], [dati["id"]])
        self.assertEqual(self.request("DELETE", f"/api/v1/schedules/{dati['id']}")[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/schedules")[1]["schedules"], [])

    def test_failed_registration_removes_schedule(self):
        api.scheduler.register.side_effect = RuntimeError("Access denied")
        corpo = {"action_id": "cleanup.temp", "kind": "daily", "at": "2026-11-05T03:00", "days": "", "confirmed": False}
        stato, dati, _ = self.request("POST", "/api/v1/schedules", corpo)
        self.assertEqual(stato, 500)
        self.assertIn("Access denied", dati["error"])
        self.assertEqual(self.agent.store.schedules(), [])


    def test_restore_point_on_start(self):
        with mock.patch.object(self.agent.jobs, "start", return_value="a" * 32) as avvia:
            self.assertEqual(self.agent.restore_point_on_start(), "a" * 32)
            avvia.assert_called_once_with(["security.restore_point"], "auto", confirmed=True)
            self.agent.store.save_settings({"restore_on_start": "0"})
            self.assertIsNone(self.agent.restore_point_on_start())
            self.assertEqual(avvia.call_count, 1)

    def test_restore_point_on_start_skips_when_a_run_holds_the_lock(self):
        with mock.patch.object(self.agent.jobs, "start", side_effect=api.RunInProgress("busy")):
            self.assertIsNone(self.agent.restore_point_on_start())

    def test_autostart_endpoints(self):
        with mock.patch.object(api.autostart, "is_enabled", return_value=False), mock.patch.object(api.autostart, "enable") as attiva:
            stato, dati, _ = self.request("GET", "/api/v1/agent/autostart")
            self.assertEqual((stato, dati["enabled"], dati["protected"]), (200, False, False))
            self.assertEqual(self.request("PUT", "/api/v1/agent/autostart", {"enabled": True}, token=False)[0], 403)
            self.assertEqual(self.request("PUT", "/api/v1/agent/autostart", {"enabled": "yes"})[0], 400)
            stato, _, _ = self.request("PUT", "/api/v1/agent/autostart", {"enabled": True})
            self.assertEqual(stato, 200)
            attiva.assert_called_once_with(self.agent.python, self.agent.script, self.agent.port)

    def test_autostart_unprotected_is_409(self):
        with mock.patch.object(api.autostart, "is_enabled", return_value=False), \
                mock.patch.object(api.autostart, "enable", side_effect=api.scheduler.UnprotectedProgram("Writable paths: x")):
            stato, dati, _ = self.request("PUT", "/api/v1/agent/autostart", {"enabled": True})
        self.assertEqual(stato, 409)
        self.assertIn("Writable", dati["error"])


    def test_shutdown_stops_others_then_itself(self):
        with mock.patch.object(api.shutdown, "stop_others", return_value=[4321]) as altri, \
                mock.patch.object(self.agent, "_stop_self") as se_stesso, mock.patch.object(api.threading, "Timer") as timer:
            self.assertEqual(self.request("POST", "/api/v1/agent/shutdown", token=False)[0], 403)
            altri.assert_not_called()
            stato, dati, _ = self.request("POST", "/api/v1/agent/shutdown")
        self.assertEqual((stato, dati["stopped_processes"], dati["run_interrupted"]), (200, 1, False))
        timer.assert_called_once_with(1.0, se_stesso)
        timer.return_value.start.assert_called_once()

    def test_shutdown_refused_in_preview(self):
        agente = api.Agent(Path(self.tmp.name), preview=True, admin=True)
        with mock.patch.object(api.shutdown, "stop_others") as altri:
            with self.assertRaises(api.ApiError) as errore:
                agente.shutdown()
        self.assertEqual(errore.exception.status, 409)
        altri.assert_not_called()


class NotAdmin(ApiTests):
    admin = False

    def test_shutdown_stops_others_then_itself(self):
        with mock.patch.object(api.shutdown, "stop_others") as altri, mock.patch.object(api.threading, "Timer") as timer:
            stato, dati, _ = self.request("POST", "/api/v1/agent/shutdown")
        self.assertEqual(stato, 409)
        self.assertIn("administrator", dati["error"])
        altri.assert_not_called()
        timer.assert_not_called()

    def test_restore_point_on_start(self):
        with mock.patch.object(self.agent.jobs, "start") as avvia:
            self.assertIsNone(self.agent.restore_point_on_start())
        avvia.assert_not_called()

    def test_autostart_endpoints(self):
        with mock.patch.object(api.autostart, "is_enabled", return_value=False), mock.patch.object(api.autostart, "enable") as attiva:
            self.assertEqual(self.request("PUT", "/api/v1/agent/autostart", {"enabled": True})[0], 409)
        attiva.assert_not_called()

    test_restore_point_on_start_skips_when_a_run_holds_the_lock = None
    test_autostart_unprotected_is_409 = None

    def test_not_admin_409(self):
        stato, dati, _ = self.request("POST", "/api/v1/runs", {"actions": ["cleanup.temp"], "confirmed": True})
        self.assertEqual(stato, 409)
        self.assertIn("Administrator", dati["error"])

    # Schedules need administrator rights too: the lifecycle tests do not apply.
    test_schedule_lifecycle = None
    test_failed_registration_removes_schedule = None


if __name__ == "__main__":
    unittest.main()
