"""Tests for 2.9: accounts, roles and permissions, the audit log, the permission of every route, and the app settings
(alert rules, connections, run rules, retention, backup). Nothing changes the PC."""
import base64
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from wmm.agent import accounts as A
from wmm.agent import actions, appsettings, notify
from wmm.server import api, permissions
from tests import test_api

PW = "Str0ng!Passw0rd"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.clock = Clock()
        self.acc = A.Accounts(self.dir / "accounts.db", clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()


class Passwords(unittest.TestCase):
    def test_hash_totp_and_policy(self):
        h = A.hash_password(PW)
        self.assertTrue(h.startswith("scrypt$") and A.check_password(PW, h) and not A.check_password("x", h))
        self.assertFalse(A.check_password(PW, "garbage"))
        segreto = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(A.totp_code(segreto, 59 // 30), "287082")  # RFC 6238 test vector (SHA-1, T=59)
        self.assertIsNotNone(A.totp_match(segreto, A.totp_code(segreto, 100), t=100 * 30 + 5))
        self.assertIsNone(A.totp_match(segreto, A.totp_code(segreto, 100), t=100 * 30 + 5, last=100))  # never twice
        pol = dict(A.POLICY_DEFAULTS)
        self.assertEqual(A.password_problems(PW, pol), [])
        self.assertTrue(A.password_problems("short", pol))
        self.assertIn("without the user name", A.password_problems("Mario!Rossi2026", pol, "rossi"))
        self.assertEqual(A.password_problems(A.temporary_password(), dict(pol, classes=4)), [])

    def test_catalog_and_builtin_roles(self):
        ids = [p["id"] for p in A.catalog()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len([i for i in ids if i.count(".") == 2 and i.startswith("run.")]), 9 * 4)
        for ruolo in A.BUILTIN.values():
            self.assertTrue(set(ruolo["permissions"]) <= A.ALL)
        self.assertNotIn("users.manage", A.BUILTIN["technician"]["permissions"])
        self.assertNotIn("run.cleanup.safe", A.BUILTIN["viewer"]["permissions"])
        self.assertIn("run.cleanup.report", A.BUILTIN["viewer"]["permissions"])


class SignIn(Temp):
    def setUp(self):
        super().setUp()
        self.admin = self.acc.setup("admin", PW, "Boss")

    def test_setup_once_and_login(self):
        self.assertTrue(self.acc.enabled)
        with self.assertRaises(A.AccountError):
            self.acc.setup("other", PW)
        r = self.acc.login("ADMIN", PW)  # user names are not case-sensitive
        s = self.acc.session(r["token"])
        self.assertEqual(set(s["permissions"]), A.ALL)
        self.assertFalse(s["limited"])
        self.assertNotIn(r["token"], (self.dir / "accounts.db").read_bytes().decode("latin-1"))  # only the hash is kept

    def test_wrong_passwords_lock_the_account(self):
        pol = self.acc.policy()
        for _ in range(pol["lockout_attempts"]):
            with self.assertRaises(A.AccountError):
                self.acc.login("admin", "wrong")
        with self.assertRaises(A.AccountError) as e:
            self.acc.login("admin", PW)
        self.assertEqual(e.exception.status, 423)
        self.clock.t += pol["lockout_minutes"] * 60 + 1
        self.assertTrue(self.acc.login("admin", PW)["token"])
        with self.assertRaises(A.AccountError) as e:
            self.acc.login("nobody", PW)
        self.assertEqual(e.exception.status, 401)

    def test_idle_and_max_session(self):
        r = self.acc.login("admin", PW)
        self.clock.t += (self.acc.policy()["idle_minutes"] + 1) * 60
        self.assertIsNone(self.acc.session(r["token"]))
        r = self.acc.login("admin", PW)
        for _ in range(30):
            self.clock.t += 25 * 60
            self.acc.session(r["token"])
        self.assertIsNone(self.acc.session(r["token"]))  # 12 hours at most even when active

    def test_single_session_and_revoke(self):
        self.acc.set_policy({"single_session": True})
        a = self.acc.login("admin", PW)["token"]
        b = self.acc.login("admin", PW)["token"]
        self.assertIsNone(self.acc.session(a))
        self.assertIsNotNone(self.acc.session(b))
        self.acc.revoke_session(self.acc.sessions()[0]["id"])
        self.assertIsNone(self.acc.session(b))

    def test_temporary_password_limits_the_session_until_changed(self):
        u = self.acc.create_user({"username": "mario", "role_id": "operator"})
        r = self.acc.login("mario", u["temporary_password"])
        self.assertTrue(r["must_change"])
        s = self.acc.session(r["token"])
        self.assertTrue(s["limited"])
        with self.assertRaises(A.AccountError):
            self.acc.change_password(s, "wrong", "N3w!Password99")
        with self.assertRaises(A.AccountError):
            self.acc.change_password(s, u["temporary_password"], u["temporary_password"])  # history
        self.acc.change_password(s, u["temporary_password"], "N3w!Password99")
        self.assertFalse(self.acc.session(r["token"])["limited"])

    def test_two_step(self):
        s = self.acc.session(self.acc.login("admin", PW)["token"])
        segreto = self.acc.totp_begin(s)["secret"]
        with self.assertRaises(A.AccountError):
            self.acc.totp_confirm(s, "000000")
        self.acc.totp_confirm(s, A.totp_code(segreto, int(self.clock.t // 30)))
        with self.assertRaises(A.AccountError) as e:
            self.acc.login("admin", PW)
        self.assertEqual(e.exception.status, 428)
        self.clock.t += 31
        codice = A.totp_code(segreto, int(self.clock.t // 30))
        self.assertTrue(self.acc.login("admin", PW, codice)["token"])
        with self.assertRaises(A.AccountError):
            self.acc.login("admin", PW, codice)  # the same code twice

    def test_role_requiring_two_step_limits_until_enrolled(self):
        self.acc.update_role("operator", {"require_2fa": True})
        self.acc.create_user({"username": "op", "role_id": "operator", "password": "0perator!Pass"})
        r = self.acc.login("op", "0perator!Pass")
        self.assertTrue(r["must_enroll_2fa"])
        s = self.acc.session(r["token"])
        self.assertTrue(s["limited"])
        segreto = self.acc.totp_begin(s)["secret"]
        self.acc.totp_confirm(s, A.totp_code(segreto, int(self.clock.t // 30)))
        self.assertFalse(self.acc.session(r["token"])["limited"])

    def test_hours_expiry_and_disabled(self):
        momento = datetime.fromtimestamp(self.clock.t)
        altro_giorno = (momento.weekday() + 3) % 7
        self.acc.create_user({"username": "night", "role_id": "viewer", "password": "N1ght!Shift22",
                              "hours": {"days": [altro_giorno], "from": "08:00", "to": "09:00"}})
        with self.assertRaises(A.AccountError):
            self.acc.login("night", "N1ght!Shift22")
        self.acc.create_user({"username": "old", "role_id": "viewer", "password": "0ld!Account99", "expires": "2000-01-01"})
        with self.assertRaises(A.AccountError):
            self.acc.login("old", "0ld!Account99")
        u = self.acc.create_user({"username": "off", "role_id": "viewer", "password": "D1sabled!Pass", "active": False})
        with self.assertRaises(A.AccountError):
            self.acc.login("off", "D1sabled!Pass")
        self.assertEqual(self.acc.get_user(u["id"])["status"], "disabled")

    def test_hours_across_midnight(self):
        ore = {"days": [0], "from": "22:00", "to": "06:00"}
        lunedi_23 = datetime(2026, 11, 2, 23, 0).timestamp()
        martedi_03 = datetime(2026, 11, 3, 3, 0).timestamp()
        martedi_23 = datetime(2026, 11, 3, 23, 0).timestamp()
        self.assertTrue(self.acc._within_hours(ore, lunedi_23))
        self.assertTrue(self.acc._within_hours(ore, martedi_03))
        self.assertFalse(self.acc._within_hours(ore, martedi_23))


class Management(Temp):
    def setUp(self):
        super().setUp()
        self.admin = self.acc.setup("admin", PW)

    def test_users_crud_copy_and_last_admin(self):
        u = self.acc.create_user({"username": "luca", "role_id": "technician", "email": "luca@example.com",
                                  "hours": {"days": [0, 1], "from": "08:00", "to": "18:00"}, "expires": "2030-01-01"})
        c = self.acc.copy_user(u["id"], "luca2")
        self.assertEqual((c["role_id"], c["hours"], c["expires"]), ("technician", u["hours"], "2030-01-01"))
        self.assertTrue(c["temporary_password"])
        with self.assertRaises(A.AccountError):
            self.acc.create_user({"username": "LUCA", "role_id": "viewer"})
        with self.assertRaises(A.AccountError):
            self.acc.create_user({"username": "bad name", "role_id": "viewer"})
        with self.assertRaises(A.AccountError):
            self.acc.update_user(self.admin["id"], {"role_id": "viewer"})  # the last administrator
        with self.assertRaises(A.AccountError):
            self.acc.update_user(self.admin["id"], {"active": False})
        with self.assertRaises(A.AccountError):
            self.acc.delete_user(self.admin["id"], self_id=u["id"])
        with self.assertRaises(A.AccountError):
            self.acc.delete_user(u["id"], self_id=u["id"])  # yourself
        self.acc.delete_user(c["id"])
        self.assertEqual([x["username"] for x in self.acc.users()], ["admin", "luca"])
        self.assertEqual([x["username"] for x in self.acc.users(role="technician")], ["luca"])
        self.assertEqual([x["username"] for x in self.acc.users(q="example")], ["luca"])

    def test_reset_unlock_and_bulk(self):
        u = self.acc.create_user({"username": "anna", "role_id": "viewer", "password": "Secret!Pass2026"})
        t = self.acc.reset_password(u["id"])["temporary_password"]
        self.assertTrue(self.acc.login("anna", t)["must_change"])
        ids = [self.acc.create_user({"username": f"u{i}", "role_id": "viewer"})["id"] for i in range(3)]
        r = self.acc.bulk(ids + [self.admin["id"]], "disable", self_id=self.admin["id"])
        self.assertEqual((r["done"], len(r["errors"])), (3, 1))
        self.assertEqual(self.acc.bulk(ids, "role", "operator")["done"], 3)
        self.assertEqual(self.acc.users(role="operator")[0]["role_id"], "operator")
        self.assertEqual(self.acc.bulk(ids, "delete")["done"], 3)

    def test_csv_import_and_export(self):
        r = self.acc.import_users("\ufeffusername,display,email,role,active\nmario,Mario,m@example.com,Operator,1\nbad name,,,viewer,1\nx1,,,Nope,1\n")
        self.assertEqual([c["username"] for c in r["created"]], ["mario"])
        self.assertEqual(len(r["skipped"]), 2)
        testo = self.acc.export_users()
        self.assertIn("mario,Mario,m@example.com,,Operator,1", testo)
        self.assertNotIn("scrypt", testo)

    def test_roles_crud_copy_compare_import(self):
        r = self.acc.create_role({"name": "Help desk", "base": "operator", "color": "teal"})
        self.assertEqual(set(r["permissions"]), set(A.BUILTIN["operator"]["permissions"]))
        r = self.acc.update_role(r["id"], {"permissions": r["permissions"] + ["registry.edit"]})
        self.assertIn("registry.edit", r["permissions"])
        with self.assertRaises(A.AccountError):
            self.acc.update_role(r["id"], {"permissions": ["nope"]})
        with self.assertRaises(A.AccountError):
            self.acc.update_role("admin", {"name": "x"})
        with self.assertRaises(A.AccountError):
            self.acc.create_role({"name": "help DESK"})
        copia = self.acc.copy_role(r["id"], "")
        self.assertEqual(copia["name"], "Help desk (copy)")
        d = self.acc.compare_roles(r["id"], "operator")
        self.assertEqual(d["only_a"], ["registry.edit"])
        esportato = self.acc.export_role(r["id"])
        self.acc.delete_role(copia["id"])
        u = self.acc.create_user({"username": "hd", "role_id": r["id"]})
        with self.assertRaises(A.AccountError):
            self.acc.delete_role(r["id"])  # it has users: where do they go?
        self.acc.delete_role(r["id"], reassign="viewer")
        self.assertEqual(self.acc.get_user(u["id"])["role_id"], "viewer")
        nuovo = self.acc.import_role(dict(esportato, permissions=esportato["permissions"] + ["future.permission"]))
        self.assertEqual(nuovo["skipped"], ["future.permission"])
        with self.assertRaises(A.AccountError):
            self.acc.delete_role("viewer")
        self.acc.update_role("viewer", {"permissions": []})
        self.assertEqual(set(self.acc.reset_role("viewer")["permissions"]), set(A.BUILTIN["viewer"]["permissions"]))

    def test_removing_user_management_from_the_only_admin_role_is_refused(self):
        self.acc.update_user(self.admin["id"], {"role_id": "admin"})
        r = self.acc.create_role({"name": "Boss", "permissions": sorted(A.ALL)})
        other = self.acc.create_user({"username": "boss", "role_id": r["id"], "password": "B0ss!Password"})
        self.acc.update_user(self.admin["id"], {"active": False})  # another manager exists: allowed
        with self.assertRaises(A.AccountError):
            self.acc.update_role(r["id"], {"permissions": ["view.dashboard"]})
        self.assertTrue(other["id"])

    def test_audit_filters_csv_and_prune(self):
        self.acc.create_user({"username": "zoe", "role_id": "viewer"}, by="admin")
        with self.assertRaises(A.AccountError):
            self.acc.login("admin", "wrong")
        tutti = self.acc.audit_list()
        self.assertGreaterEqual(tutti["total"], 3)
        self.assertEqual({e["action"] for e in self.acc.audit_list(action="user.")["entries"]}, {"user.create"})
        self.assertTrue(all(not e["ok"] for e in self.acc.audit_list(failed=True)["entries"]))
        self.assertIn("user.create", self.acc.audit_csv())
        self.clock.t += 400 * 86400
        self.assertGreaterEqual(self.acc.audit_prune(), tutti["total"])

    def test_can_run(self):
        operatore = {"permissions": A.BUILTIN["operator"]["permissions"]}
        self.assertTrue(A.can_run(operatore, actions.CATALOG["network.flush_dns"]))
        self.assertTrue(A.can_run(operatore, actions.CATALOG["network.speed_test"]))
        self.assertFalse(A.can_run(operatore, actions.CATALOG["network.reset"]))
        self.assertFalse(A.can_run({"permissions": []}, actions.CATALOG["network.speed_test"]))

    def test_policy_validation(self):
        with self.assertRaises(A.AccountError):
            self.acc.set_policy({"min_length": 4})
        with self.assertRaises(A.AccountError):
            self.acc.set_policy({"enabled": False})
        self.assertEqual(self.acc.set_policy({"min_length": 14})["min_length"], 14)


class SecurityReview(Temp):
    """The findings of the security review of 2.9, kept fixed."""

    def setUp(self):
        super().setUp()
        self.admin = self.acc.setup("admin", PW)

    def test_wrong_codes_lock_the_account(self):
        s = self.acc.session(self.acc.login("admin", PW)["token"])
        segreto = self.acc.totp_begin(s)["secret"]
        self.acc.totp_confirm(s, A.totp_code(segreto, int(self.clock.t // 30)))
        for _ in range(self.acc.policy()["lockout_attempts"]):
            with self.assertRaises(A.AccountError):
                self.acc.login("admin", PW, "000000")
        self.clock.t += 31
        with self.assertRaises(A.AccountError) as e:
            self.acc.login("admin", PW, A.totp_code(segreto, int(self.clock.t // 30)))
        self.assertEqual(e.exception.status, 423)

    def test_replacing_two_step_needs_the_password_and_keeps_it_on_until_confirmed(self):
        s = self.acc.session(self.acc.login("admin", PW)["token"])
        segreto = self.acc.totp_begin(s)["secret"]
        self.acc.totp_confirm(s, A.totp_code(segreto, int(self.clock.t // 30)))
        with self.assertRaises(A.AccountError):
            self.acc.totp_begin(s)
        self.acc.totp_begin(s, PW)
        self.assertTrue(self.acc.get_user(self.admin["id"])["totp_on"])  # the old secret still protects the account
        self.clock.t += 31
        self.assertTrue(self.acc.login("admin", PW, A.totp_code(segreto, int(self.clock.t // 30)))["token"])

    def test_nobody_grants_more_than_they_have(self):
        self.acc.create_user({"username": "hr", "role_id": "technician", "password": "Human!Res2026"})
        ruolo = self.acc.create_role({"name": "People", "permissions": ["view.users", "users.view", "users.manage"]})
        self.acc.update_user(self.acc.users(q="hr")[0]["id"], {"role_id": ruolo["id"]})
        hr = self.acc.session(self.acc.login("hr", "Human!Res2026")["token"])
        with self.assertRaises(A.AccountError):
            self.acc.create_user({"username": "boss2", "role_id": "admin"}, actor=hr)
        with self.assertRaises(A.AccountError):
            self.acc.update_user(hr["id"], {"role_id": "viewer"}, actor=hr)  # not even your own role
        with self.assertRaises(A.AccountError):
            self.acc.update_user(self.admin["id"], {"role_id": "viewer"}, actor=hr)  # nor demote someone above you
        with self.assertRaises(A.AccountError):
            self.acc.create_role({"name": "Sneaky", "permissions": ["registry.edit"]}, actor=hr)
        self.assertEqual(self.acc.create_user({"username": "intern", "role_id": ruolo["id"]}, actor=hr)["role_id"], ruolo["id"])

    def test_backup_restore_respects_permissions(self):
        lettore = {"permissions": ["settings.edit"]}
        esito = appsettings.import_config(self.dir, {"format": "wmm-config/1", "app_settings": {"org_name": "ACME"},
                                                     "account_policy": {"min_length": 30},
                                                     "custom_tools": [{"title": "x", "script": "rm"}]}, None, self.acc, "x", lettore)
        self.assertEqual(esito["restored"], ["app_settings"])
        self.assertEqual(sorted(esito["skipped"]), ["account_policy", "custom_tools"])
        self.assertNotEqual(self.acc.policy()["min_length"], 30)

    def test_webhooks_never_reach_local_addresses(self):
        self.assertEqual(appsettings.public_https("https://127.0.0.1/x"), "the address is not public")
        self.assertEqual(appsettings.public_https("https://192.168.1.1/x"), "the address is not public")
        self.assertEqual(appsettings.public_https("http://example.com/x"), "not an https:// address")
        self.assertEqual(appsettings.webhook_send("https://localhost/hook", "generic", "t", "x"), "the address is not public")


class RoutesHavePermissions(unittest.TestCase):
    def test_every_write_is_mapped_and_every_permission_exists(self):
        for metodo, schema, funzione in api.ROUTES:
            nome = funzione.__name__
            if metodo != "GET":
                self.assertTrue(nome in permissions.RULES or nome in permissions.PUBLIC, nome)
            for p in permissions.required(nome, metodo, ("cleanup", "x", "run")):
                self.assertIn(p, A.ALL, f"{nome}: {p}")
        self.assertEqual(permissions.required("area", "GET", ("registry",)), ["view.registry"])
        self.assertEqual(permissions.required("script_operation", "POST", ("ab", "run")), ["scripts.run"])
        self.assertEqual(permissions.required("unknown_write", "POST", ()), list(permissions.ADMIN))


class ApiBase(unittest.TestCase):
    admin = True
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def call(self, metodo, percorso, corpo=None, sessione=None):
        return self.request(metodo, "/api/v1" + percorso, corpo, headers={"X-WMM-Session": sessione} if sessione else None)


class ApiWithAccounts(ApiBase):
    def test_accounts_off_changes_nothing(self):
        self.assertEqual(self.call("GET", "/dashboard")[0], 200)
        self.assertFalse(self.call("GET", "/agent/info")[1]["accounts"])
        self.assertEqual(self.call("GET", "/auth/me")[1], {"accounts": False})

    def test_sign_in_roles_and_audit(self):
        stato, r, _ = self.call("POST", "/auth/setup", {"username": "admin", "password": PW, "display": "Boss"})
        self.assertEqual(stato, 200)
        admin = r["token"]
        self.assertEqual(self.call("GET", "/dashboard")[0], 401)
        self.assertEqual(self.call("GET", "/agent/info")[0], 200)  # the sign-in screen needs it
        self.assertEqual(self.call("GET", "/dashboard", sessione=admin)[0], 200)
        stato, u, _ = self.call("POST", "/users", {"username": "vera", "role_id": "viewer", "password": "V3ra!Password"}, admin)
        self.assertEqual(stato, 201)
        vera = self.call("POST", "/auth/login", {"username": "vera", "password": "V3ra!Password"})[1]["token"]
        self.assertEqual(self.call("GET", "/dashboard", sessione=vera)[0], 200)
        stato, err, _ = self.call("GET", "/registry", sessione=vera)
        self.assertEqual(stato, 403)
        self.assertIn("view.registry", err["error"])
        self.assertEqual(self.call("GET", "/users", sessione=vera)[0], 403)
        self.assertEqual(self.call("POST", "/runs", {"actions": ["network.flush_dns"]}, vera)[0], 403)
        consentiti = [a for a in self.call("GET", "/actions", sessione=vera)[1]["actions"] if a["allowed"]]
        self.assertTrue(consentiti and all(a["kind"] == "report" for a in consentiti))
        self.assertEqual(self.call("PUT", "/app-settings", {"org_name": "x"}, vera)[0], 403)
        voci = self.call("GET", "/audit?action=denied", sessione=admin)[1]["entries"]
        self.assertTrue(any(e["user"] == "vera" for e in voci))
        self.call("PUT", "/app-settings", {"org_name": "ACME"}, admin)
        self.assertTrue(any(e["action"] == "api.app_settings_put" for e in self.call("GET", "/audit", sessione=admin)[1]["entries"]))
        self.assertEqual(self.call("POST", "/auth/logout", {}, vera)[0], 200)
        self.assertEqual(self.call("GET", "/dashboard", sessione=vera)[0], 401)

    def test_temporary_password_session_is_limited(self):
        admin = self.call("POST", "/auth/setup", {"username": "admin", "password": PW})[1]["token"]
        temp = self.call("POST", "/users", {"username": "neo", "role_id": "technician"}, admin)[1]["temporary_password"]
        s = self.call("POST", "/auth/login", {"username": "neo", "password": temp})[1]
        self.assertTrue(s["must_change"])
        self.assertEqual(self.call("GET", "/dashboard", sessione=s["token"])[0], 403)
        self.assertEqual(self.call("POST", "/auth/password", {"old": temp, "new": "N30!Matrix2026"}, s["token"])[0], 200)
        self.assertEqual(self.call("GET", "/dashboard", sessione=s["token"])[0], 200)

    def test_run_rules(self):
        appsettings.save(self.agent.data_dir, {"block_high_risk": True, "require_reason": True})
        alto = next(a.id for a in actions.CATALOG.values() if a.risk == "high" and a.kind != "report")
        stato, err, _ = self.call("POST", "/runs", {"actions": [alto], "confirmed": True})
        self.assertEqual(stato, 409)
        stato, err, _ = self.call("POST", "/runs", {"actions": ["network.flush_dns"]})
        self.assertEqual(stato, 400)
        self.assertIn("reason", err["error"])
        with mock.patch.object(self.agent.jobs, "start", return_value="ab" * 16):
            self.assertEqual(self.call("POST", "/runs", {"actions": ["network.flush_dns"], "reason": "TICKET-12"})[0], 202)
        self.assertTrue(any(e["detail"] == "TICKET-12" for e in self.agent.accounts.audit_list(action="run.reason")["entries"]))

    def test_settings_routes(self):
        stato, d, _ = self.call("GET", "/app-settings")
        self.assertEqual(stato, 200)
        self.assertTrue(d["presets"])
        self.assertEqual(self.call("PUT", "/app-settings", {"proxy_url": "ftp://x"})[0], 400)
        self.assertEqual(self.call("PUT", "/app-settings", {"lan_allow": "8.8.8.0/24"})[0], 400)
        self.assertEqual(self.call("PUT", "/app-settings", {"pc_label": "Front desk"})[1]["values"]["pc_label"], "Front desk")
        stato, testo, risposta = self.request("GET", "/api/v1/config/export")
        backup = json.loads(testo) if isinstance(testo, str) else testo
        self.assertEqual(backup["format"], "wmm-config/1")
        self.assertNotIn("smtp_password", json.dumps(backup))
        self.call("POST", "/app-settings/reset", {"section": "app"})
        self.assertEqual(self.call("POST", "/config/import", {"data": backup})[0], 200)
        self.assertEqual(appsettings.load(self.agent.data_dir)["pc_label"], "Front desk")
        self.assertEqual(self.call("POST", "/data/maintenance", {"action": "integrity"})[1]["results"][0]["result"], "ok")
        self.assertEqual(self.call("GET", "/diagnostics")[0], 200)


class AppSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        appsettings.reset(self.dir, "all")  # the proxy and the opener go back to the defaults
        self.tmp.cleanup()

    def test_windows_quiet_hours_and_networks(self):
        f = {"enabled": True, "days": [0], "from": "22:00", "to": "06:00"}
        self.assertTrue(appsettings.in_window(f, datetime(2026, 11, 2, 23, 30).timestamp()))   # Monday night
        self.assertTrue(appsettings.in_window(f, datetime(2026, 11, 3, 5, 0).timestamp()))     # into Tuesday
        self.assertFalse(appsettings.in_window(f, datetime(2026, 11, 3, 12, 0).timestamp()))
        self.assertTrue(appsettings.in_window({"enabled": False}, 0))
        self.assertTrue(appsettings.in_quiet({"enabled": True, "from": "22:00", "to": "07:00"}, datetime(2026, 11, 3, 2, 0).timestamp()))
        appsettings.save(self.dir, {"lan_allow": "192.168.1.0/24"})
        self.assertTrue(appsettings.lan_allowed(self.dir, "192.168.1.20"))
        self.assertFalse(appsettings.lan_allowed(self.dir, "192.168.2.20"))
        self.assertTrue(appsettings.lan_allowed(self.dir, "127.0.0.1"))

    def test_offline_and_validation(self):
        self.assertTrue(appsettings.allowed(self.dir, "kev"))
        appsettings.save(self.dir, {"allow_kev": False})
        self.assertFalse(appsettings.allowed(self.dir, "kev"))
        appsettings.save(self.dir, {"allow_kev": True, "offline": True})
        self.assertFalse(appsettings.allowed(self.dir, "telegram"))
        for chiave, valore in (("console_port", 80), ("alert_repeat_hours", 0), ("webhook_url", "http://x.example"), ("alert_routes", {"nope": ["email"]}),
                               ("maint_window", {"enabled": True, "days": [], "from": "22:00", "to": "06:00"}), ("retention", {"history_days": 3})):
            with self.assertRaises(appsettings.SettingsError, msg=chiave):
                appsettings.save(self.dir, {chiave: valore})

    def test_webhook_payloads_and_telegram_chats(self):
        self.assertIn("content", appsettings.webhook_payload("discord", "T", "x"))
        self.assertIn("*T*", appsettings.webhook_payload("slack", "T", "x")["text"])
        risposta = json.dumps({"result": [{"message": {"chat": {"id": 42, "first_name": "Marco", "type": "private"}}},
                                          {"channel_post": {"chat": {"id": -100, "title": "Ops", "type": "channel"}}}]}).encode()

        class R:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                return risposta
        chats = appsettings.telegram_chats("12345:" + "a" * 30, opener=lambda req, timeout: R())
        self.assertEqual({c["id"] for c in chats}, {"42", "-100"})
        with self.assertRaises(appsettings.SettingsError):
            appsettings.telegram_bot("bad")

    def test_alert_rules(self):
        n = notify.for_data_dir(self.dir)
        appsettings.save(self.dir, {"webhook_url": "https://hooks.example.com/abc", "alert_prefix": "ACME", "alert_lang": "it",
                                    "alert_routes": {"disk_low": ["webhook"]}, "alert_repeat_hours": 2})
        inviati = []
        with mock.patch.object(appsettings, "webhook_send", side_effect=lambda url, kind, t, x: inviati.append(t) or "ok"):
            n.event("disk_low", "C: 95%", quando=1000)
            n.event("disk_low", "C: 95%", quando=1000 + 3600)      # inside the repeat interval
            n.event("disk_low", "C: 95%", quando=1000 + 3 * 3600)
        self.assertEqual(len(inviati), 2)
        self.assertTrue(inviati[0].startswith("[ACME] Il disco di sistema è quasi pieno su "))
        storia = appsettings.alert_log(self.dir)
        self.assertEqual(storia[0]["event"], "disk_low")
        appsettings.save(self.dir, {"alert_quiet": {"enabled": True, "from": "00:00", "to": "23:59"}})
        with mock.patch.object(appsettings, "webhook_send", return_value="ok") as w:
            n.event("unsafe_apps", "x", quando=time.time())
        w.assert_not_called()
        self.assertEqual(appsettings.alert_log(self.dir)[0]["skipped"], "quiet hours")

    def test_retention_and_data_info(self):
        snap = self.dir / "drift_snapshots"
        snap.mkdir()
        (snap / "2020-01-01.json").write_text("{}")
        (snap / "2099-01-01.json").write_text("{}")
        (self.dir / "connection_history.json").write_text(json.dumps({"samples": [{"t": "2020-01-01T00:00:00"}, {"t": "2099-01-01T00:00:00"}]}))
        fatto = appsettings.retention_run(self.dir)
        self.assertEqual((fatto["snapshots"], fatto["connection"]), (1, 1))
        self.assertTrue(any(f["name"] == "drift_snapshots" for f in appsettings.data_info(self.dir)["files"]))


if __name__ == "__main__":
    unittest.main()
