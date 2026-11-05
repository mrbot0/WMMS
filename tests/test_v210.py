"""Tests for 2.10: company sign-in, approvals, API tokens, audit chain, SIEM, HTTPS, encrypted data, ransomware decoys,
automatic undo, central server (a real HTTPS round trip), deployment, update rings, baselines, tickets, incidents and
the executive PDF. Nothing changes the PC."""
import base64
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from wmm.agent import (accounts as A, appsettings, baselines, canary, central, deploy, governance, incidents, pdfreport, securestore, sso, tickets,
                       tlsutil, updatepolicy)
from tests import test_api

PW = "Str0ng!Passw0rd"


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.acc = A.Accounts(self.dir / "accounts.db")
        self.admin = self.acc.setup("admin", PW)

    def tearDown(self):
        self.tmp.cleanup()

    def me(self, user="admin", pw=PW):
        return self.acc.session(self.acc.login(user, pw)["token"])


class AuditAndTokens(Temp):
    def test_chain_detects_changes_and_deletions(self):
        self.acc.create_user({"username": "zoe", "role_id": "viewer"})
        self.assertTrue(governance.verify(self.acc)["ok"])
        import sqlite3
        db = sqlite3.connect(self.dir / "accounts.db")
        db.execute("DELETE FROM audit WHERE id = 2")
        db.commit()
        db.close()
        self.assertEqual(governance.verify(self.acc)["broken"]["reason"], "an entry before this one was deleted or changed")

    def test_hooks_and_syslog(self):
        visti = []
        self.acc.audit_hooks.append(visti.append)
        self.acc.audit("x", "test.action", "t", "d")
        self.assertEqual(visti[-1]["action"], "test.action")
        riga = governance.syslog_line({"at": "2026-11-05T10:00:00", "user": 'a"b', "action": "login.fail", "target": "", "detail": "x", "ok": False}, "PC")
        self.assertTrue(riga.startswith(b"<36>1 2026-11-05T10:00:00 PC WMM"))
        self.assertIn(b'user="a\\"b"', riga)
        with self.assertRaises(governance.GovernanceError):
            governance.save_siem(self.dir, {"syslog_host": "bad host!", "syslog_port": 514})

    def test_tokens_scoped_and_revoked(self):
        me = self.me()
        t = governance.create_token(self.acc, me, "ci", ["view.dashboard", "run.cleanup.report"], 30)
        self.assertTrue(t["token"].startswith("wmm_"))
        u = governance.token_user(self.acc, t["token"])
        self.assertEqual(u["permissions"], ["run.cleanup.report", "view.dashboard"])
        self.assertNotIn(t["token"], (self.dir / "accounts.db").read_bytes().decode("latin-1"))
        viewer = self.acc.create_user({"username": "vv", "role_id": "viewer", "password": "V1ewer!Pass26"})
        with self.assertRaises(governance.GovernanceError):
            governance.create_token(self.acc, self.me("vv", "V1ewer!Pass26"), "x", ["registry.edit"])
        governance.revoke_token(self.acc, t["id"], me)
        self.assertIsNone(governance.token_user(self.acc, t["token"]))
        self.assertTrue(viewer)

    def test_approvals_need_another_person(self):
        me = self.me()
        req = governance.request(self.acc, me, ["network.reset"], "TICKET-9")
        with self.assertRaises(governance.GovernanceError):
            governance.decide(self.acc, req["id"], me, True)
        self.acc.create_user({"username": "boss", "role_id": "admin", "password": "B0ss!Password"})
        avviati = []
        esito = governance.decide(self.acc, req["id"], self.me("boss", "B0ss!Password"), True, "ok", lambda ids, u: avviati.append(ids) or "job1")
        self.assertEqual((esito["status"], esito["job_id"], avviati), ("approved", "job1", [["network.reset"]]))
        with self.assertRaises(governance.GovernanceError):
            governance.decide(self.acc, req["id"], self.me("boss", "B0ss!Password"), False)


