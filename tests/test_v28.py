"""Tests for 2.8: blue screens, slow startup, failure signs, good configuration, suspicious programs, phone console,
several PCs at once (with a second PC in its own process), periodic report and assistant. Nothing changes the PC."""
import base64
import hashlib
import json
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from wmm.agent import (actions, assistant, boot, crashes, digest, early_warning, fleet, goodconfig, notify, phone, suspicious)
from wmm.server import api

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 5, 12, 0, 0)


def runner(dati):
    return lambda *a: "noise\n" + json.dumps(dati)


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class BlueScreens(Temp):
    def dump(self, name, code, when):
        testa = bytearray(0x80)
        testa[:8] = b"PAGEDU64"
        struct.pack_into("<I", testa, 0x38, code)
        struct.pack_into("<4Q", testa, 0x40, 1, 2, 3, 0xFFFF)
        p = self.dir / name
        p.write_bytes(bytes(testa) + b"\0" * 64)
        t = when.timestamp()
        import os
        os.utime(p, (t, t))
        return p

    def test_header_and_explanation(self):
        p = self.dump("a.dmp", 0xD1, NOW)
        self.assertEqual(crashes.read_dump_header(p), {"code": 0xD1, "params": [1, 2, 3, 0xFFFF]})
        (self.dir / "bad.dmp").write_bytes(b"MDMP" + b"\0" * 200)
        self.assertIsNone(crashes.read_dump_header(self.dir / "bad.dmp"))
        self.assertEqual(crashes.explain(0xD1)["name"], "DRIVER_IRQL_NOT_LESS_OR_EQUAL")
        ignoto = crashes.explain(0x1234)
        self.assertEqual(ignoto["name"], "0x1234")
        self.assertTrue(ignoto["cause_it"])
        for codice, voce in crashes.CODES.items():
            for t in voce["tools"]:
                self.assertIn(t, actions.CATALOG, f"{codice:x} {t}")

    def test_groups_dedup_and_suspects(self):
        primo = NOW - timedelta(days=3)
        self.dump("1.dmp", 0x9F, primo)
        self.dump("2.dmp", 0x9F, NOW - timedelta(days=1))
        eventi = {"drivers": [{"at": (primo - timedelta(days=2)).isoformat(), "text": "Driver Management concluded installing usbxhci"},
                              {"at": (primo - timedelta(days=20)).isoformat(), "text": "old driver"}],
                  "bugchecks": [{"at": (primo + timedelta(minutes=2)).isoformat(), "text": "The computer has rebooted from a bugcheck. The bugcheck was: 0x0000009f (0x3)"},
                                {"at": (NOW - timedelta(days=40)).isoformat(), "text": "The bugcheck was: 0x00000124 (0x0)"}]}
        d = crashes.analyze(self.dir, runner(eventi), now=NOW)
        self.assertEqual(d["crashes"], 3)  # the event two minutes after a dump is the same crash
        self.assertEqual(d["last_30_days"], 2)
        g = d["groups"][0]
        self.assertEqual((g["name"], g["count"]), ("DRIVER_POWER_STATE_FAILURE", 2))
        self.assertEqual([s["text"] for s in g["suspects"]], ["Driver Management concluded installing usbxhci"])


