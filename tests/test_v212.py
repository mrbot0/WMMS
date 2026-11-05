"""Tests for 2.12: the thirty features (wmm/agent/plus212.py), their settings and routes, the QR code, idle schedules
and campaigns. Nothing changes the PC: the checks that read Windows get fixed answers."""
import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from wmm.agent import actions, appsettings, central, notify, plus212, qrcode, scheduler
from tests import test_v29

PW = test_v29.PW


class Explanations(unittest.TestCase):
    def test_slow_pc_explained(self):
        d = plus212.explain_slow({"cpu": 97, "top_cpu": [{"name": "TiWorker", "cpu": 60, "mem_mb": 300}], "mem_total_mb": 8000, "mem_free_mb": 500,
                                  "top_mem": [{"name": "chrome", "mem_mb": 3000}], "disk_busy": 99, "disk_queue": 4, "uptime_days": 12, "power_plan": "Power saver"})
        self.assertTrue(d["causes"][0]["title"].startswith("The processor is at 97%"))
        self.assertIn("Windows Update", d["causes"][0]["detail"])
        self.assertEqual(len(d["causes"]), 5)
        self.assertFalse(d["ok"])
        for c in d["causes"]:
            for t in c["tools"]:
                self.assertIn(t, actions.CATALOG)
        calmo = plus212.explain_slow({"cpu": 5, "mem_total_mb": 8000, "mem_free_mb": 5000, "uptime_days": 1, "top_cpu": []})
        self.assertTrue(calmo["ok"])
        self.assertEqual(calmo["verdict"], "Nothing is slowing the PC right now")

    def test_disk_forecast(self):
        oggi = datetime(2026, 11, 5)
        punti = [((oggi - timedelta(days=30 - i * 10)).isoformat(), 100 - i * 10, 500) for i in range(4)]  # 1 GB a day
        f = plus212.disk_forecast(punti, oggi)
        self.assertAlmostEqual(f["per_month_gb"], -30, delta=0.5)
        self.assertEqual(f["days"], 70)
        self.assertEqual(f["full_on"], "2027-01-14")
        self.assertIsNone(plus212.disk_forecast(punti[:2], oggi)["full_on"])
        self.assertIn("stable", plus212.disk_forecast([(p[0], 50, 500) for p in punti], oggi)["reason"])

    def test_ports_explained(self):
        porte = plus212.explain_ports([{"port": 3389, "address": "0.0.0.0", "process": "svchost"}, {"port": 8765, "address": "127.0.0.1", "process": "python"},
                                       {"port": 445, "address": "::", "process": "System"}, {"port": 3389, "address": "::", "process": "svchost"}])
        self.assertEqual([p["port"] for p in porte], [3389, 445, 8765])
        self.assertEqual(porte[0]["risk"], "high")
        self.assertTrue(porte[2]["local_only"])

    def test_windows_support(self):
        self.assertEqual(plus212.windows_support(19045, "Professional", date(2026, 11, 5))["status"], "ended")
        s = plus212.windows_support(22631, "Enterprise", date(2026, 11, 5))
        self.assertEqual((s["status"], s["days"]), ("soon", 5))
        self.assertEqual(plus212.windows_support(26100, "Professional", date(2026, 1, 1))["status"], "ok")
        self.assertEqual(plus212.windows_support(99999, "Professional")["status"], "unknown")

    def test_extensions_are_rated(self):
        self.assertEqual(plus212.score_extension(["<all_urls>", "cookies", "debugger"])["level"], "high")
        self.assertEqual(plus212.score_extension(["storage"])["level"], "low")
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "Google" / "Chrome" / "User Data" / "Default" / "Extensions" / "abc" / "1.0_0"
            (v / "_locales" / "en").mkdir(parents=True)
            (v / "manifest.json").write_text(json.dumps({"name": "__MSG_appName__", "permissions": ["tabs", "cookies"], "host_permissions": ["<all_urls>"]}))
            (v / "_locales" / "en" / "messages.json").write_text(json.dumps({"appName": {"message": "Coupon Helper"}}))
            e = plus212.browser_extensions(Path(d))
        self.assertEqual((e[0]["name"], e[0]["level"]), ("Coupon Helper", "high"))

    def test_bitlocker_explained(self):
        self.assertEqual(plus212.explain_bitlocker({"readable": False})["state"], "unknown")
        self.assertEqual(plus212.explain_bitlocker({"readable": True, "status": "Off", "protectors": []})["state"], "off")
        self.assertEqual(plus212.explain_bitlocker({"readable": True, "status": "On", "protectors": ["Tpm"]})["state"], "nokey")
        self.assertEqual(plus212.bitlocker(lambda: '{"readable": true, "status": "On", "percent": 100, "protectors": ["Tpm", "RecoveryPassword"]}')["state"], "ok")

    def test_update_calendar(self):
        dati = json.dumps({"history": [{"date": "2026-10-14T10:00:00", "title": "2026-10 Cumulative Update (KB5050001)", "result": 2},
                                       {"date": "2026-10-20T10:00:00", "title": "Driver X", "result": 4}],
                           "hotfix": [{"date": "2026-10-14T00:00:00", "title": "KB5050001 Update", "result": 2}]})
        c = plus212.update_calendar(lambda: dati)
        self.assertEqual(c["failed"], 1)
        self.assertEqual(c["months"], {"2026-10": 2})  # the hotfix of the same KB and day is not counted twice
        self.assertEqual(c["last"], "2026-10-20")

    def test_internet_check_stops_at_the_first_failure(self):
        schede = lambda: {"adapters": [{"name": "Wi-Fi", "ipv4": "192.168.1.5", "gateway": "192.168.1.1"}]}  # noqa: E731
        ok = plus212.internet_check(schede, ping=lambda h: True, dns=lambda n: True, http=lambda: "ok", https=lambda: True)
        self.assertTrue(ok["ok"])
        self.assertEqual(len(ok["steps"]), 6)
        dns = plus212.internet_check(schede, ping=lambda h: True, dns=lambda n: False, http=lambda: "ok", https=lambda: True)
        self.assertEqual(dns["steps"][-1]["step"], "Names (DNS)")
        self.assertIn("network.flush_dns", dns["steps"][-1]["tools"])
        apipa = plus212.internet_check(lambda: {"adapters": [{"name": "Ethernet", "ipv4": "169.254.3.4", "gateway": ""}]})
        self.assertEqual(apipa["steps"][-1]["step"], "Address (DHCP)")
        portale = plus212.internet_check(schede, ping=lambda h: True, dns=lambda n: True, http=lambda: "portal", https=lambda: True)
        self.assertIn("sign-in page", portale["verdict"])
        for s in dns["steps"] + apipa["steps"]:
            for t in s["tools"]:
                self.assertIn(t, actions.CATALOG)

    def test_winget_list_is_parsed(self):
        testo = ("Name             Id                    Version  Available Source\n" + "-" * 70 + "\n"
                 "7-Zip 23.01      7zip.7zip             23.01    24.08     winget\nGit              Git.Git               2.40.0   2.47.0    winget\n"
                 "2 upgrades available.\n")
        self.assertEqual(plus212.winget_upgradable(lambda: testo), ["7zip.7zip", "Git.Git"])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.casa = Path(self.tmp.name)
        for c in ("Documents", "Downloads"):
            (self.casa / c).mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicates_forgotten_and_map(self):
        dati = os.urandom(1 << 20) + b"x"
        (self.casa / "Documents" / "a.bin").write_bytes(dati)
        (self.casa / "Downloads" / "a (1).bin").write_bytes(dati)
        (self.casa / "Downloads" / "b.bin").write_bytes(dati[:-1] + b"y")  # same size, different content
        cartelle = plus212.default_folders(self.casa)
        d = plus212.duplicates(cartelle)
        self.assertEqual(len(d["groups"]), 1)
        self.assertEqual(d["waste"], len(dati))
        vecchio = self.casa / "Downloads" / "old.iso"
        vecchio.write_bytes(b"0" * 2048)
        prima = time.time() - 400 * 86400
        os.utime(vecchio, (prima, prima))
        f = plus212.forgotten(cartelle, minimo=1024)
        self.assertEqual([Path(x["path"]).name for x in f["files"]], ["old.iso"])
        m = plus212.folder_map(str(self.casa))
        self.assertEqual({c["name"] for c in m["children"]}, {"Documents", "Downloads"})
        self.assertGreater(m["total"], 3 * len(dati) - 10)
        with self.assertRaises(ValueError):
            plus212.folder_map("\\\\server\\share")

    def test_recycle_only_inside_the_user_folders(self):
        dentro = self.casa / "Documents" / "x.txt"
        dentro.write_text("x")
        fuori = Path(tempfile.gettempdir()) / "wmm-outside.txt"
        r = plus212.recycle([str(dentro), str(fuori), "C:\\Windows\\win.ini"], ammessi=plus212.default_folders(self.casa), preview=True)
        self.assertEqual(r["would_move"], 1)
        self.assertEqual(len(r["refused"]), 2)
        chiamato = []
        r = plus212.recycle([str(dentro)], ammessi=plus212.default_folders(self.casa), runner=lambda: chiamato.append(1) or '{"moved": 1}')
        self.assertEqual((r["moved"], chiamato), (1, [1]))
        # A name with quotes PowerShell recognises never reaches the script as text.
        strano = self.casa / "Documents" / "a’); Remove-Item x; (’.txt"
        strano.write_text("x")
        visti = []
        with mock.patch.object(plus212.crashes, "run_json", side_effect=lambda script, runner, timeout: visti.append(script) or {"moved": 1}):
            plus212.recycle([str(strano)], ammessi=plus212.default_folders(self.casa))
        self.assertNotIn("Remove-Item", visti[0])
        self.assertNotIn("’", visti[0])


class SettingsAndRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_are_validated(self):
        appsettings.save(self.dir, {"automation_rules": [{"event": "disk_low", "action_id": "cleanup.temp"}],
                                    "goals": [{"metric": "c_free_pct", "op": ">=", "value": 15}], "winget_exclusions": ["Zoom.Zoom", "Zoom.Zoom"]})
        s = appsettings.load(self.dir)
        self.assertEqual(s["automation_rules"][0]["action_id"], "cleanup.temp")
        self.assertEqual(s["winget_exclusions"], ["Zoom.Zoom"])
        for errato in ({"automation_rules": [{"event": "disk_low", "action_id": "integrity.disk_repair"}]},  # not a safe tool
                       {"automation_rules": [{"event": "nope", "action_id": "cleanup.temp"}]}, {"goals": [{"metric": "x", "op": ">=", "value": 1}]},
                       {"winget_exclusions": ["rm -rf /"]}, {"file_backup": {"target": "not a path"}}):
            with self.assertRaises(appsettings.SettingsError):
                appsettings.save(self.dir, errato)
        with mock.patch.object(plus212, "user_home", return_value=Path("C:\\Users\\tester")):
            with self.assertRaises(appsettings.SettingsError):
                appsettings.save(self.dir, {"file_backup": {"target": "C:\\Users\\tester\\Backup"}})
            appsettings.save(self.dir, {"file_backup": {"target": "\\\\nas\\backup\\pc", "folders": ["Documents"]}})

    def test_rules_run_once_per_gap_and_wait_when_busy(self):
        regole = [{"id": "r1", "event": "disk_low", "action_id": "cleanup.temp", "enabled": True}]
        plus212.enqueue(self.dir, "disk_low")
        avviati = []
        self.assertEqual(plus212.process_rules(self.dir, regole, avviati.append, adesso=1000.0), ["cleanup.temp"])
        plus212.enqueue(self.dir, "disk_low")
        self.assertEqual(plus212.process_rules(self.dir, regole, avviati.append, adesso=1100.0), [])  # within 30 minutes
        plus212.enqueue(self.dir, "disk_low")

        def occupato(_):
            raise RuntimeError("busy")
        self.assertEqual(plus212.process_rules(self.dir, regole, occupato, adesso=5000.0), [])
        self.assertEqual(plus212.process_rules(self.dir, regole, avviati.append, adesso=5060.0), ["cleanup.temp"])  # the event waited

    def test_alerts_queue_rules_even_without_channels(self):
        notify.for_data_dir(self.dir).event("disk_low", "C: is full")
        coda = json.loads((self.dir / plus212.QUEUE).read_text(encoding="utf-8"))
        self.assertEqual(coda[0]["event"], "disk_low")

    def test_goals_and_changes(self):
        stato = plus212.evaluate_goals(plus212.clean_goals([{"metric": "c_free_pct", "op": ">=", "value": 20}, {"metric": "open_issues", "op": "<=", "value": 5},
                                                            {"metric": "overall", "op": ">=", "value": 80}]), {"c_free_pct": 12.0, "open_issues": 3, "overall": None})
        self.assertEqual([g["ok"] for g in stato], [False, True, None])
        prima = {"cleanup": {"score": 90, "created": "2026-11-04T10:00:00", "data": {"recommendations": [{"title": "Old"}]}}}
        dopo = {"cleanup": {"score": 70, "created": "2026-11-05T10:00:00", "data": {"recommendations": [{"title": "New"}]}}}
        c = plus212.changes(dopo, prima, [{"status": "error", "action_id": "cleanup.temp", "note": "x"}, {"status": "ok"}])
        self.assertEqual((c["areas"][0]["delta"], c["areas"][0]["new"], c["areas"][0]["solved"]), (-20, ["New"], ["Old"]))
        self.assertEqual(c["runs"], 2)
        self.assertEqual(c["failed"][0]["action_id"], "cleanup.temp")

    def test_diagnostic_package_removes_secrets(self):
        z = zipfile.ZipFile(io.BytesIO(plus212.diagnostic_package({"app_settings": {"webhook_url": "https://hooks/x", "org_name": "ACME",
                                                                                    "nested": {"smtp_password": "p", "telegram_token": ""}}})))
        dati = json.loads(z.read("app_settings.json"))
        self.assertEqual(dati["webhook_url"], "[removed]")
        self.assertEqual(dati["nested"]["smtp_password"], "[removed]")
        self.assertEqual(dati["org_name"], "ACME")
        self.assertIn("README.txt", z.namelist())

    def test_idle_schedules(self):
        voce = {"id": 3, "action_id": "cleanup.temp", "kind": "idle", "at": "2026-11-05T00:00", "days": "", "delay": 0, "enabled": True}
        xml = scheduler.task_xml(voce, "C:\\Python\\python.exe", "C:\\WMM\\wmm.py")
        self.assertIn("<IdleTrigger>", xml)
        self.assertIn("<Duration>PT10M</Duration>", xml)
        self.assertIn("<RunOnlyIfIdle>true</RunOnlyIfIdle>", xml)
        self.assertIsNone(scheduler.next_run(voce, datetime(2026, 11, 5)))


