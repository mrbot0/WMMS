"""Tests for the schedule fixes: Task Scheduler status, result codes, one-time schedules in the past, the Test button."""
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from wmm.agent import scheduler

from tests import test_api


class ResultCodes(unittest.TestCase):
    def test_known_and_unknown_codes(self):
        self.assertEqual(scheduler.result_text(0), ("ok", "Completed"))
        self.assertEqual(scheduler.result_text(1)[0], "error")
        self.assertEqual(scheduler.result_text(0x41303)[1], "Has not run yet")
        self.assertEqual(scheduler.result_text(-2147024894)[1], "Python or the program was not found (moved or uninstalled)")  # 0x80070002 as signed
        self.assertEqual(scheduler.result_text(0x1234), ("error", "Failed with code 0x1234"))
        self.assertEqual(scheduler.result_text("x")[0], "skipped")

    def test_task_status_reads_one_call(self):
        out = json.dumps([{"name": "WMM-3", "state": "Ready", "result": 0, "last": "2026-11-03T12:00:05", "next": "2026-11-04T12:00:00"},
                          {"name": "WMM-4", "state": "Ready", "result": 267011, "last": "", "next": ""}])
        with mock.patch.object(scheduler, "_powershell", return_value=out) as ps:
            stati = scheduler.task_status()
        ps.assert_called_once()
        self.assertEqual(stati["WMM-3"]["result_text"], "Completed")
        self.assertEqual(stati["WMM-4"]["result_tone"], "skipped")
        with mock.patch.object(scheduler, "_powershell", return_value="not json"):
            self.assertEqual(scheduler.task_status(), {})

    def test_run_task_now_reports_errors(self):
        fallito = mock.Mock(returncode=1, stdout=b"ERROR: The system cannot find the file specified.")
        with mock.patch.object(scheduler, "_schtasks", return_value=fallito):
            with self.assertRaises(RuntimeError):
                scheduler.run_task_now(5)


class ScheduleApi(unittest.TestCase):
    admin = True
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_one_time_schedule_in_the_past_is_refused(self):
        passato = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        stato, dati, _ = self.request("POST", "/api/v1/schedules", {"action_id": "cleanup.temp", "kind": "once", "at": passato, "confirmed": False})
        self.assertEqual(stato, 400)
        self.assertIn("already passed", dati["error"])
        futuro = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(self.request("POST", "/api/v1/schedules", {"action_id": "cleanup.temp", "kind": "once", "at": futuro, "confirmed": False})[0], 201)

    def test_list_carries_the_windows_status_and_test_starts_the_task(self):
        futuro = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        _, creata, _ = self.request("POST", "/api/v1/schedules", {"action_id": "cleanup.temp", "kind": "daily", "at": futuro, "confirmed": False})
        nome = scheduler.task_name(creata["id"]).rsplit("\\", 1)[-1]
        stato_windows = {nome: {"state": "Ready", "last": None, "next": None, "result": 267011, "result_tone": "skipped", "result_text": "Has not run yet"}}
        with mock.patch.object(test_api.api.scheduler, "task_status", return_value=stato_windows):
            _, elenco, _ = self.request("GET", "/api/v1/schedules")
        self.assertEqual(elenco["schedules"][0]["task"]["result_text"], "Has not run yet")
        with mock.patch.object(test_api.api.scheduler, "run_task_now") as avvia:
            stato, dati, _ = self.request("POST", f"/api/v1/schedules/{creata['id']}/test")
        self.assertEqual((stato, dati["ok"]), (200, True))
        avvia.assert_called_once_with(creata["id"])
        self.assertEqual(self.request("POST", "/api/v1/schedules/9999/test")[0], 404)


if __name__ == "__main__":
    unittest.main()