class SlowBoot(unittest.TestCase):
    def events(self):
        ev = []
        for i, sec in enumerate([30, 32, 31, 60, 62, 64]):
            ev.append({"id": 100, "at": (NOW - timedelta(days=30 - i)).isoformat(), "data": {"BootTime": str(sec * 1000), "MainPathBootTime": "20000"}})
        ev += [{"id": 101, "at": (NOW - timedelta(days=2)).isoformat(), "data": {"Name": "C:\\Apps\\Updater.exe", "FriendlyName": "Updater", "DegradationTime": "8000"}},
               {"id": 101, "at": (NOW - timedelta(days=1)).isoformat(), "data": {"Name": "C:\\Apps\\Updater.exe", "DegradationTime": "6000"}},
               {"id": 103, "at": (NOW - timedelta(days=1)).isoformat(), "data": {"Name": "Spooler", "FriendlyName": "Print Spooler", "DegradationTime": "2500"}},
               {"id": 101, "at": (NOW - timedelta(days=200)).isoformat(), "data": {"Name": "old.exe", "DegradationTime": "99000"}}]
        return {"events": ev}

    def test_trend_culprits_and_startup_match(self):
        dati = boot.read(runner(self.events()))
        startup = [{"id": "ab" * 8, "name": "Updater", "command": '"C:\\Apps\\Updater.exe" /min', "enabled": True, "location": "HKCU Run"}]
        d = boot.analyze(dati, startup, now=NOW)
        self.assertEqual(d["count"], 6)
        self.assertTrue(d["slower"])
        self.assertEqual(d["culprits"][0]["lost_seconds"], 14.0)
        self.assertEqual(d["culprits"][0]["times"], 2)
        self.assertEqual(d["culprits"][0]["startup"]["id"], "ab" * 8)
        self.assertIsNone(d["culprits"][1]["startup"])  # a service never matches a startup entry
        self.assertNotIn("old.exe", [c["name"] for c in d["culprits"]])


class FailureSigns(unittest.TestCase):
    def test_growing_and_steady(self):
        ev = [{"kind": "disk", "at": (NOW - timedelta(days=1, hours=i)).isoformat()} for i in range(5)]
        ev += [{"kind": "whea", "at": (NOW - timedelta(days=10 + i)).isoformat()} for i in range(8)]
        ev += [{"kind": "whea", "at": (NOW - timedelta(days=2)).isoformat()}]
        ev += [{"kind": "filesystem", "at": (NOW - timedelta(days=1)).isoformat()}]
        tendenze = {"disks": [{"name": "SSD", "worn_out": (NOW + timedelta(days=60)).date().isoformat(), "new_errors": 3}],
                    "batteries": [{"name": "BAT", "below_limit": (NOW + timedelta(days=900)).date().isoformat()}]}
        d = early_warning.evaluate(ev, tendenze, NOW)
        self.assertEqual(sorted(d["growing"]), ["disk", "filesystem"])
        whea = next(s for s in d["signals"] if s["kind"] == "whea")
        self.assertFalse(whea["growing"])  # 1 this week against 2 a week before
        self.assertEqual([p["kind"] for p in d["forecasts"]], ["disk_wear", "disk_errors"])
        self.assertIn("SSD", early_warning.alert_text(d))
        self.assertEqual(early_warning.evaluate([], {}, NOW)["level"], "ok")


SNAP_GOOD = {
    "run_keys": {"HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\OneDrive": "onedrive.exe", "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Gone": "gone.exe"},
    "startup_folders": {}, "services": {"Spooler": "Auto | spoolsv.exe", "Svc": "Manual | a.exe"}, "tasks": {}, "hosts": {"127.0.0.1 localhost": "line"},
    "proxy": {"ProxyEnable": "0", "ProxyServer": "", "AutoConfigURL": ""}, "defender_exclusions": {}, "extensions": {}, "admins": {"PC\\me": "Local"},
}
SNAP_NOW = {
    "run_keys": {"HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\OneDrive": "onedrive.exe", "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Evil": "C:\\Temp\\e.exe ' ; rm"},
    "startup_folders": {"C:\\Users\\me\\Startup\\x.lnk": "100"}, "services": {"Spooler": "Disabled | spoolsv.exe", "Svc": "Manual | b.exe", "NewSvc": "Auto | n.exe"},
    "tasks": {"\\Updater\\Run": "u.exe"}, "hosts": {"127.0.0.1 localhost": "line", "1.2.3.4 bank.com": "line"},
    "proxy": {"ProxyEnable": "1", "ProxyServer": "evil:8080", "AutoConfigURL": ""}, "defender_exclusions": {"path: C:\\Temp": "excluded"},
    "extensions": {"Chrome Default abc": "installed"}, "admins": {"PC\\me": "Local", "PC\\other": "Local"},
}