class QrCode(unittest.TestCase):
    def test_versions_and_label(self):
        self.assertEqual(qrcode.QR(b"hi").size, 21)
        self.assertEqual(qrcode.QR(b"x" * 84).version, 5)  # 5-M: 86 data codewords, 2 for mode and length
        self.assertEqual(qrcode.QR(b"x" * 85).version, 6)
        with self.assertRaises(ValueError):
            qrcode.QR(b"x" * 300)
        etichetta = plus212.inventory_label({"hardware": {"manufacturer": "ACME", "model": "X1", "serial": "S9"}}, "PC-01", "abcdef1234567890")
        self.assertTrue(etichetta["qr"].startswith("<svg"))
        self.assertEqual(etichetta["fields"]["Serial"], "S9")

    def test_same_matrix_as_a_reference_encoder(self):
        try:
            import segno
            import segno.encoder
        except ImportError:
            self.skipTest("segno is not installed")
        # segno adds 8 zero bits when the data already ends on a byte; the standard does not: align it for the comparison.
        with mock.patch.object(segno.encoder, "write_padding_bits", lambda buff, version, length: buff.extend([0] * ((8 - length % 8) % 8))):
            for testo in (b"WMM", b"PC-01 serial 1234", b"y" * 90):
                for m in (0, 3, 7):
                    q = qrcode.QR(testo, mask=m)
                    s = segno.make(testo, error="m", version=q.version, mask=m, mode="byte", boost_error=False)
                    self.assertEqual([[bool(c) for c in r] for r in s.matrix], q.modules)


