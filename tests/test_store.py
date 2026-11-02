"""Tests for the SQLite history store."""
import tempfile
import time
import unittest
from pathlib import Path

from wmm.agent.store import Store

M = "PC-1"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "wmm.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_scan_is_most_recent(self):
        self.store.save_scan(M, "cleanup", 50, {"a": 1})
        self.store.save_scan(M, "cleanup", 80, {"a": 2})
        ultima = self.store.last_scan(M, "cleanup")
        self.assertEqual(ultima["score"], 80)
        self.assertEqual(ultima["data"], {"a": 2})
        self.assertIsNone(self.store.last_scan(M, "services"))

    def test_trend_ascending(self):
        for punteggio in (10, 20, 30):
            self.store.save_scan(M, "integrity", punteggio, {})
        self.assertEqual([p["score"] for p in self.store.trend(M, "integrity")], [10, 20, 30])
        self.assertEqual([p["score"] for p in self.store.trend(M, "integrity", limit=2)], [20, 30])

    def test_run_open_and_close(self):
        run_id = self.store.open_run(M, "cleanup.temp", "manual")
        self.store.close_run(run_id, "ok", "done", 1024, "line1\nline2")
        run = self.store.runs(M)[0]
        self.assertEqual((run["status"], run["bytes_freed"], run["area"]), ("ok", 1024, "cleanup"))
        self.assertIsNotNone(run["finished"])
        self.assertEqual(self.store.run_log(run_id), "line1\nline2")
        self.assertEqual(self.store.last_runs_by_action(M)["cleanup.temp"]["status"], "ok")

    def test_runs_filtered_by_area(self):
        self.store.open_run(M, "cleanup.temp", "manual")
        self.store.open_run(M, "services.safe", "schedule")
        self.assertEqual([r["action_id"] for r in self.store.runs(M, area="services")], ["services.safe"])

    def test_average_seconds_from_recent_successful_runs(self):
        self.assertIsNone(self.store.average_seconds(M, "cleanup.temp"))
        with self.store._db() as db:
            db.executemany("INSERT INTO runs (machine_id, action_id, area, origin, started, finished, status) VALUES (?, ?, 'cleanup', 'manual', ?, ?, ?)", [
                (M, "cleanup.temp", "2026-11-02T10:00:00", "2026-11-02T10:00:30", "ok"),
                (M, "cleanup.temp", "2026-11-02T11:00:00", "2026-11-02T11:00:50", "preview"),
                (M, "cleanup.temp", "2026-11-02T12:00:00", "2026-11-02T12:09:00", "error"),
            ])
        self.assertEqual(self.store.average_seconds(M, "cleanup.temp"), 40.0)

    def test_schedule_crud(self):
        sid = self.store.create_schedule("cleanup.temp", "weekly", "2026-11-05T03:00", "MON,WED", True)
        self.assertEqual(self.store.schedule(sid)["days"], "MON,WED")
        self.assertTrue(self.store.schedule(sid)["enabled"])
        self.store.update_schedule(sid, enabled=False, last_status="ok")
        self.assertFalse(self.store.schedule(sid)["enabled"])
        self.assertEqual(len(self.store.schedules()), 1)
        self.store.delete_schedule(sid)
        self.assertIsNone(self.store.schedule(sid))


class SettingsTests(unittest.TestCase):
    def test_settings_roundtrip_and_defaults(self):
        with tempfile.TemporaryDirectory() as cartella:
            store = Store(Path(cartella) / "wmm.db")
            self.assertEqual(store.settings()["company"], "")
            store.save_settings({"company": "Acme IT", "technician": "Sam"})
            store.save_settings({"technician": "Alex"})
            self.assertEqual(store.settings()["company"], "Acme IT")
            self.assertEqual(store.settings()["technician"], "Alex")
            with self.assertRaises(ValueError):
                store.save_settings({"unknown": "x"})
            store.save_settings({"notes": "n" * 3000})
            self.assertEqual(len(store.settings()["notes"]), 3000)
            with self.assertRaises(ValueError):
                store.save_settings({"company": "c" * 600})

    def test_restore_on_start_is_on_by_default_and_a_flag(self):
        with tempfile.TemporaryDirectory() as cartella:
            store = Store(Path(cartella) / "wmm.db")
            self.assertEqual(store.settings()["restore_on_start"], "1")
            store.save_settings({"restore_on_start": "0"})
            self.assertEqual(store.settings()["restore_on_start"], "0")
            with self.assertRaises(ValueError):
                store.save_settings({"restore_on_start": "yes"})


if __name__ == "__main__":
    unittest.main()