class CompanySignIn(Temp):
    def setUp(self):
        super().setUp()
        sso.save(self.dir, {"oidc_enabled": True, "issuer": "https://login.example.com/t/v2.0", "client_id": "app-123",
                            "role_map": {"WMM-Admins": "admin", "WMM-Tech": "technician"}, "default_role": ""}, ["admin", "technician", "viewer"])

    def flow(self, claims_override=None):
        conf = {"authorization_endpoint": "https://login.example.com/auth", "token_endpoint": "https://login.example.com/token"}
        url = sso.start(self.dir, "http://127.0.0.1:8765/api/v1/auth/oidc/callback", fetch=lambda u: conf)
        import urllib.parse
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(q["code_challenge_method"], "S256")
        voce = sso._PENDING[q["state"]]
        claims = {"iss": "https://login.example.com/t/v2.0", "aud": "app-123", "exp": time.time() + 600, "nonce": voce["nonce"], "sub": "S1",
                  "preferred_username": "mario.rossi@company.com", "name": "Mario Rossi", "groups": ["WMM-Tech"]}
        claims.update(claims_override or {})
        token = "x." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".y"
        visti = {}

        def post(url_t, campi):
            visti.update(campi)
            return {"id_token": token}
        c = sso.finish(self.dir, q["state"], "CODE", post=post)
        self.assertEqual(visti["code_verifier"], voce["verifier"])
        return c

    def test_oidc_creates_the_user_with_the_mapped_role(self):
        c = self.flow()
        ident = sso.oidc_identity(self.dir, c)
        r = self.acc.login_external(ident, metodo="entra")
        self.assertEqual((r["user"]["username"], r["user"]["role_id"]), ("mario.rossi", "technician"))
        self.assertIsNotNone(self.acc.session(r["token"]))
        r2 = self.acc.login_external(dict(ident, role="admin"), metodo="entra")  # the role follows the groups
        self.assertEqual(r2["user"]["role_id"], "admin")

    def test_oidc_refuses_wrong_tokens_and_unmapped_people(self):
        with self.assertRaises(sso.SsoError):
            self.flow({"aud": "other-app"})
        with self.assertRaises(sso.SsoError):
            self.flow({"nonce": "replayed"})
        ident = sso.oidc_identity(self.dir, self.flow({"groups": ["Sales"], "sub": "S2"}))
        with self.assertRaises(A.AccountError):
            self.acc.login_external(ident)
        with self.assertRaises(sso.SsoError):
            sso.finish(self.dir, "unknown-state", "CODE", post=lambda u, c: {})

    def test_never_linked_by_name_to_a_local_user(self):
        ident = {"subject": "oidc:evil", "username": "admin", "display": "x", "email": "", "role": "viewer"}
        r = self.acc.login_external(ident)
        self.assertNotEqual(r["user"]["id"], self.admin["id"])
        self.assertEqual(r["user"]["role_id"], "viewer")

    def test_windows_wrong_password(self):
        self.assertIsNone(sso.windows_logon("wmm-no-such-user-test", "nope"))
        self.assertEqual(sso.map_role(["BUILTIN\\Administrators", "Users"], {"Users": "viewer", "Administrators": "admin"}, ""), "viewer")


class SecurityReview210(Temp):
    def test_tokens_cannot_mint_tokens_and_scopes_are_fixed(self):
        me = self.me()
        t = governance.create_token(self.acc, me, "narrow", ["view.dashboard"])
        with self.assertRaises(governance.GovernanceError):
            governance.create_token(self.acc, governance.token_user(self.acc, t["token"]), "wide", [])
        pieno = governance.create_token(self.acc, me, "all", [])
        self.assertEqual(sorted(pieno["scopes"]), sorted(me["permissions"]))

    def test_issuer_always_checked(self):
        with self.assertRaises(sso.SsoError):
            sso.save(self.dir, {"issuer": "https://login.microsoftonline.com/common/v2.0"}, ["admin"])
        with self.assertRaises(sso.SsoError):
            sso.save(self.dir, {"issuer": "https://login.microsoftonline.com/organizations/v2.0"}, ["admin"])

    def test_ring_needs_level_everything(self):
        chiamate = []
        cartella = self.dir / "ag"
        cartella.mkdir()
        central._client_write(cartella, server="h", port=1, fingerprint="AA", agent_id="a1", secret=__import__("wmm.agent.notify", fromlist=["x"]).protect("s"), level="safe")
        client = central.Client(cartella, lambda j: {}, lambda: {}, "PC", "M", "2.10.0")
        risposta = {"jobs": [], "ring": {"name": "Pilot", "quality_days": 3, "feature_days": 0, "active_hours": "8-18"}}
        with mock.patch.object(updatepolicy, "apply_ring", side_effect=lambda r, preview: chiamate.append(r)), \
                mock.patch.object(central, "collect_inventory", return_value={}):
            client.contact(req=lambda *a: risposta)
            self.assertEqual(chiamate, [])
            central.set_client(cartella, level="all")
            client.contact(req=lambda *a: risposta)
        self.assertEqual(chiamate[0]["name"], "Pilot")


