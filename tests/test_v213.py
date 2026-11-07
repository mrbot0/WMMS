"""Tests for 2.13: the Backup tab of Storage (wmm/agent/backups.py and wmm/server/routes213.py). Archives are made for
real in a temporary folder; robocopy is replaced by a fake that copies with shutil, so nothing outside the folder changes."""
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from wmm.agent import actions, backups
from tests import test_v29


def fake_robocopy(cmd, **k):
    """Copies like robocopy /E (or /MIR) and prints its summary."""
    src, dst = Path(cmd[1]), Path(cmd[2])
    n = b = 0
    if "/L" not in cmd:
        if "/MIR" in cmd and dst.exists():
            shutil.rmtree(dst)
        for f in src.rglob("*"):
            if f.is_file():
                t = dst / f.relative_to(src)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                n += 1
                b += f.stat().st_size
    out = f"   Files :  {n}  {n}  0  0  0  0\n   Bytes :  {b}  {b}  0  0  0  0\n"
    return SimpleNamespace(returncode=1 if n else 0, stdout=out)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.dati, self.src, self.dst = r / "dati", r / "Documents", r / "Backup"
        (self.src / "work").mkdir(parents=True)
        (self.src / "node_modules").mkdir()
        (self.src / "a.txt").write_text("alpha", encoding="utf-8")
        (self.src / "work" / "b.docx").write_bytes(os.urandom(3000))
        (self.src / "skip.tmp").write_text("x")
        (self.src / "node_modules" / "big.js").write_text("y" * 100)
        self.rounds = mock.patch.object(backups, "ROUNDS", 1000)
        self.rounds.start()

    def tearDown(self):
        self.rounds.stop()
        backups.RUNNING.clear()
        self.tmp.cleanup()

    def profile(self, **k):
        d = {"name": "Docs", "sources": [str(self.src)], "target": str(self.dst), "kind": "archive", "exclude": ["*.tmp", "node_modules"], "keep": 2}
        d.update(k)
        return backups.save(self.dati, d)


class Profiles(Base):
    def test_checks(self):
        for male, testo in [({"name": ""}, "Name"), ({"sources": []}, "1 to 20"), ({"sources": [str(self.src / "nope")]}, "does not exist"),
                            ({"target": "backup"}, "destination"), ({"target": str(self.src / "inside")}, "inside"),
                            ({"kind": "sync"}, "Kind"), ({"keep": 0}, "keep"), ({"frequency": "hourly"}, "Frequency"),
                            ({"password": "short"}, "8 characters"), ({"exclude": ["a/b"]}, "Exclusions")]:
            with self.assertRaises(backups.BackupError) as e:
                self.profile(**male)
            self.assertIn(testo, str(e.exception))
        self.assertEqual(self.profile(target=r"\\nas\share\pc")["target"], r"\\nas\share\pc")

    def test_password_is_kept_and_never_shown(self):
        p = self.profile(password="Secret-123")
        self.assertNotIn("password", p)
        self.assertTrue(p["encrypted"])
        self.assertNotIn(b"Secret-123", (self.dati / backups.PROFILES).read_bytes())
        cambiato = backups.save(self.dati, {**p, "name": "Docs 2"}, p["id"])
        self.assertTrue(cambiato["encrypted"])
        tolto = backups.save(self.dati, {**p, "clear_password": True}, p["id"])
        self.assertFalse(tolto["encrypted"])
        backups.delete(self.dati, p["id"])
        self.assertEqual(backups.profiles(self.dati), [])
        with self.assertRaises(backups.BackupError):
            backups.delete(self.dati, p["id"])

    def test_due(self):
        p = self.profile(frequency="daily")
        self.profile(name="Manual")
        self.assertEqual([x["id"] for x in backups.due(self.dati)], [p["id"]])
        backups._record(self.dati, {"profile": p["id"], "ok": True, "finished": datetime.now().isoformat(timespec="seconds")})
        self.assertEqual(backups.due(self.dati), [])
        self.assertEqual(len(backups.due(self.dati, datetime.now() + timedelta(hours=21))), 1)