class Delegations(test_v29.Temp):
    def test_temporary_role_comes_back(self):
        from wmm.agent import accounts as A
        acc = A.Accounts(self.dir / "accounts.db")
        acc.setup("admin", PW)
        admin = acc.session(acc.login("admin", PW)["token"])
        acc.create_user({"username": "luca", "role_id": "operator", "password": "L4ca!Password22"})
        v = plus212.delegate(acc, self.dir, "luca", "technician", 4, admin)
        self.assertEqual(v["previous_role"], "operator")
        self.assertEqual(next(u for u in acc.users() if u["username"] == "luca")["role_id"], "technician")
        with self.assertRaises(ValueError):
            plus212.delegate(acc, self.dir, "luca", "technician", 4, admin)
        self.assertEqual(plus212.end_delegations(acc, self.dir, adesso=datetime.now() + timedelta(hours=1)), [])
        self.assertEqual(plus212.end_delegations(acc, self.dir, adesso=datetime.now() + timedelta(hours=5)), ["luca"])
        self.assertEqual(next(u for u in acc.users() if u["username"] == "luca")["role_id"], "operator")
        r = plus212.access_review(acc.users(), [], {})
        self.assertIn("administrator without two-step verification", next(u for u in r["users"] if u["username"] == "admin")["flags"])


