"""Tests for alerts by email and Telegram: settings, secrets, once a day, the API and the scheduled-run hook."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_api
from wmm.agent import notify


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.n = notify.for_data_dir(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_secrets_are_encrypted_and_never_returned(self):
        vista = self.n.save({"telegram_token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabc", "telegram_chat": "123456789", "smtp_password": "pw"})
        grezzo = self.n.path.read_text(encoding="utf-8")
        self.assertNotIn("ABCDEFGHIJ", grezzo)
        self.assertNotIn('"pw"', grezzo)
        self.assertNotIn("telegram_token", vista)
        self.assertTrue(vista["has_telegram_token"])
        self.assertEqual(vista["channels"], ["telegram"])
        # An empty secret keeps the saved one; clear_secrets deletes them.
        self.assertTrue(self.n.save({"telegram_token": ""})["has_telegram_token"])
        self.assertFalse(self.n.save({"clear_secrets": True})["has_telegram_token"])

    def test_invalid_values_are_refused(self):
        for valori in ({"smtp_port": "abc"}, {"email_to": "not-an-address"}, {"telegram_chat": "x"}, {"events": ["unknown"]}, {"smtp_host": 5}):
            with self.assertRaises(notify.NotifyError):
                self.n.save(valori)

    def test_event_sent_once_a_day_and_only_when_enabled(self):
        self.n.save({"smtp_host": "smtp.example.com", "email_to": "a@example.com", "events": ["disk_low"]})
        with mock.patch.object(notify.Notifier, "send", return_value={"email": "ok"}) as invia:
            self.assertEqual(self.n.event("disk_low", "full", quando=1000.0, gruppo="C"), {"email": "ok"})
            self.assertEqual(self.n.event("disk_low", "full", quando=2000.0, gruppo="C"), {})
            self.assertEqual(self.n.event("disk_low", "full", quando=1000.0 + notify.REPEAT_SECONDS + 1, gruppo="C"), {"email": "ok"})
            self.assertEqual(self.n.event("run_failed", "x"), {})  # turned off
            self.assertEqual(invia.call_count, 2)

    def test_failed_send_is_retried_next_time(self):
        self.n.save({"smtp_host": "smtp.example.com", "email_to": "a@example.com"})
        with mock.patch.object(notify.Notifier, "send", return_value={"email": "connection refused"}):
            self.n.event("unsafe_apps", "x", quando=1000.0)
        self.assertNotIn("sent", json.loads(self.n.path.read_text(encoding="utf-8")))

    def test_telegram_errors_never_show_the_token(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("failed bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabc")):
            esito = notify.Notifier._telegram("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabc", "1", "t")
        self.assertNotIn("ABCDEFGHIJ", esito)

    def test_safe_event_never_raises(self):
        with mock.patch.object(notify.Notifier, "event", side_effect=RuntimeError("boom")):
            notify.safe_event(Path(self.tmp.name), "disk_low", "x")


class NotifyApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_settings_and_test_message(self):
        stato, dati, _ = self.request("GET", "/api/v1/notifications")
        self.assertEqual((stato, dati["channels"]), (200, []))
        self.assertEqual(self.request("POST", "/api/v1/notifications/test")[0], 409)
        self.assertEqual(self.request("PUT", "/api/v1/notifications", {"smtp_port": "x"})[0], 400)
        stato, dati, _ = self.request("PUT", "/api/v1/notifications", {"smtp_host": "smtp.example.com", "email_to": "a@example.com"})
        self.assertEqual((stato, dati["channels"]), (200, ["email"]))
        with mock.patch.object(notify.Notifier, "send", return_value={"email": "ok"}):
            stato, dati, _ = self.request("POST", "/api/v1/notifications/test")
        self.assertEqual((stato, dati["ok"]), (200, True))
        self.assertEqual(self.request("PUT", "/api/v1/notifications", {}, token=False)[0], 403)

    def test_low_disk_alert_after_a_storage_scan(self):
        sistema = dict(test_api.SYSTEM, volumes=[{"letter": "C", "free_gb": 5.0, "total_gb": 400.0}])
        with mock.patch.object(test_api.collectors, "collect_system", return_value=sistema), \
                mock.patch.object(notify, "safe_event") as evento:
            self.agent.system(force=True)
            self.request("POST", "/api/v1/areas/storage/scan")
        self.assertEqual(evento.call_args[0][1], "disk_low")


class ScheduledRunAlert(unittest.TestCase):
    def test_failed_scheduled_run_sends_an_alert(self):
        from wmm.agent import scheduler
        store = mock.Mock()
        store.path = Path(tempfile.gettempdir()) / "wmm.db"
        store.schedule.return_value = {"enabled": True, "action_id": "cleanup.temp", "confirmed": True, "kind": "daily"}
        jobs = mock.Mock()
        jobs.run_sync.return_value = {"results": [{"action_id": "cleanup.temp", "status": "error", "note": "disk busy"}]}
        with mock.patch("wmm.agent.routines.expand", return_value=["cleanup.temp"]), mock.patch.object(notify, "safe_event") as evento:
            self.assertEqual(scheduler.run_schedule(4, store, jobs), 1)
        self.assertEqual(evento.call_args[0][1], "run_failed")
        self.assertIn("disk busy", evento.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