class Archives(Base):
    def test_archive_versions_restore_and_verify(self):
        p = self.profile()
        r = backups.run(self.dati, p["id"])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["files"], 2)  # skip.tmp and node_modules are excluded
        v = backups.list_versions(self.dati, p["id"])
        self.assertEqual(len(v), 1)
        self.assertFalse(v[0]["encrypted"])
        elenco = backups.files(self.dati, p["id"], v[0]["name"])
        self.assertEqual(sorted(f["path"] for f in elenco["files"]), ["Documents/a.txt", "Documents/work/b.docx"])
        self.assertTrue(backups.verify(self.dati, p["id"])["ok"])
        # restore one file into a new folder, then all of them back in place
        nuova = Path(self.tmp.name) / "Restored"
        out = backups.restore(self.dati, p["id"], v[0]["name"], str(nuova), ["Documents/a.txt"])
        self.assertEqual(out["restored"], 1)
        self.assertEqual((nuova / "Documents" / "a.txt").read_text(encoding="utf-8"), "alpha")
        (self.src / "a.txt").unlink()
        out = backups.restore(self.dati, p["id"], v[0]["name"])
        self.assertEqual((out["restored"], out["skipped"]), (1, 1))  # b.docx is still there and is kept
        self.assertEqual((self.src / "a.txt").read_text(encoding="utf-8"), "alpha")
        self.assertEqual(backups.history(self.dati, p["id"])[0]["version"], v[0]["name"])

    def test_retention(self):
        p = self.profile(keep=2)
        base = backups.folder(p)
        base.mkdir(parents=True)
        for nome in ("20250101-000000.zip", "20250102-000000.zip"):
            with zipfile.ZipFile(base / nome, "w") as z:
                z.writestr("x", "x")
        backups.run(self.dati, p["id"])
        nomi = [v["name"] for v in backups.list_versions(self.dati, p["id"])]
        self.assertEqual(len(nomi), 2)
        self.assertNotIn("20250101-000000.zip", nomi)
        backups.delete_version(self.dati, p["id"], nomi[-1])
        self.assertEqual(len(backups.list_versions(self.dati, p["id"])), 1)
        with self.assertRaises(backups.BackupError):
            backups.delete_version(self.dati, p["id"], "..\\..\\x.zip")

    def test_encrypted_archive(self):
        p = self.profile(password="Secret-123")
        self.assertTrue(backups.run(self.dati, p["id"])["ok"])
        v = backups.list_versions(self.dati, p["id"])[0]
        self.assertTrue(v["encrypted"])
        dato = (backups.folder(p) / v["name"]).read_bytes()
        self.assertTrue(dato.startswith(backups.MAGIC))
        self.assertNotIn(b"Documents/a.txt", dato)
        self.assertEqual(backups.files(self.dati, p["id"], v["name"])["count"], 2)  # the saved password opens it
        with self.assertRaises(backups.BackupError) as e:
            backups.files(self.dati, p["id"], v["name"], password="wrong-password")
        self.assertEqual(e.exception.status, 403)
        # a changed byte is refused before anything is decrypted
        rotto = bytearray(dato)
        rotto[60] ^= 1
        (backups.folder(p) / v["name"]).write_bytes(bytes(rotto))
        with self.assertRaises(backups.BackupError):
            backups.verify(self.dati, p["id"])

    def test_zip_slip_is_refused(self):
        p = self.profile()
        base = backups.folder(p)
        base.mkdir(parents=True)
        with zipfile.ZipFile(base / "20260101-000000.zip", "w") as z:
            z.writestr("../../evil.txt", "x")
        with self.assertRaises(backups.BackupError):
            backups.restore(self.dati, p["id"], "20260101-000000.zip", str(Path(self.tmp.name) / "R"))
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())
        self.assertEqual(backups.restore(self.dati, p["id"], "20260101-000000.zip")["restored"], 0)  # nothing outside its source

    def test_unreachable_target(self):
        p = self.profile(target=r"\\no-such-nas-wmm\share")
        r = backups.run(self.dati, p["id"])
        self.assertFalse(r["ok"])
        self.assertIn("not reachable", r["errors"][0])

    def test_streamed_encryption_round_trip(self):
        a, b, c = (Path(self.tmp.name) / n for n in ("a", "b", "c"))
        a.write_bytes(os.urandom(backups.CHUNK * 2 + 17))
        backups.encrypt_file(a, b, "pw-12345678")
        backups.decrypt_file(b, c, "pw-12345678")
        self.assertEqual(a.read_bytes(), c.read_bytes())
        self.assertEqual(b.stat().st_size, a.stat().st_size + len(backups.MAGIC) + 64)


class Protected(Base):
    def test_system_and_app_folders_are_refused(self):
        for male in ({"sources": [os.environ.get("SystemRoot", r"C:\Windows")]}, {"target": str(self.dati / "out")},
                     {"target": os.environ.get("ProgramData", r"C:\ProgramData") + r"\wmm-test"}, {"sources": [str(Path(backups.__file__).parents[2])]}):
            with self.assertRaises(backups.BackupError) as e:
                self.profile(**male)
            self.assertIn("cannot be saved", str(e.exception))
        self.assertTrue(backups.protected("C:\\", None))
        self.assertFalse(backups.protected(str(self.src), self.dati))

    def test_restore_goes_where_the_archive_says(self):
        p = self.profile()
        backups.run(self.dati, p["id"])
        nome = backups.list_versions(self.dati, p["id"])[0]["name"]
        with self.assertRaises(backups.BackupError):
            backups.restore(self.dati, p["id"], nome, str(self.dati / "x"))
        (self.src / "a.txt").unlink()
        self.assertEqual(backups.restore(self.dati, p["id"], nome)["restored"], 1)
        self.assertTrue((self.src / "a.txt").exists())
        # a folder this profile does not save anymore is never written to, whatever the archive says
        altra = Path(self.tmp.name) / "Other"
        altra.mkdir()
        backups.save(self.dati, {**p, "sources": [str(altra)]}, p["id"])
        (self.src / "a.txt").unlink()
        out = backups.restore(self.dati, p["id"], nome)
        self.assertEqual(out["restored"], 0)
        self.assertFalse((self.src / "a.txt").exists())
        self.assertEqual(list(altra.iterdir()), [])


