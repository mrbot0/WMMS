"""Tests for 2.11: every route called with every kind of role (permission matrix), database migrations, central
server tenants and backups. Nothing changes the PC: a request that would run something is only made by roles the
route must refuse, so the code behind it never starts."""
import re
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import accounts as A
from wmm.agent import central, centralmove, migrations, store, tlsutil
from wmm.server import api, permissions
from tests import test_v29

PW = test_v29.PW
CANDIDATI = ["cleanup", "run", "save", "ack", "approve", "wifi", "end", "json", "start", "email", "set", "uninstall",
             "1", "a" + "0" * 16, "c" + "0" * 10, "r" + "0" * 10, "t" + "0" * 12, "u" + "0" * 12,
             "k" + "0" * 10, "b" + "0" * 10, "0" * 8, "0" * 12, "0" * 16, "0" * 32, "abc"]


def sample_path(schema: re.Pattern) -> tuple:
    """A concrete path that matches the route, and its groups."""
    testo = schema.pattern

    def scegli(m):
        gruppo = re.compile(m.group(0))
        for c in CANDIDATI:
            if gruppo.fullmatch(c):
                return c
        raise AssertionError(f"no sample for {m.group(0)} in {testo}")

    percorso = re.sub(r"\((?!\?)[^)]*\)", scegli, testo).replace("\\", "")
    trovato = schema.fullmatch(percorso)
    assert trovato, (testo, percorso)
    return percorso, trovato.groups()


class PathSamples(unittest.TestCase):
    def test_every_route_has_a_sample(self):
        for metodo, schema, funzione in api.ROUTES:
            sample_path(schema)


class PermissionMatrix(test_v29.ApiBase):
    """Every route, without a session, with a role without permissions and with a role that has every permission but
    the ones the route needs: all must be refused before the route runs."""

    def setUp(self):
        super().setUp()
        self.admin_token = self.call("POST", "/auth/setup", {"username": "admin", "password": PW})[1]["token"]
        self.conti = self.agent.accounts
        self.ruoli = {}

    def session_for(self, permessi: frozenset) -> str:
        if permessi not in self.ruoli:
            n = len(self.ruoli)
            ruolo = self.conti.create_role({"name": f"Matrix {n}", "permissions": sorted(permessi)})
            self.conti.create_user({"username": f"tester{n}", "role_id": ruolo["id"], "password": f"Zq9!Kw{n:03d}xYvB"})
            self.ruoli[permessi] = self.conti.login(f"tester{n}", f"Zq9!Kw{n:03d}xYvB")["token"]
        return self.ruoli[permessi]

    def test_matrix(self):
        nessuno = self.session_for(frozenset())
        provate = 0
        for metodo, schema, funzione in api.ROUTES:
            nome = funzione.__name__
            if nome in permissions.PUBLIC or metodo == "HEAD":
                continue
            percorso, gruppi = sample_path(schema)
            corpo = None if metodo == "GET" else {}
            with self.subTest(route=f"{metodo} {percorso}"):
                stato = self.request(metodo, percorso, corpo)[0]
                self.assertEqual(stato, 401, "no session must be refused")
                richiesti = permissions.required(nome, metodo, gruppi)
                if not richiesti:
                    continue  # any signed-in user: calling it would run it
                for p in richiesti:
                    self.assertIn(p, A.ALL, f"{nome} needs an unknown permission {p}")
                stato = self.call(metodo, percorso[len("/api/v1"):], corpo, nessuno)[0]
                self.assertEqual(stato, 403, f"a role without permissions reached {nome}")
                quasi = self.session_for(frozenset(A.ALL) - set(richiesti))
                stato = self.call(metodo, percorso[len("/api/v1"):], corpo, quasi)[0]
                self.assertEqual(stato, 403, f"{nome} must need {richiesti}")
                provate += 1
        self.assertGreater(provate, 150)

    def test_user_limited_to_some_clients(self):
        srv = self.agent._central_server
        rossi = srv.save_tenant({"name": "Rossi"})
        tecnico = self.session_for(frozenset(A.ALL))
        nome = self.conti.session(tecnico)["username"]
        srv.set_access(nome, [rossi["id"]])
        stato, dati, _ = self.call("GET", "/central", sessione=tecnico)
        self.assertEqual(stato, 200)
        self.assertTrue(dati["limited"])
        self.assertEqual([t["name"] for t in dati["tenants"]], ["Rossi"])
        for metodo, percorso, corpo in (("POST", "/central/groups", {"name": "x"}), ("POST", "/central/tenants", {"name": "Altro"}),
                                        ("POST", "/central/backup", {"password": "x" * 20}), ("PUT", "/central/server", {"enabled": False, "port": 8770}),
                                        ("POST", "/central/jobs", {"kind": "relocate", "payload": {"host": "h", "port": 9000}, "group": "x"})):
            self.assertEqual(self.call(metodo, percorso, corpo, tecnico)[0], 403, percorso)
        stato, dati, _ = self.call("GET", "/central", sessione=self.admin_token)
        self.assertFalse(dati["limited"])
        self.assertEqual(dati["tenants"][0]["users"], [nome])

    def test_tokens_cannot_manage_tokens_or_sign_in(self):
        from wmm.agent import governance
        utente = self.conti.session(self.admin_token)
        token = governance.create_token(self.conti, utente, {"name": "ci", "scopes": []})["token"]
        for metodo, percorso in (("GET", "/tokens"), ("POST", "/tokens"), ("POST", "/auth/password")):
            stato = self.request(metodo, "/api/v1" + percorso, {} if metodo != "GET" else None,
                                 headers={"Authorization": "Bearer " + token})[0]
            self.assertEqual(stato, 403, percorso)


