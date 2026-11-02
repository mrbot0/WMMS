"""Tests for the job manager (fake actions, no system changes)."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from ottimizza_pc import Esito, SequenzaFermata, Stato
from wmm.agent import actions, jobs
from wmm.agent.store import Store

M = "PC-1"


def fake_action(action_id, risk, run):
    return actions.Action(action_id, action_id.split(".")[0], action_id, "", risk, 0.1, run, "" if risk == "safe" else "careful")


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "wmm.db")
        self.chiamate = []
        self.evento = threading.Event()

        def ok(ctx):
            self.chiamate.append("ok")
            ctx.scrivi("working")
            return Esito(Stato.OK, "fine")

        def lento(ctx):
            self.evento.wait(5)
            return Esito(Stato.OK)

        def rotto(ctx):
            raise RuntimeError("boom")

        catalogo = {
            "cleanup.ok": fake_action("cleanup.ok", "safe", ok),
            "cleanup.slow": fake_action("cleanup.slow", "safe", lento),
            "cleanup.broken": fake_action("cleanup.broken", "safe", rotto),
            "services.risky": fake_action("services.risky", "moderate", ok),
        }
        self.patches = [
            mock.patch.dict(actions.CATALOG, catalogo, clear=True),
            mock.patch.object(jobs, "free_bytes", return_value=0),
            mock.patch.object(jobs.op.Contesto, "registra"),
        ]
        for patch in self.patches:
            patch.start()
        self.manager = jobs.JobManager(self.store, M)

    def tearDown(self):
        self.evento.set()
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def wait(self, job_id):
        for _ in range(200):
            if not self.manager.status(job_id)["active"]:
                return self.manager.status(job_id)
            time.sleep(0.02)
        self.fail("job did not finish")

    def test_non_safe_without_confirmation_rejected(self):
        with self.assertRaises(jobs.ConfirmationRequired):
            self.manager.start(["services.risky"], "manual", confirmed=False)

    def test_unknown_action_rejected(self):
        with self.assertRaises(KeyError):
            self.manager.start(["nope"], "manual", confirmed=True)

    def test_second_job_rejected_while_running(self):
        primo = self.manager.start(["cleanup.slow"], "manual", confirmed=False)
        with self.assertRaises(jobs.RunInProgress):
            self.manager.start(["cleanup.ok"], "manual", confirmed=False)
        self.evento.set()
        self.wait(primo)

    def test_failed_restore_point_skips_all(self):
        with mock.patch.object(jobs.op, "punto_ripristino", side_effect=SequenzaFermata("no restore point")):
            stato = self.wait(self.manager.start(["cleanup.ok", "services.risky"], "manual", confirmed=True))
        self.assertEqual([r["status"] for r in stato["results"]], ["skipped", "skipped"])
        self.assertEqual(self.chiamate, [])
        self.assertEqual([r["status"] for r in self.store.runs(M)], ["skipped", "skipped"])

    def test_exception_becomes_error_and_is_stored(self):
        stato = self.wait(self.manager.start(["cleanup.broken", "cleanup.ok"], "manual", confirmed=False))
        self.assertEqual([r["status"] for r in stato["results"]], ["error", "ok"])
        self.assertIn("boom", stato["results"][0]["note"])
        self.assertEqual(self.store.runs(M)[1]["status"], "error")

    def test_safe_actions_skip_restore_point(self):
        with mock.patch.object(jobs.op, "punto_ripristino") as punto:
            stato = self.wait(self.manager.start(["cleanup.ok"], "auto", confirmed=False))
        punto.assert_not_called()
        self.assertEqual(stato["results"][0]["status"], "ok")
        self.assertIn("working", stato["log"])
        self.assertIn("working", self.store.run_log(self.store.runs(M)[0]["id"]))

    def test_other_process_holding_the_lock_blocks_runs(self):
        altro = jobs.ProcessLock(self.store.path.with_suffix(".lock"))
        self.assertTrue(altro.acquire())
        try:
            with self.assertRaises(jobs.RunInProgress):
                self.manager.start(["cleanup.ok"], "manual", confirmed=False)
            self.assertFalse(self.manager.busy)
        finally:
            altro.release()
        self.wait(self.manager.start(["cleanup.ok"], "manual", confirmed=False))

    def test_lock_released_even_if_process_unlock_fails(self):
        originale = jobs.msvcrt.locking

        def locking(fd, mode, nbytes):
            if mode == jobs.msvcrt.LK_UNLCK:
                raise OSError("unlock failed")
            return originale(fd, mode, nbytes)

        with mock.patch.object(jobs.msvcrt, "locking", side_effect=locking):
            self.wait(self.manager.start(["cleanup.ok"], "manual", confirmed=False))
        self.assertFalse(self.manager.busy)

    def test_history_failure_does_not_drop_remaining_actions(self):
        originale = self.store.open_run
        chiamate = {"n": 0}

        def open_run(*args):
            chiamate["n"] += 1
            if chiamate["n"] == 1:
                raise jobs.sqlite3.OperationalError("database is locked")
            return originale(*args)

        with mock.patch.object(self.store, "open_run", side_effect=open_run):
            stato = self.wait(self.manager.start(["cleanup.ok", "cleanup.ok"], "manual", confirmed=False))
        self.assertEqual([r["status"] for r in stato["results"]], ["error", "ok"])

    def test_recover_marks_interrupted_runs(self):
        run_id = self.store.open_run(M, "cleanup.ok", "manual")
        self.assertEqual(self.manager.recover_interrupted(), 1)
        run = self.store.runs(M)[0]
        self.assertEqual((run["id"], run["status"]), (run_id, "error"))
        self.assertIn("Interrupted", run["note"])

    def test_recover_skips_while_another_process_runs(self):
        self.store.open_run(M, "cleanup.ok", "schedule")
        altro = jobs.ProcessLock(self.store.path.with_suffix(".lock"))
        self.assertTrue(altro.acquire())
        try:
            self.assertEqual(self.manager.recover_interrupted(), 0)
        finally:
            altro.release()
        self.assertEqual(self.store.runs(M)[0]["status"], "running")

    def test_list_jobs_summarizes_recent_runs(self):
        primo = self.wait(self.manager.start(["cleanup.ok"], "manual", confirmed=False))
        elenco = self.manager.list()
        self.assertEqual(elenco[0]["id"], primo["id"])
        self.assertFalse(elenco[0]["active"])
        self.assertIn("finished", elenco[0])
        self.assertLessEqual(len(elenco[0]["log"]), jobs.LIST_LOG_LINES)
        self.assertEqual(elenco[0]["titles"], ["cleanup.ok"])

    def test_tasks_registry(self):
        registro = jobs.TaskRegistry()
        tid = registro.start("scan", "Full scan", 3)
        registro.step(tid, "Cleanup")
        self.assertEqual(registro.list()[0]["done"], 1)
        self.assertTrue(registro.list()[0]["active"])
        registro.finish(tid, "ok")
        voce = registro.list()[0]
        self.assertEqual((voce["active"], voce["status"], voce["done"]), (False, "ok", 3))

    def test_run_sync_returns_results(self):
        with mock.patch.object(jobs.op, "punto_ripristino", return_value=Esito(Stato.OK)):
            stato = self.manager.run_sync(["services.risky"], "schedule", confirmed=True)
        self.assertFalse(stato["active"])
        self.assertEqual(stato["results"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