class CopyAndMirror(Base):
    def test_copy_mirror_verify_and_restore(self):
        p = self.profile(kind="mirror")
        r = backups.run(self.dati, p["id"], runner=fake_robocopy)
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["files"], 0)
        self.assertTrue((backups.folder(p) / "Documents" / "a.txt").exists())
        v = backups.verify(self.dati, p["id"])
        self.assertTrue(v["ok"], v)
        (self.src / "new.txt").write_text("n")
        v = backups.verify(self.dati, p["id"])
        self.assertEqual(v["missing"], ["Documents/new.txt"])
        out = backups.restore(self.dati, p["id"], dest=str(Path(self.tmp.name) / "R"), runner=fake_robocopy)
        self.assertGreater(out["restored"], 0)
        with self.assertRaises(backups.BackupError):
            backups.restore(self.dati, p["id"], scelti=["Documents/a.txt"])
        comandi = []
        backups.run(self.dati, p["id"], preview=True, runner=lambda c, **k: comandi.append(c) or fake_robocopy(c))
        self.assertIn("/L", comandi[0])
        self.assertIn("/MIR", comandi[0])
        self.assertEqual(comandi[0][comandi[0].index("/XF") + 1:comandi[0].index("/XD")], ["*.tmp", "node_modules"])

    def test_robocopy_summary(self):
        s = backups.parse_robocopy("               Total    Copied   Skipped  Mismatch    FAILED    Extras\n"
                                   "    Dirs :         4         1         3         0         0         0\n"
                                   "   Files :        12         5         6         0         1         0\n"
                                   "   Bytes :    123456     23456    100000         0        10         0\n")
        self.assertEqual(s, {"files_copied": 5, "files_failed": 1, "bytes_copied": 23456, "files_total": 12})

    def test_one_run_at_a_time(self):
        p = self.profile()
        backups.RUNNING[p["id"]] = {}
        with self.assertRaises(backups.BackupError) as e:
            backups.run(self.dati, p["id"])
        self.assertEqual(e.exception.status, 409)


class Tool(Base):
    def test_run_due_tool(self):
        self.assertIn("storage.backup_profiles", actions.CATALOG)
        ctx = SimpleNamespace(anteprima=False, righe=[])
        ctx.scrivi = ctx.righe.append
        self.assertIn("No backup", backups.run_due(ctx, self.dati).nota)
        self.profile(frequency="weekly")
        esito = backups.run_due(ctx, self.dati)
        self.assertIn("1 backups done", esito.nota)
        self.assertIn("No backup", backups.run_due(ctx, self.dati).nota)


class Api(test_v29.ApiBase):
    def test_routes(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "src").mkdir()
        (tmp / "src" / "f.txt").write_text("hello")
        try:
            with mock.patch.object(backups, "ROUNDS", 1000):
                stato, p, _ = self.call("POST", "/backups", {"name": "Api", "sources": [str(tmp / "src")], "target": str(tmp / "dst"), "kind": "archive"})
                self.assertEqual(stato, 201, p)
                self.assertEqual(self.call("POST", "/backups", {"name": ""})[0], 400)
                self.assertEqual(self.call("PUT", "/backups/b0000000000", {"name": "x"})[0], 404)
                self.assertEqual(self.call("POST", f"/backups/{p['id']}/run", {})[0], 202)
                for _ in range(200):
                    if self.call("GET", f"/backups/{p['id']}/history")[1]["history"]:
                        break
                    time.sleep(0.05)
                s = self.call("GET", "/backups")[1]
                self.assertEqual(s["profiles"][0]["versions"], 1)
                self.assertTrue(s["profiles"][0]["last"]["ok"])
                versione = self.call("GET", f"/backups/{p['id']}/versions")[1]["versions"][0]["name"]
                self.assertEqual(self.call("POST", f"/backups/{p['id']}/files", {"version": versione})[1]["count"], 1)
                self.assertTrue(self.call("POST", f"/backups/{p['id']}/verify", {})[1]["ok"])
                e = self.call("GET", f"/backups/{p['id']}/estimate")[1]
                self.assertEqual((e["files"], e["target_ok"]), (1, True))
                r = self.call("POST", f"/backups/{p['id']}/restore", {"version": versione, "dest": str(tmp / "R")})[1]
                self.assertEqual(r["restored"], 1)
                self.assertEqual(self.call("POST", f"/backups/{p['id']}/restore", {"version": versione, "files": "x"})[0], 400)
                self.assertEqual(self.call("DELETE", f"/backups/{p['id']}/versions?version={versione}")[0], 200)
                self.assertEqual(self.call("DELETE", f"/backups/{p['id']}")[0], 200)
                self.assertEqual(self.call("GET", "/backups")[1]["profiles"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