class Migrations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # sqlite may hold a file a moment longer on Windows
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def old_wmm_db(self):
        """A wmm.db as a 1.6 build left it: no delay column, none of the 2.6 columns, version 0."""
        db = sqlite3.connect(self.dir / "wmm.db")
        db.executescript("""CREATE TABLE schedules (id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT, action_id TEXT, cron TEXT, enabled INTEGER);
                            CREATE TABLE runs (id TEXT PRIMARY KEY, machine_id TEXT, started TEXT);
                            INSERT INTO runs (id, machine_id, started) VALUES ('r1', 'M', '2025-01-01T10:00:00');""")
        db.commit()
        db.close()

    def test_old_database_is_saved_then_upgraded(self):
        self.old_wmm_db()
        s = store.Store(self.dir / "wmm.db")
        self.assertEqual(migrations.version(self.dir / "wmm.db"), len(store.MIGRATIONS))
        self.assertIn("delay", migrations.columns(sqlite3.connect(self.dir / "wmm.db"), "schedules"))
        self.assertTrue(s.migration["backup"])
        copia = sqlite3.connect(s.migration["backup"])
        self.assertEqual(copia.execute("SELECT id FROM runs").fetchall(), [("r1",)])  # the copy is the database before the change
        self.assertNotIn("delay", migrations.columns(copia, "schedules"))
        copia.close()
        again = store.Store(self.dir / "wmm.db")  # up to date: no new copy
        self.assertIsNone(again.migration["backup"])
        self.assertEqual(again.migration["applied"], [])

    def test_new_database_needs_no_backup(self):
        a = A.Accounts(self.dir / "accounts.db")
        self.assertIsNone(a.migration["backup"])
        self.assertEqual(migrations.version(self.dir / "accounts.db"), len(A.MIGRATIONS))
        self.assertFalse((self.dir / migrations.BACKUP_DIR).exists())

    def test_failing_step_changes_nothing(self):
        self.old_wmm_db()

        def rotto(db):
            raise sqlite3.OperationalError("disk full")
        with self.assertRaises(sqlite3.OperationalError):
            migrations.upgrade(self.dir / "wmm.db", "wmm", store.SCHEMA, store.MIGRATIONS + [rotto])
        self.assertEqual(migrations.version(self.dir / "wmm.db"), 0)
        self.assertNotIn("delay", migrations.columns(sqlite3.connect(self.dir / "wmm.db"), "schedules"))
        self.assertEqual(len(list((self.dir / migrations.BACKUP_DIR).glob("wmm-v0-*.db"))), 1)

    def test_newer_database_is_left_alone_and_backups_are_capped(self):
        store.Store(self.dir / "wmm.db")
        db = sqlite3.connect(self.dir / "wmm.db")
        db.execute("PRAGMA user_version = 99")
        db.commit()
        db.close()
        self.assertTrue(store.Store(self.dir / "wmm.db").migration["newer"])
        for i in range(8):
            migrations.backup(sqlite3.connect(self.dir / "wmm.db"), self.dir / "wmm.db", "wmm", i)
        self.assertEqual(len(list((self.dir / migrations.BACKUP_DIR).glob("wmm-*.db"))), migrations.KEEP)
        self.assertEqual([d["name"] for d in migrations.status(self.dir)], ["wmm.db"])


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


class CentralClientsAndMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # sqlite may hold a file a moment longer on Windows
        base = Path(self.tmp.name)
        self.a_dir, self.b_dir, self.pc_dir = base / "old", base / "new", base / "pc"
        for d in (self.a_dir, self.b_dir, self.pc_dir):
            d.mkdir()
        self.server = central.Server(self.a_dir)
        self.http = [central.server_http(self.server, 0, self.a_dir, tls=True)]
        self.port = self.http[0].server_address[1]
        self.fp = tlsutil.ensure(self.a_dir)["fingerprint"]
        self.inv = mock.patch.object(central, "collect_inventory", return_value={})
        self.inv.start()

    def tearDown(self):
        self.inv.stop()
        for h in self.http:
            h.shutdown()
            h.server_close()
        self.tmp.cleanup()

    def enroll(self, nome, cartella, tenant=""):
        codice = self.server.enrollment_code("127.0.0.1", self.port, self.fp, [], tenant)["code"]
        central.enroll(cartella, codice, nome, "M-" + nome)
        return next(a for a in self.server.agents() if a["hostname"] == nome)["id"]

    def test_clients_are_kept_apart(self):
        rossi = self.server.save_tenant({"name": "Rossi & Figli"})
        bianchi = self.server.save_tenant({"name": "Bianchi S.r.l."})
        with self.assertRaises(central.CentralError):
            self.server.save_tenant({"name": "rossi & figli"})
        a1 = self.enroll("R-01", self.pc_dir, rossi["id"])
        altro = Path(self.tmp.name) / "pc2"
        altro.mkdir()
        a2 = self.enroll("B-01", altro, bianchi["id"])
        with self.assertRaises(central.CentralError):
            self.server.enrollment_code("h", 1, self.fp, [], "k" + "0" * 10)
        self.server.set_access("tecnico", [rossi["id"]])
        ambito = self.server.scope_for("tecnico")
        self.assertEqual([a["hostname"] for a in self.server.agents(scope=ambito)], ["R-01"])
        self.assertIsNone(self.server.scope_for("admin"))  # no client = every client
        with self.assertRaises(central.CentralError):
            self.server.agent(a2, ambito)
        with self.assertRaises(central.CentralError):
            self.server.remove(a2, ambito)
        self.assertEqual(self.server.targets([a1, a2], scope=ambito), [a1])
        self.assertEqual(self.server.targets(tenant=bianchi["id"]), [a2])
        lotto = self.server.queue([a1, a2], "inventory", {})["batch"]
        self.assertEqual(len(self.server.batch(lotto, ambito)), 1)
        self.assertEqual(self.server.overview(ambito)["agents"], 1)
        self.assertNotIn("B-01", self.server.inventory_csv(ambito))
        from wmm.server.enterprise_api import _ScopedServer  # what the executive report of a limited user reads
        visto = _ScopedServer(self.server, ambito)
        self.assertEqual([a["hostname"] for a in visto.agents()], ["R-01"])
        with self.assertRaises(central.CentralError):
            visto.agent(a2)
        with self.assertRaises(central.CentralError):
            self.server.delete_tenant(bianchi["id"])  # still has a PC
        self.assertEqual(self.server.move_to_tenant([a2], rossi["id"]), 1)
        self.server.set_access("solo-bianchi", [bianchi["id"]])
        with self.assertRaises(central.CentralError):
            self.server.delete_tenant(bianchi["id"])  # someone is limited to it: deleting would open every client to them
        self.assertEqual(self.server.scope_for("solo-bianchi"), {bianchi["id"]})
        self.server.set_access("solo-bianchi", [rossi["id"]])
        self.server.delete_tenant(bianchi["id"])
        self.assertEqual({t["name"]: t["agents"] for t in self.server.tenants()}, {"Rossi & Figli": 2})

    def test_backup_is_sealed(self):
        blob = centralmove.seal("correct horse battery", b"hello" * 100)
        self.assertNotIn(b"hello", blob)
        self.assertEqual(centralmove.unseal("correct horse battery", blob), b"hello" * 100)
        with self.assertRaises(centralmove.MoveError):
            centralmove.unseal("wrong password!!", blob)
        rotto = bytearray(blob)
        rotto[40] ^= 1
        with self.assertRaises(centralmove.MoveError):
            centralmove.unseal("correct horse battery", bytes(rotto))
        with self.assertRaises(centralmove.MoveError):
            centralmove.seal("short", b"x")

    def test_move_to_another_pc_without_enrolling_again(self):
        cliente = self.server.save_tenant({"name": "Verdi"})
        ident = self.enroll("PC-01", self.pc_dir, cliente["id"])
        client = central.Client(self.pc_dir, lambda j: {"ok": True}, lambda: {"overall": 70}, "PC-01", "M-PC-01", "2.11.0")
        client.contact()
        nuova = free_port()
        with self.assertRaises(central.CentralError):
            self.server.queue([ident], "relocate", {"host": "bad host!", "port": nuova})
        self.server.queue([ident], "relocate", {"host": "127.0.0.1", "port": nuova})
        client.contact()  # receives the move
        self.assertEqual(central.client_settings(self.pc_dir)["port"], nuova)
        blob = centralmove.export(self.a_dir, "a long backup password", self.port)
        self.assertNotIn(b"PC-01", blob)
        info = centralmove.inspect(blob, "a long backup password")
        self.assertEqual((info["agents"], info["tenants"], info["fingerprint"]), (1, 1, self.fp))
        esito = centralmove.restore(self.b_dir, blob, "a long backup password")
        self.assertTrue(esito["restored"])
        nuovo = central.Server(self.b_dir)
        self.http.append(central.server_http(nuovo, nuova, self.b_dir, tls=True))
        self.assertEqual(tlsutil.ensure(self.b_dir)["fingerprint"], self.fp)  # same certificate: the pin still holds
        nuovo.queue([ident], "inventory", {})
        client.contact()  # reports the move to the new server and gets its job
        client.contact()
        self.assertEqual(nuovo.agents()[0]["tenant_name"], "Verdi")
        self.assertTrue(any(j["kind"] == "relocate" and j["status"] == "done" for j in nuovo.recent_jobs()))
        self.assertTrue(any(j["kind"] == "inventory" and j["status"] == "done" for j in nuovo.recent_jobs()))
        with self.assertRaises(centralmove.MoveError):
            centralmove.restore(self.b_dir, blob, "not the password")