class GoodConfig(Temp):
    def test_snapshots_are_dated_and_pruned(self):
        for i in range(goodconfig.KEEP_DAYS + 3):
            goodconfig.save_snapshot(self.dir, SNAP_GOOD, NOW.date() - timedelta(days=i))
        giorni = goodconfig.days(self.dir)
        self.assertEqual(len(giorni), goodconfig.KEEP_DAYS)
        self.assertEqual(giorni[0], NOW.date().isoformat())
        self.assertEqual(goodconfig.load(self.dir, giorni[0])["services"]["Spooler"], "Auto | spoolsv.exe")
        with self.assertRaises(goodconfig.GoodConfigError):
            goodconfig.load(self.dir, "../../x")

    def test_plan_has_an_opposite_for_each_change(self):
        piano = goodconfig.build_plan(SNAP_GOOD, SNAP_NOW, "Q")
        tipi = sorted(o["do"]["kind"] for o in piano["ops"])
        self.assertEqual(tipi, sorted(["remove_value", "set_value", "move_file", "set_start", "set_start", "disable_task", "hosts_remove",
                                       "set_proxy", "set_proxy", "remove_exclusion"]))
        for o in piano["ops"]:
            self.assertTrue(goodconfig._valid(o["do"]) and goodconfig._valid(o["undo"]), o)
        spooler = next(o for o in piano["ops"] if o["item"] == "Spooler")
        self.assertEqual((spooler["do"]["mode"], spooler["undo"]["mode"]), ("auto", "disabled"))
        manuali = {(m["category"], m["item"]) for m in piano["manual"]}
        self.assertIn(("extensions", "Chrome Default abc"), manuali)
        self.assertIn(("admins", "PC\\other"), manuali)
        self.assertIn(("services", "Svc"), manuali)  # its program changed
        self.assertEqual(len({o["id"] for o in piano["ops"]}), len(piano["ops"]))

    def test_apply_keeps_the_opposites_and_revert_runs_them(self):
        piano = dict(goodconfig.build_plan(SNAP_GOOD, SNAP_NOW, "Q"), day="2026-11-01")
        script_visti = []

        def finto(script):
            script_visti.append(script)
            ops = json.loads(base64.b64decode(script.split("FromBase64String('")[1].split("'")[0]).decode("utf-8"))
            return json.dumps({"results": [{"ok": o["kind"] != "hosts_remove", "error": "" if o["kind"] != "hosts_remove" else "denied"} for o in ops]})
        scelte = [o["id"] for o in piano["ops"] if o["category"] in ("run_keys", "hosts")]
        esito = goodconfig.apply(self.dir, piano, scelte, finto)
        self.assertEqual((esito["done"], esito["failed"]), (2, 1))
        self.assertNotIn("rm", script_visti[0].split("FromBase64String")[0])  # the values never enter the script text
        self.assertEqual(goodconfig.last(self.dir)["count"], 2)
        indietro = goodconfig.revert(self.dir, finto)
        self.assertEqual(indietro["done"], 2)
        with self.assertRaises(goodconfig.GoodConfigError):
            goodconfig.revert(self.dir, finto)
        with self.assertRaises(goodconfig.GoodConfigError):
            goodconfig.apply(self.dir, piano, ["nope"], finto)

    def test_invalid_operations_are_refused(self):
        with self.assertRaises(goodconfig.GoodConfigError):
            goodconfig.run_ops([{"kind": "set_value", "path": "HKLM:\\SYSTEM\\CurrentControlSet", "name": "x", "value": "1"}], lambda s: "")
        with self.assertRaises(goodconfig.GoodConfigError):
            goodconfig.run_ops([{"kind": "format_disk"}], lambda s: "")
        self.assertEqual(goodconfig.run_ops([{"kind": "hosts_add", "line": "a"}], lambda s: "garbage")[0]["ok"], False)

    def test_undoable_runs_since_the_day(self):
        runs = [{"id": 1, "action_id": "a.b", "started": "2026-11-02T10:00:00", "undo_count": 2, "undone": None},
                {"id": 2, "action_id": "a.c", "started": "2026-10-01T10:00:00", "undo_count": 2, "undone": None},
                {"id": 3, "action_id": "a.d", "started": "2026-11-03T10:00:00", "undo_count": 0, "undone": None},
                {"id": 4, "action_id": "a.e", "started": "2026-11-03T10:00:00", "undo_count": 1, "undone": "2026-11-04"}]
        self.assertEqual([r["id"] for r in goodconfig.undoable_runs(runs, "2026-11-01")], [1])