class Campaigns(unittest.TestCase):
    def test_progress_and_scope(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            s = central.Server(Path(d))
            with s._db() as db:
                for i, t in (("a" + "1" * 16, ""), ("a" + "2" * 16, "k1")):
                    db.execute("INSERT INTO agents (id, hostname, machine_id, secret, enrolled, tenant) VALUES (?, ?, ?, '', '2026-11-05', ?)", (i, "PC" + i[-1], "M" + i[-1], t))
            k = s.create_campaign("Chrome everywhere", "2026-11-01", ["a" + "1" * 16, "a" + "2" * 16], "inventory", {}, "admin")
            self.assertEqual((k["total"], k["queued"], k["percent"], k["overdue"]), (2, 2, 0, True))
            with s._db() as db:
                db.execute("UPDATE jobs SET status = 'done'")
            self.assertEqual(s.campaigns()[0]["percent"], 100)
            self.assertEqual(s.campaigns({"k1"})[0]["total"], 1)
            with self.assertRaises(central.CentralError):
                s.create_campaign("x", "", ["a" + "1" * 16], "inventory", {})


class Api(test_v29.ApiBase):
    def test_routes(self):
        with mock.patch.object(plus212, "slow_now", return_value={"verdict": "ok"}), \
                mock.patch.object(plus212, "internet_check", return_value={"ok": True}):
            self.assertEqual(self.call("GET", "/plus/slow-now")[1]["verdict"], "ok")
            self.assertTrue(self.call("POST", "/plus/internet-check", {})[1]["ok"])
        stato, d, _ = self.call("PUT", "/plus/automation", {"goals": [{"metric": "overall", "op": ">=", "value": 80}]})
        self.assertEqual((stato, d["goals"][0]["metric"]), (200, "overall"))
        self.assertEqual(self.call("PUT", "/plus/automation", {"automation_rules": [{"event": "disk_low", "action_id": "integrity.disk_repair"}]})[0], 400)
        self.assertIsNone(self.call("GET", "/plus/goals")[1]["goals"][0]["ok"])
        self.assertIn("areas", self.call("GET", "/plus/changes")[1])
        stato, corpo, risposta = self.request("GET", "/api/v1/plus/diagnostic.zip")
        self.assertEqual((stato, risposta.getheader("Content-Type")), (200, "application/zip"))


if __name__ == "__main__":
    unittest.main()