class DocsAndUpdates(unittest.TestCase):
    def test_openapi_is_up_to_date_and_complete(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_docs", Path(__file__).resolve().parent.parent / "tools" / "build_docs.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertEqual(modulo.OUT.read_text(encoding="utf-8"), modulo.render(), "run: python tools/build_docs.py")
        from wmm.server import openapi
        d = openapi.document()
        operazioni = sum(len(v) for v in d["paths"].values())
        self.assertEqual(operazioni, sum(1 for m, _, _ in api.ROUTES if m != "HEAD"))
        self.assertEqual(d["paths"]["/api/v1/central/tenants/{tenant_id}"]["delete"]["x-permissions"], ["central.manage"])
        self.assertEqual(d["paths"]["/api/v1/auth/login"]["post"]["security"], [])

    def release(self):
        from wmm.agent import updater
        return updater.parse_release({"tag_name": "v9.9.9", "assets": [
            {"name": "WindowsMaintenanceManager-9.9.9.msi", "browser_download_url": "https://github.com/x/y/releases/download/v9.9.9/a.msi"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/x/y/releases/download/v9.9.9/SHA256SUMS.txt"}]})

    def test_msi_update_checks_hash_and_signature(self):
        import hashlib
        from wmm.agent import updater
        r = self.release()
        self.assertTrue(r["msi_url"].endswith(".msi"))
        msi = b"MSI" * 1000
        somme = f"{hashlib.sha256(msi).hexdigest()}  WindowsMaintenanceManager-9.9.9.msi\n".encode()
        lanciati = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(updater, "_get", side_effect=lambda url, n, *a: msi if url.endswith(".msi") else somme):
            firma = mock.Mock(return_value=mock.Mock(stdout="NotSigned\n"))
            esito = updater.install_msi(r, Path(d), runner=firma, launcher=lambda cmd, **k: lanciati.append(cmd))
            self.assertEqual((esito["method"], esito["signature"]), ("msi", "NotSigned"))
            self.assertEqual(lanciati[0][:2], ["msiexec", "/i"])
            self.assertIn("/qn", lanciati[0])
            with self.assertRaises(updater.UpdateError):
                updater.install_msi(r, Path(d), runner=mock.Mock(return_value=mock.Mock(stdout="HashMismatch")), launcher=lambda *a, **k: None)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(updater, "_get", side_effect=lambda url, n, *a: b"other" if url.endswith(".msi") else somme):
            with self.assertRaises(updater.UpdateError):
                updater.install_msi(r, Path(d), runner=firma, launcher=lambda *a, **k: None)
        self.assertEqual(len(lanciati), 1)

    def test_msi_installations_use_the_msi(self):
        from wmm.agent import updater
        with mock.patch.object(updater, "msi_installed", return_value=True), mock.patch.object(updater, "install_msi", return_value={"method": "msi"}) as m:
            self.assertEqual(updater.install(self.release(), Path("."))["method"], "msi")
            m.assert_called_once()


if __name__ == "__main__":
    unittest.main()