class Suspicious(Temp):
    DATI = {"items": [
        {"source": "running", "name": "svchost.exe", "command": "", "path": "C:\\Users\\me\\AppData\\Roaming\\svchost.exe"},
        {"source": "running", "name": "conhost.exe", "command": "", "path": "\\\\?\\C:\\WINDOWS\\system32\\conhost.exe"},
        {"source": "run_key", "name": "Inv", "command": "C:\\Users\\me\\Downloads\\invoice.pdf.exe", "path": "C:\\Users\\me\\Downloads\\invoice.pdf.exe"},
        {"source": "task", "name": "\\T", "command": "powershell.exe -w hidden -enc AAAA", "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"},
        {"source": "service", "name": "Tool", "command": "C:\\Tools\\tool.exe", "path": "C:\\Tools\\tool.exe"},
        {"source": "service", "name": "Old", "command": "C:\\Program Files\\Old\\old.exe", "path": "C:\\Program Files\\Old\\old.exe"},
        {"source": "running", "name": "ok.exe", "command": "", "path": "C:\\Program Files\\Ok\\ok.exe"}],
        "files": [{"path": "C:\\Users\\me\\AppData\\Roaming\\svchost.exe", "status": "NotSigned", "sha256": "a" * 64},
                  {"path": "\\\\?\\C:\\WINDOWS\\system32\\conhost.exe", "status": "Valid", "sha256": "b" * 64},
                  {"path": "C:\\Users\\me\\Downloads\\invoice.pdf.exe", "status": "HashMismatch", "sha256": "c" * 64},
                  {"path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "status": "Valid", "sha256": "d" * 64},
                  {"path": "C:\\Tools\\tool.exe", "status": "NotSigned", "sha256": "e" * 64},
                  {"path": "C:\\Program Files\\Old\\old.exe", "status": "NotSigned", "sha256": "f" * 64},
                  {"path": "C:\\Program Files\\Ok\\ok.exe", "status": "Valid", "sha256": "0" * 64}]}

    def test_flags(self):
        righe = {r["path"]: r for r in suspicious.evaluate(self.DATI)}
        self.assertEqual(righe["C:\\Users\\me\\AppData\\Roaming\\svchost.exe"]["flags"], ["system_name", "risky_folder", "unsigned"])
        self.assertNotIn("C:\\WINDOWS\\system32\\conhost.exe", righe)  # the \\?\ form of a Windows file is fine
        self.assertEqual(set(righe["C:\\Users\\me\\Downloads\\invoice.pdf.exe"]["flags"]), {"bad_signature", "risky_folder", "double_extension"})
        self.assertEqual(righe["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"]["flags"], ["hidden_script"])
        self.assertEqual(righe["C:\\Tools\\tool.exe"]["level"], "medium")
        self.assertEqual(righe["C:\\Program Files\\Old\\old.exe"]["level"], "low")
        self.assertNotIn("C:\\Program Files\\Ok\\ok.exe", righe)
        self.assertEqual(list(righe)[0][:3], "C:\\")
        self.assertEqual(righe["C:\\Tools\\tool.exe"]["reasons_it"][0], "Non firmato e fuori da Programmi.")

    def test_virustotal_only_hashes_cache_and_limit(self):
        with self.assertRaises(ValueError):
            suspicious.save_settings(self.dir, "not-a-key")
        suspicious.save_settings(self.dir, "1" * 64)
        self.assertNotIn("1" * 64, (self.dir / "suspicious.json").read_text())
        chiesti = []

        def finto(chiave, h):
            chiesti.append((chiave, h))
            return {"known": True, "malicious": 5 if h == "e" * 64 else 0, "suspicious": 0, "engines": 70}
        righe = [{"sha256": f"{i:x}" * 64, "level": "medium"} for i in range(6)] + [{"sha256": "e" * 64, "level": "medium"}, {"sha256": "9" * 64, "level": "low"}]
        self.assertEqual(suspicious.add_reputation(self.dir, righe, finto), suspicious.VT_PER_CHECK)
        self.assertTrue(all(k == "1" * 64 and len(h) == 64 for k, h in chiesti))
        righe2 = [{"sha256": "0" * 64, "level": "medium"}, {"sha256": "e" * 64, "level": "medium"}]
        self.assertEqual(suspicious.add_reputation(self.dir, righe2, finto), 1)  # the first comes from the cache
        self.assertEqual(righe2[1]["level"], "high")
        suspicious.save_settings(self.dir, "")
        self.assertFalse(suspicious.settings(self.dir)["virustotal"])


def sign_phone(secret, method, path, body=b"", device="ab" * 8):
    t, n = str(int(time.time())), secrets.token_hex(8)
    return {phone.SIG_HEADER: fleet.signature(secret, method, path, t, n, body), phone.TIME_HEADER: t, phone.NONCE_HEADER: n, phone.DEVICE_HEADER: device}


class PhoneConsole(Temp):
    def setUp(self):
        super().setUp()
        self.phones = phone.for_data_dir(self.dir)
        self.phones.configure(True, 8767)
        self.started = []
        self.server = phone.phone_server(self.phones, 0, lambda: {"hostname": "PC", "overall": 90, "secret": "x"},
                                         lambda: [{"title": "Fix <b>", "area": "cleanup", "risk": "safe"}],
                                         lambda ids: self.started.append(ids) or "cd" * 16,
                                         lambda job: {"id": job, "active": False, "done": 1, "total": 1, "results": []})
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, method, path, secret, body=None, device="ab" * 8, headers=None):
        dati = json.dumps(body).encode() if body is not None else b""
        h = headers or sign_phone(secret, method, path, dati, device)
        req = urllib.request.Request(self.base + path, data=dati if body is not None else None, method=method, headers=dict(h, **{"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_page_is_served_with_a_strict_policy(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as r:
            self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
            self.assertIn(b"/phone.js", r.read())

    def test_pairing_signed_calls_and_limits(self):
        self.assertEqual(self.call("GET", "/phone/v1/summary", "WRONGCODEWRONG12")[0], 403)
        codice = phone.normalize(self.phones.new_code())
        self.assertEqual(len(codice), 16)
        self.assertNotIn(codice, (self.dir / "phone.json").read_text())
        self.assertEqual(self.call("POST", "/phone/v1/hello", codice, {})[0], 200)
        self.assertEqual(len(self.phones.state()["devices"]), 1)
        self.assertIsNone(self.phones.state()["pairing_until"])  # the code works once
        self.assertEqual(self.call("POST", "/phone/v1/hello", codice, {}, device="cd" * 8)[0], 403)
        stato, d = self.call("GET", "/phone/v1/summary", codice)
        self.assertEqual((stato, d["summary"]["overall"]), (200, 90))
        self.assertNotIn("secret", d["summary"])
        strumenti = self.call("GET", "/phone/v1/tools", codice)[1]["tools"]
        self.assertTrue(all(fleet.allowed("safe", actions.CATALOG[t["id"]]) for t in strumenti))
        self.assertEqual(self.call("POST", "/phone/v1/runs", codice, {"actions": ["network.reset"]})[0], 403)
        self.assertEqual(self.call("POST", "/phone/v1/runs", codice, {"actions": ["network.flush_dns"]})[0], 202)
        self.assertEqual(self.started, [["network.flush_dns"]])
        self.assertEqual(self.call("GET", "/phone/v1/runs/" + "cd" * 16, codice)[0], 200)
        h = sign_phone(codice, "GET", "/phone/v1/summary")
        self.assertEqual(self.call("GET", "/phone/v1/summary", codice, headers=h)[0], 200)
        self.assertEqual(self.call("GET", "/phone/v1/summary", codice, headers=h)[0], 403)  # replayed
        self.assertTrue(self.phones.remove("ab" * 8))
        self.assertEqual(self.call("GET", "/phone/v1/summary", codice)[0], 403)

    def test_expired_code_and_old_timestamp(self):
        codice = phone.normalize(self.phones.new_code(now=time.time() - phone.PAIR_SECONDS - 5))
        self.assertEqual(self.call("POST", "/phone/v1/hello", codice, {})[0], 403)
        codice = phone.normalize(self.phones.new_code())
        vecchio = str(int(time.time()) - 600)
        firma = fleet.signature(codice, "POST", "/phone/v1/hello", vecchio, "n" * 12, b"{}")
        self.assertIsNone(self.phones.verify("POST", "/phone/v1/hello", "ab" * 8, vecchio, "n" * 12, b"{}", firma))

    def test_javascript_signature_matches_python(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed")
        messaggio = "GET\n/phone/v1/summary\n1700000000\nabcdef12\n{\"a\":\"è\"}"
        js = subprocess.run(["node", "-e", f"require({json.dumps(str(ROOT / 'wmm/web/js/phone.js'))});"
                             f"process.stdout.write(WMMPhone.hmac('ABCDEFGHJKLMNPQR', {json.dumps(messaggio)}))"],
                            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        import hmac
        atteso = hmac.new(b"ABCDEFGHJKLMNPQR", messaggio.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(js.stdout.strip(), atteso)


class TwoRealPCs(Temp):
    """The other PC runs in its own Python process with its own data folder, key and port: the console talks to it over
    TCP exactly as it would to another PC of the network."""

    def setUp(self):
        super().setUp()
        (self.dir / "peer").mkdir()
        self.peer = subprocess.Popen([sys.executable, str(ROOT / "tests" / "fleet_peer.py"), str(self.dir / "peer")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, cwd=str(ROOT))
        info = json.loads(self.peer.stdout.readline())
        self.console = fleet.Fleet(self.dir / "console.json")
        self.pc = self.console.add("Peer", "127.0.0.1", info["port"], info["key"])
        self.port = info["port"]

    def tearDown(self):
        self.peer.stdin.close()
        self.peer.wait(timeout=10)
        self.peer.stdout.close()
        super().tearDown()

    def test_summary_runs_and_refusals_across_processes(self):
        voce = next(p for p in self.console.gather() if p["id"] == self.pc["id"])
        self.assertEqual((voce["status"], voce["summary"]["hostname"]), ("online", "PEER"))
        job = self.console.run_remote(self.pc["id"], ["network.flush_dns"])["id"]
        stato = self.console.run_status(self.pc["id"], job)
        self.assertEqual(stato["results"][0]["verify"]["verdict"], "fixed")
        with self.assertRaises(fleet.FleetError):
            self.console.run_remote(self.pc["id"], ["network.reset"])  # moderate: refused by the other PC
        with self.assertRaises(fleet.FleetError):
            fleet.fetch_summary("127.0.0.1", self.port, "wrong-key-wrong-key-123")

    def test_a_captured_request_cannot_be_replayed(self):
        dati = b'{"actions": ["network.flush_dns"]}'
        t, n = str(int(time.time())), secrets.token_hex(12)
        chiave = notify.unprotect(self.console._pc(self.pc["id"])["key"])
        h = {fleet.SIG_HEADER: fleet.signature(fleet.key_hash(chiave), "POST", fleet.RUN_PATH, t, n, dati), fleet.TIME_HEADER: t,
             fleet.NONCE_HEADER: n, "Content-Type": "application/json"}
        codici = []
        for _ in range(2):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}{fleet.RUN_PATH}", data=dati, headers=h, method="POST"), timeout=5) as r:
                    codici.append(r.status)
            except urllib.error.HTTPError as e:
                codici.append(e.code)
        self.assertEqual(codici, [202, 403])

    def test_batch_on_this_pc_and_the_peer(self):
        locali = {}

        def qui(ids):
            locali["job"] = "ef" * 16
            return locali["job"]
        lotto = fleet.start_batch(self.console, [fleet.THIS_PC, self.pc["id"], "000000000000"], ["network.flush_dns", "network.speed_test"], qui)
        righe = {r["pc_id"]: r for r in lotto["rows"]}
        self.assertEqual(righe[fleet.THIS_PC]["job_id"], "ef" * 16)
        self.assertTrue(righe[self.pc["id"]]["job_id"])
        self.assertEqual(righe["000000000000"]["error"], "PC not found")
        stato = fleet.batch_status(self.console, lotto, lambda job: {"id": job, "active": True, "done": 0, "total": 2, "results": []})
        self.assertTrue(stato["active"])
        peer = next(r for r in stato["rows"] if r["pc_id"] == self.pc["id"])
        self.assertEqual([x["action_id"] for x in peer["results"]], ["network.flush_dns", "network.speed_test"])
        with self.assertRaises(fleet.FleetError):
            fleet.start_batch(self.console, [], ["network.flush_dns"])


class PeriodicReport(Temp):
    def data(self):
        return {"start": "2026-10-29T12:00:00", "end": "2026-11-05T12:00:00", "scores": {"cleanup": 90, "security": 70}, "changes": {"cleanup": 5, "security": None},
                "overall": 80, "c_free_gb": 50.5, "runs": {"total": 3, "ok": 2, "warning": 0, "error": 1, "checked": 2, "fixed": 1, "not_fixed": 1,
                                                           "failed": [{"action_id": "network.flush_dns", "note": "denied"}]},
                "outages": [{"from": "a", "until": "b", "cause": "dns"}], "drift": 2, "bsod": 0,
                "signals": [{"title": "Disk errors and retries", "title_it": "Errori e tentativi del disco", "growing": True}],
                "forecasts": [{"text": "SSD worn", "text_it": "SSD consumato"}], "alerts": ["config_changed"], "disks": []}

    def test_render_in_both_languages(self):
        titolo, testo = digest.render(self.data(), "it", "PC1", {"network.flush_dns": "Flush DNS"})
        self.assertEqual(titolo, "Rapporto del PC PC1: 2026-10-29 – 2026-11-05")
        self.assertIn("Pulizia: 90 (+5)", testo)
        self.assertIn("Falliti: Flush DNS — denied", testo)
        self.assertIn("Errori e tentativi del disco", testo)
        titolo, testo = digest.render(self.data(), "en", "PC1")
        self.assertIn("Cleanup: 90 (+5)", testo)
        self.assertIn("SSD worn", testo)

    def test_period_moves_only_when_delivered(self):
        dati = self.data()
        import wmm.agent.digest as d
        originale = d.collect
        d.collect = lambda *a, **k: dati
        try:
            esito = digest.send(self.dir, sender=lambda t, x: {"email": "refused"}, now=NOW)
            self.assertFalse(esito["sent"])
            self.assertIsNone(digest.settings(self.dir)["last_sent"])
            esito = digest.send(self.dir, sender=lambda t, x: {"telegram": "ok"}, now=NOW)
            self.assertTrue(esito["sent"])
            self.assertEqual(digest.settings(self.dir)["last_sent"], dati["end"])
        finally:
            d.collect = originale
        with self.assertRaises(ValueError):
            digest.save_settings(self.dir, "fr")


def block(**kw):
    return SimpleNamespace(**kw)


class Assistant(Temp):
    def kit(self):
        self.reports = []
        return assistant.Toolkit(actions.CATALOG, lambda i: self.reports.append(i) or {"log": ["line"], "status": "ok", "note": ""},
                                 lambda: {"overall": 80}, lambda s: {"symptom": s}, lambda q: [{"id": "slow_pc"}])

    def test_tools_read_only_and_proposals_filtered(self):
        k = self.kit()
        self.assertIn("error", json.loads(k.call("run_report", {"tool_id": "network.flush_dns"})))  # a fix never runs here
        self.assertEqual(json.loads(k.call("run_report", {"tool_id": "network.speed_test"}))["output"], "line")
        self.assertEqual(self.reports, ["network.speed_test"])
        k.call("propose_fixes", {"fixes": [{"tool_id": "network.flush_dns", "reason": "r"}, {"tool_id": "network.speed_test", "reason": "report"},
                                           {"tool_id": "nope", "reason": ""}, {"tool_id": "network.flush_dns", "reason": "again"}]})
        self.assertEqual([p["action_id"] for p in k.proposals], ["network.flush_dns"])
        self.assertTrue(json.loads(k.call("find_tools", {"query": "dns cache", "kind": "fix"})))
        for t in assistant.TOOLS:
            self.assertFalse(t["input_schema"]["additionalProperties"])

    def test_turn_loop_with_tools(self):
        risposte = [block(stop_reason="tool_use", content=[block(type="text", text="checking"),
                                                            block(type="tool_use", id="t1", name="run_report", input={"tool_id": "network.speed_test"}),
                                                            block(type="tool_use", id="t2", name="propose_fixes", input={"fixes": [{"tool_id": "network.flush_dns", "reason": "x"}]})]),
                    block(stop_reason="end_turn", content=[block(type="thinking", thinking=""), block(type="text", text="Try flushing DNS.")])]
        visti = []

        def crea(**kw):
            visti.append(kw)
            return risposte[len(visti) - 1]
        k = self.kit()
        messaggi = [{"role": "user", "content": "internet slow"}]
        self.assertEqual(assistant.turn(None, messaggi, k, crea), "Try flushing DNS.")
        self.assertEqual(visti[0]["model"], "claude-opus-5-5")
        self.assertNotIn("tool_choice", visti[0])
        risultati = messaggi[2]["content"]
        self.assertEqual([r["tool_use_id"] for r in risultati], ["t1", "t2"])  # all results in one user message
        self.assertEqual(k.proposals[0]["action_id"], "network.flush_dns")

    def test_refusal_and_old_sdk(self):
        def crea(**kw):
            if "fallbacks" in kw:
                raise TypeError("unexpected keyword")
            return block(stop_reason="refusal", content=[])
        self.assertIn("declined", assistant.turn(None, [{"role": "user", "content": "x"}], self.kit(), crea))

    def test_key_is_encrypted_and_conversation_runs_in_background(self):
        with self.assertRaises(assistant.AssistantError):
            assistant.save_key(self.dir, "abc")
        assistant.save_key(self.dir, "sk-ant-" + "x" * 30)
        self.assertNotIn("sk-ant-", (self.dir / "assistant.json").read_text())
        self.assertTrue(assistant.settings(self.dir)["configured"])
        conv = assistant.Conversations()
        v = conv.start(None, "slow", lambda: None, self.kit, create=lambda **kw: block(stop_reason="end_turn", content=[block(type="text", text="ok")]))
        for _ in range(50):
            if conv.view(v["id"])["state"] != "working":
                break
            time.sleep(0.05)
        vista = conv.view(v["id"])
        self.assertEqual([m["role"] for m in vista["history"]], ["user", "assistant"])
        with self.assertRaises(assistant.AssistantError):
            conv.start(v["id"], "", lambda: None, self.kit)


class Catalog(unittest.TestCase):
    def test_new_reports_and_routes(self):
        for a in actions.WATCH_28:
            self.assertEqual(actions.CATALOG[a].kind, "report")
        self.assertIn("early_warning", notify.EVENTS)
        percorsi = [("GET", "/api/v1/integrity/crashes"), ("GET", "/api/v1/startup/boot"), ("POST", "/api/v1/security/good-config/plan"),
                    ("PUT", "/api/v1/security/suspicious/settings"), ("POST", "/api/v1/digest/send"), ("GET", "/api/v1/assistant/chat/" + "a" * 16),
                    ("DELETE", "/api/v1/phone/devices/" + "a" * 16), ("GET", "/api/v1/fleet/batch/" + "a" * 16)]
        for metodo, percorso in percorsi:
            self.assertTrue(any(m == metodo and s.fullmatch(percorso) for m, s, f in api.ROUTES), percorso)


if __name__ == "__main__":
    unittest.main()