class Https(unittest.TestCase):
    def test_certificate_and_pinning(self):
        import http.server
        import socketserver
        import threading
        with tempfile.TemporaryDirectory() as d:
            info = tlsutil.ensure(Path(d))

            class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
                daemon_threads = True
            s = S(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
            tlsutil.wrap(s, Path(d))
            threading.Thread(target=s.serve_forever, daemon=True).start()
            c, fp = tlsutil.pinned_connection("127.0.0.1", s.server_address[1], info["fingerprint"])
            c.close()
            self.assertEqual(fp, info["fingerprint"])
            with self.assertRaises(tlsutil.PinError):
                tlsutil.pinned_connection("127.0.0.1", s.server_address[1], "00" * 32)
            s.shutdown()
            s.server_close()


class EncryptionAndRansomware(unittest.TestCase):
    def test_securestore_roundtrip_and_convert(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wifi_history.json"
            securestore.write_text(p, '{"a": "Wi-Fi è"}', encrypt=True)
            self.assertTrue(p.read_bytes().startswith(securestore.MAGIC))
            self.assertNotIn(b"Wi-Fi", p.read_bytes())
            self.assertEqual(json.loads(securestore.read_text(p))["a"], "Wi-Fi è")
            self.assertEqual(securestore.convert(Path(d), False), ["wifi_history.json"])
            self.assertTrue(p.read_bytes().startswith(b"{"))
            securestore.set_cached(False)

    def test_decoys_detect_changes(self):
        with tempfile.TemporaryDirectory() as d:
            casa = Path(d) / "home"
            for c in ("Documents", "Desktop", "Pictures"):
                (casa / c).mkdir(parents=True)
            voci = canary.place(Path(d), casa)
            self.assertEqual(len(voci), 4)
            self.assertEqual(canary.check(Path(d))["tripped"], [])
            with open(voci[0]["path"], "r+b") as f:  # what a ransomware does: rewrites the content in place
                f.write(b"encrypted!!")
            Path(voci[1]["path"]).unlink()
            self.assertEqual(sorted(t["change"] for t in canary.check(Path(d))["tripped"]), ["missing", "modified"])


class Central(unittest.TestCase):
    """A real round trip: the server over HTTPS with its own certificate, an agent enrolling and contacting it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.srv_dir, self.ag_dir = Path(self.tmp.name) / "srv", Path(self.tmp.name) / "agent"
        self.srv_dir.mkdir()
        self.ag_dir.mkdir()
        self.server = central.Server(self.srv_dir)
        self.http = central.server_http(self.server, 0, self.srv_dir, tls=True)
        self.port = self.http.server_address[1]
        self.fp = tlsutil.ensure(self.srv_dir)["fingerprint"]

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.tmp.cleanup()

    def test_enroll_jobs_and_results(self):
        codice = self.server.enrollment_code("127.0.0.1", self.port, self.fp, ["Office"])["code"]
        self.assertNotIn(codice.split("-")[1][:20], json.dumps(self.server.agents()))
        stato = central.enroll(self.ag_dir, codice, "PC-01", "M-1")
        self.assertTrue(stato["enrolled"])
        with self.assertRaises(central.CentralError):
            central.enroll(self.ag_dir, codice, "PC-02", "M-2")  # the code works once
        agente = self.server.agents()[0]
        self.assertEqual((agente["hostname"], agente["tags"]), ("PC-01", ["Office"]))
        self.server.queue([agente["id"]], "actions", {"actions": ["network.speed_test"]})
        self.server.queue([agente["id"]], "actions", {"actions": ["network.reset"]})
        eseguiti = []
        client = central.Client(self.ag_dir, lambda j: eseguiti.append(j) or {"results": [{"action_id": "network.speed_test", "status": "ok"}]},
                                lambda: {"overall": 77, "scores": {"cleanup": 80}}, "PC-01", "M-1", "2.10.0")
        with mock.patch.object(central, "collect_inventory", return_value={"hardware": {"model": "X1", "serial": "S9"}, "software": [{"name": "7-Zip", "version": "24"}]}):
            client.contact()
            client.contact()  # sends the results of the first contact
        self.assertEqual([j["payload"]["actions"] for j in eseguiti], [["network.speed_test"]])  # network.reset refused by this PC (level safe)
        jobs = {j["payload"]["actions"][0]: j for j in self.server.recent_jobs()}
        self.assertEqual(jobs["network.speed_test"]["status"], "done")
        self.assertEqual(jobs["network.reset"]["status"], "error")
        self.assertIn("not allowed", jobs["network.reset"]["result"]["error"])
        self.assertEqual(self.server.agents()[0]["overall"], 77)
        self.assertEqual(self.server.software_search("7-zip")[0]["hostname"], "PC-01")
        self.assertIn("X1", self.server.inventory_csv())

    def test_wrong_fingerprint_and_signature_are_refused(self):
        codice = self.server.enrollment_code("127.0.0.1", self.port, "AB" * 32)["code"]
        with self.assertRaises(tlsutil.PinError):
            central.enroll(self.ag_dir, codice, "PC-01", "M-1")
        self.assertIsNone(self.server.authenticate("a" + "0" * 16, "POST", "/x", str(int(time.time())), "n" * 12, b"{}", "sig"))

    def test_groups_assets_rings_catalog(self):
        a = self.server.enroll.__self__  # the same server object
        with mock.patch.object(central.Server, "_fresh", return_value=True):
            codice = self.server.enrollment_code("h", 1, self.fp)["code"]
            ident, segreto = codice.split("/")[3].split("#")[0].split("-")
            corpo = json.dumps({"hostname": "PC-02", "machine_id": "M-2"}).encode()
            from wmm.agent.fleet import signature
            r = self.server.enroll(ident, "1", "n" * 12, corpo, signature(segreto, "POST", central.API + "/enroll", "1", "n" * 12, corpo))
        self.assertTrue(r["secret"] and a)
        self.assertEqual(self.server.set_tags(r["agent_id"], ["Lab", "Lab", "Floor 2"]), ["Floor 2", "Lab"])
        with self.assertRaises(central.CentralError):
            self.server.set_tags(r["agent_id"], ["<script>"])
        self.server.set_asset(r["agent_id"], {"asset_tag": "A-12", "warranty_until": "2020-01-01"})
        self.assertEqual(self.server.overview()["warranty_expired"], 1)
        anello = self.server.save_ring({"name": "Pilot", "quality_days": 0, "feature_days": 30, "active_hours": "8-18"})
        self.server.save_group({"name": "Lab", "ring": anello["id"]})
        self.assertEqual(self.server.agents()[0]["ring"], anello["id"])
        self.server.save_catalog({"winget_id": "7zip.7zip", "name": "7-Zip"})
        with self.assertRaises(central.CentralError):
            self.server.save_catalog({"winget_id": "rm -rf"})
        self.assertEqual(self.server.targets(gruppo="Lab"), [r["agent_id"]])

    def test_this_pc_decides_what_it_runs(self):
        self.assertIsNone(central.allowed_job("reports", {"kind": "actions", "payload": {"actions": ["network.speed_test"]}}))
        self.assertTrue(central.allowed_job("reports", {"kind": "actions", "payload": {"actions": ["network.flush_dns"]}}))
        self.assertIsNone(central.allowed_job("safe", {"kind": "actions", "payload": {"actions": ["network.flush_dns"]}}))
        self.assertTrue(central.allowed_job("safe", {"kind": "winget", "payload": {"id": "x.y"}}))
        self.assertIsNone(central.allowed_job("all", {"kind": "winget", "payload": {"id": "x.y"}}))
        self.assertTrue(central.allowed_job("all", {"kind": "actions", "payload": {"actions": ["custom.ab12cd34"]}}))


class SoftwareUpdatesBaselines(unittest.TestCase):
    def test_winget(self):
        self.assertTrue(deploy.valid_id("Mozilla.Firefox"))
        for cattivo in ("firefox", "a.b; rm", "--force.x", "x" * 130 + ".y"):
            self.assertFalse(deploy.valid_id(cattivo), cattivo)
        self.assertIn("--accept-package-agreements", deploy.command("install", "Mozilla.Firefox"))
        r = deploy.run("install", "Mozilla.Firefox", runner=lambda c: SimpleNamespace(returncode=0, stdout="Successfully installed", stderr=""))
        self.assertTrue(r["ok"])
        r = deploy.run("upgrade", "Mozilla.Firefox", runner=lambda c: SimpleNamespace(returncode=-1978335189, stdout="No applicable update", stderr=""))
        self.assertTrue(r["ok"])

    def test_rings(self):
        r = updatepolicy.clean_ring({"name": "Broad", "quality_days": 7, "feature_days": 90, "target_version": "24h2", "active_hours": "7-19"})
        self.assertEqual(r["target_version"], "24H2")
        for cattivo in ({"name": "x", "quality_days": 31}, {"name": "x", "target_version": "Win11"}, {"name": "x", "active_hours": "0-23"},
                        {"name": "x", "paused_until": (datetime.now() + timedelta(days=60)).date().isoformat()}):
            with self.assertRaises(ValueError):
                updatepolicy.clean_ring(cattivo)
        scritti = []
        esito = updatepolicy.apply_ring(r, writer=lambda root, key, name, value: scritti.append((root, name, value)))
        self.assertIn(("HKLM", "DeferQualityUpdatesPeriodInDays", 7), scritti)
        self.assertIn(("HKLM", "TargetReleaseVersionInfo", "24H2"), scritti)
        self.assertFalse(esito["preview"])

    def test_baselines(self):
        with tempfile.TemporaryDirectory() as d:
            elenco = baselines.baselines(Path(d))
            self.assertTrue(elenco[0]["checks"])
            controlli = elenco[0]["checks"][:3]
            from wmm.agent import verify
            sani = {verify.CHECKS[c].script: next(v for v in ("On", "Running", "1", "0", "Enabled", "True", "Off", "Disabled", "False", "Stopped") if verify.CHECKS[c].ok(v))
                    for c in controlli if any(verify.CHECKS[c].ok(v) for v in ("On", "Running", "1", "0", "Enabled", "True", "Off", "Disabled", "False", "Stopped"))}
            esito = baselines.evaluate(controlli, runner=lambda s: sani.get(s))
            self.assertIsNotNone(esito["percent"])
            nuovo = baselines.save(Path(d), {"name": "Mine", "checks": controlli})
            with self.assertRaises(ValueError):
                baselines.save(Path(d), {"name": "x", "checks": ["nope"]})
            with self.assertRaises(ValueError):
                baselines.save(Path(d), {"name": "Edit", "checks": controlli}, "security")
            baselines.delete(Path(d), nuovo["id"])


class TicketsIncidentsReport(unittest.TestCase):
    def test_ticket_requests(self):
        s = {"kind": "jira", "url": "https://x.atlassian.net", "user": "u@x.com", "project": "OPS", "issue_type": "Task"}
        r = tickets.request_for(s, "tok", "Title", "Text")
        self.assertEqual(r.full_url, "https://x.atlassian.net/rest/api/2/issue")
        self.assertEqual(json.loads(r.data)["fields"]["project"]["key"], "OPS")
        self.assertEqual(tickets.ticket_id("servicenow", {"result": {"number": "INC0012"}}), "INC0012")
        self.assertTrue(tickets.request_for(dict(s, kind="glpi", project="app"), "t", "a", "b").get_header("App-token"))
        with self.assertRaises(ValueError):
            tickets.save(Path(tempfile.mkdtemp()), {"url": "http://insecure"})

    def test_incidents_lifecycle_and_escalation(self):
        with tempfile.TemporaryDirectory() as d:
            incidents.save_settings(Path(d), {"minutes": 15, "channels": ["email"], "roles": []}, [])
            v = incidents.open_incident(Path(d), "disk_low", "Disk almost full", "C: 95%", {"email": "ok"})
            mandati = []
            self.assertEqual(incidents.escalate_due(Path(d), sender=lambda *a: mandati.append(a), now=datetime.now() + timedelta(minutes=5)), 0)
            self.assertEqual(incidents.escalate_due(Path(d), sender=lambda *a: mandati.append(a), now=datetime.now() + timedelta(minutes=20)), 1)
            self.assertEqual(incidents.escalate_due(Path(d), sender=lambda *a: mandati.append(a), now=datetime.now() + timedelta(minutes=40)), 0)  # once
            incidents.update(Path(d), v["id"], "ack", "mario")
            with self.assertRaises(ValueError):
                incidents.update(Path(d), v["id"], "ack", "luca")
            chiuso = incidents.update(Path(d), v["id"], "close", "mario", "disk cleaned")
            self.assertEqual((chiuso["status"], chiuso["note"]), ("closed", "disk cleaned"))

    def test_executive_pdf(self):
        dati = {"org": "ACME", "start": "2026-10-06T00:00:00", "end": "2026-11-05T00:00:00", "pcs": 3, "online": 2, "overall": 81, "weak": 0,
                "compliance": None, "areas": [("Pulizia", 90)], "runs": {"total": 1, "fixed": 1, "not_fixed": 0, "failed": 0},
                "incidents": {"open": 0, "closed": 1}, "updates": {"pending": 0, "critical": 0, "days": None}, "risks": [], "warranty": []}
        pdf = pdfreport.build(dati, "it")
        self.assertTrue(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"Rapporto direzionale", pdf)


class AutoRollback(unittest.TestCase):
    def test_worse_fix_is_put_back(self):
        from wmm.agent import jobs, undo
        from wmm.agent.store import Store
        with tempfile.TemporaryDirectory() as d:
            appsettings.save(Path(d), {"auto_rollback": True})
            manager = jobs.JobManager(Store(Path(d) / "wmm.db"), "M", False)
            job = SimpleNamespace(write=lambda t: None)
            azione = SimpleNamespace(id="performance.x", title="X")
            with mock.patch.object(undo, "restore", return_value=(2, [])) as r, mock.patch("wmm.agent.notify.safe_event"):
                self.assertTrue(manager._auto_rollback(job, azione, {"verdict": "worse", "before": "1", "after": "0"}, [{"x": 1}]))
                self.assertFalse(manager._auto_rollback(job, azione, {"verdict": "fixed"}, [{"x": 1}]))
            r.assert_called_once()


class ApiTokensAndApprovals(unittest.TestCase):
    admin = True
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_bearer_token_and_approval_through_the_api(self):
        s, r, _ = self.request("POST", "/api/v1/auth/setup", {"username": "admin", "password": PW})
        sess = {"X-WMM-Session": r["token"]}
        _, t, _ = self.request("POST", "/api/v1/tokens", {"name": "script", "days": 1}, headers=sess)
        bearer = {"Authorization": "Bearer " + t["token"]}
        self.assertEqual(self.request("GET", "/api/v1/dashboard", token=False, headers=bearer)[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/dashboard", token=False, headers={"Authorization": "Bearer wmm_" + "0" * 40})[0], 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/password", {"old": PW, "new": "x"}, token=False, headers=bearer)[0], 403)
        appsettings.save(self.agent.data_dir, {"approval_levels": ["moderate", "high"]})
        alto = next(a.id for a in __import__("wmm.agent.actions", fromlist=["CATALOG"]).CATALOG.values() if a.risk == "high" and a.kind != "report")
        self.agent.accounts.update_role("technician", {"permissions": [p for p in A.BUILTIN["technician"]["permissions"] if p != "approvals.bypass"]})
        self.request("POST", "/api/v1/users", {"username": "tech", "role_id": "technician", "password": "T3ch!Password"}, headers=sess)
        tech = {"X-WMM-Session": self.request("POST", "/api/v1/auth/login", {"username": "tech", "password": "T3ch!Password"})[1]["token"]}
        stato, risposta, _ = self.request("POST", "/api/v1/runs", {"actions": [alto], "confirmed": True}, headers=tech)
        self.assertEqual(stato, 202)
        self.assertEqual(risposta["approval"]["status"], "pending")
        with mock.patch.object(self.agent.jobs, "start", return_value="cd" * 16):
            stato, d, _ = self.request("POST", f"/api/v1/approvals/{risposta['approval']['id']}/approve", {}, headers=sess)
        self.assertEqual((stato, d["status"], d["job_id"]), (200, "approved", "cd" * 16))


if __name__ == "__main__":
    unittest.main()
