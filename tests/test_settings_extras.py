"""Tests for history cleanup and the playbook groups (iteration 10)."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from wmm.agent import actions
from wmm.agent.store import Store


class HistoryCleanup(unittest.TestCase):
    def test_prune_removes_only_old_finished_runs(self):
        with tempfile.TemporaryDirectory() as cartella:
            store = Store(Path(cartella) / "wmm.db")
            vecchio, recente, aperto = (store.open_run("pc", "cleanup.temp", "manual") for _ in range(3))
            for run_id in (vecchio, recente):
                store.close_run(run_id, "ok", "", 0, "log")
            db = sqlite3.connect(Path(cartella) / "wmm.db")  # two runs started 200 days ago; one never finished
            try:
                for run_id in (vecchio, aperto):
                    db.execute("UPDATE runs SET started = ? WHERE id = ?", ((datetime.now() - timedelta(days=200)).isoformat(timespec="seconds"), run_id))
                db.commit()
            finally:
                db.close()
            self.assertEqual(store.prune_runs("pc", 180), 1)
            rimasti = {r["id"] for r in store.runs("pc", limit=10)}
            self.assertEqual(rimasti, {recente, aperto})  # an unfinished run is never deleted
            self.assertEqual(store.prune_runs("other-pc", 1), 0)


class Playbooks(unittest.TestCase):
    def test_fifteen_playbooks_with_known_actions(self):
        ids = [p["id"] for p in actions.PLAYBOOKS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 15)
        for nuovo in ("health_check", "security_audit", "deep_clean", "network_fix", "update_all", "gaming", "privacy", "laptop", "new_pc", "print_fix"):
            self.assertIn(nuovo, ids)
        for p in actions.PLAYBOOKS:
            self.assertTrue(all(a in actions.CATALOG for a in p["actions"]), p["id"])

    def test_check_playbooks_are_read_only(self):
        for pid in ("health_check", "security_audit"):
            book = next(p for p in actions.PLAYBOOKS if p["id"] == pid)
            self.assertTrue(set(book["actions"]) <= actions.REPORTS, pid)


if __name__ == "__main__":
    unittest.main()
