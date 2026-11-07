"""Tests for Task Scheduler integration (pure XML and run logic, schtasks mocked)."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from wmm.agent import scheduler
from wmm.agent.jobs import RunInProgress
from wmm.agent.store import Store

PY = r"C:\Python312\python.exe"
SCRIPT = r"C:\Tools\WMM\wmm.py"


def schedule(**sostituzioni):
    dati = {"id": 7, "action_id": "cleanup.temp", "kind": "once", "at": "2026-11-05T03:00", "days": "", "enabled": True}
    dati.update(sostituzioni)
    return dati


class Xml(unittest.TestCase):
    def test_task_name(self):
        self.assertEqual(scheduler.task_name(7), "\\WindowsMaintenanceManager\\WMM-7")

    def test_xml_once_has_start_boundary(self):
        xml = scheduler.task_xml(schedule(), PY, SCRIPT)
        self.assertIn("<StartBoundary>2026-11-05T03:00:00</StartBoundary>", xml)
        self.assertIn("<TimeTrigger>", xml)

    def test_xml_daily(self):
        xml = scheduler.task_xml(schedule(kind="daily"), PY, SCRIPT)
        self.assertIn("<DaysInterval>1</DaysInterval>", xml)

    def test_xml_weekly_days(self):
        xml = scheduler.task_xml(schedule(kind="weekly", days="MON,WED"), PY, SCRIPT)
        giorni = xml.split("<DaysOfWeek>")[1].split("</DaysOfWeek>")[0]
        self.assertIn("<Monday />", giorni)
        self.assertIn("<Wednesday />", giorni)
        self.assertNotIn("<Friday />", giorni)

    def test_xml_arguments_contain_id(self):
        xml = scheduler.task_xml(schedule(), PY, SCRIPT)
        self.assertIn("--run-schedule 7", xml)
        self.assertIn("-I &quot;", xml.replace('"', "&quot;"))
        self.assertIn(f"<Command>{PY}</Command>", xml)
        self.assertIn("<UserId>S-1-5-18</UserId>", xml)

    def test_xml_escapes_paths(self):
        xml = scheduler.task_xml(schedule(), PY, r"C:\A&B\wmm.py")
        self.assertIn("A&amp;B", xml)

    def test_invalid_schedule_rejected(self):
        with self.assertRaises(ValueError):
            scheduler.task_xml(schedule(kind="weekly", days=""), PY, SCRIPT)
        with self.assertRaises(ValueError):
            scheduler.task_xml(schedule(at="tomorrow"), PY, SCRIPT)
        with self.assertRaises(ValueError):
            scheduler.task_xml(schedule(at="2026-11-05T3:00"), PY, SCRIPT)
        with self.assertRaises(ValueError):
            scheduler.validate("weekly", "2026-11-05T03:00", ["MON"])


USER_SID = "S-1-5-21-1-2-3-1001"


class Protection(unittest.TestCase):
    def test_admin_only_acl_is_protected(self):
        voci = [{"sid": "S-1-5-18", "rights": "FullControl", "type": "Allow"},
                {"sid": "S-1-5-32-544", "rights": "FullControl", "type": "Allow"},
                {"sid": "S-1-5-32-545", "rights": "ReadAndExecute, Synchronize", "type": "Allow"}]
        self.assertFalse(scheduler.writable_by_non_admins(voci, "S-1-5-18", USER_SID))

    def test_user_folder_is_not_protected(self):
        voci = [{"sid": USER_SID, "rights": "FullControl", "type": "Allow"}]
        self.assertTrue(scheduler.writable_by_non_admins(voci, "S-1-5-32-544", USER_SID))

    def test_users_group_modify_is_not_protected(self):
        voci = [{"sid": "S-1-5-32-545", "rights": "Modify, Synchronize", "type": "Allow"}]
        self.assertTrue(scheduler.writable_by_non_admins(voci, "S-1-5-32-544", USER_SID))
        voci = [{"sid": "S-1-5-11", "rights": "CreateFiles, AppendData", "type": "Allow"}]
        self.assertTrue(scheduler.writable_by_non_admins(voci, "S-1-5-32-544", USER_SID))

    def test_deny_rules_are_ignored(self):
        voci = [{"sid": "S-1-1-0", "rights": "FullControl", "type": "Deny"}]
        self.assertFalse(scheduler.writable_by_non_admins(voci, "S-1-5-32-544", USER_SID))

    def test_user_owner_is_not_protected(self):
        self.assertTrue(scheduler.writable_by_non_admins([], USER_SID, USER_SID))

    def test_register_refuses_unprotected_program(self):
        with mock.patch.object(scheduler, "unprotected_paths", return_value=[r"C:\Users\x\Desktop\wmm.py"]), \
                mock.patch.object(scheduler, "_schtasks") as schtasks:
            with self.assertRaises(scheduler.UnprotectedProgram) as errore:
                scheduler.register(schedule(), PY, SCRIPT)
        schtasks.assert_not_called()
        self.assertIn("Desktop", str(errore.exception))


class NextRun(unittest.TestCase):
    REF = scheduler.datetime(2026, 11, 2, 12, 0)  # Monday

    def test_once(self):
        self.assertEqual(scheduler.next_run(schedule(), self.REF), "2026-11-05T03:00")
        self.assertIsNone(scheduler.next_run(schedule(at="2026-11-01T03:00"), self.REF))

    def test_daily_after_start(self):
        self.assertEqual(scheduler.next_run(schedule(kind="daily", at="2026-10-01T03:00"), self.REF), "2026-11-03T03:00")
        self.assertEqual(scheduler.next_run(schedule(kind="daily", at="2026-10-01T18:30"), self.REF), "2026-11-02T18:30")

    def test_weekly(self):
        dati = schedule(kind="weekly", at="2026-10-01T03:00", days="MON,FRI")
        self.assertEqual(scheduler.next_run(dati, self.REF), "2026-11-06T03:00")

    def test_disabled(self):
        self.assertIsNone(scheduler.next_run(schedule(enabled=False), self.REF))


class FakeJobs:
    def __init__(self, status="ok", busy=0):
        self.calls = []
        self.status = status
        self.busy = busy

    def run_sync(self, action_ids, origin, confirmed):
        if self.busy:
            self.busy -= 1
            raise RunInProgress("busy")
        self.calls.append((action_ids, origin, confirmed))
        return {"results": [{"action_id": action_ids[0], "status": self.status, "note": ""}]}


class RunSchedule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "wmm.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_once_schedule_disables_itself(self):
        sid = self.store.create_schedule("cleanup.temp", "once", "2026-11-05T03:00", "", False)
        jobs = FakeJobs()
        self.assertEqual(scheduler.run_schedule(sid, self.store, jobs), 0)
        self.assertEqual(jobs.calls, [(["cleanup.temp"], "schedule", False)])
        dati = self.store.schedule(sid)
        self.assertFalse(dati["enabled"])
        self.assertEqual(dati["last_status"], "ok")
        self.assertIsNotNone(dati["last_run"])

    def test_daily_schedule_stays_enabled_and_reports_error(self):
        sid = self.store.create_schedule("integrity.sfc", "daily", "2026-11-05T03:00", "", True)
        self.assertEqual(scheduler.run_schedule(sid, self.store, FakeJobs("error")), 1)
        self.assertTrue(self.store.schedule(sid)["enabled"])

    def test_missing_and_disabled(self):
        self.assertEqual(scheduler.run_schedule(99, self.store, FakeJobs()), 2)
        sid = self.store.create_schedule("cleanup.temp", "daily", "2026-11-05T03:00", "", False)
        self.store.update_schedule(sid, enabled=False)
        jobs = FakeJobs()
        self.assertEqual(scheduler.run_schedule(sid, self.store, jobs), 0)
        self.assertEqual(jobs.calls, [])

    def test_waits_while_another_run_is_active(self):
        sid = self.store.create_schedule("cleanup.temp", "daily", "2026-11-05T03:00", "", False)
        jobs = FakeJobs(busy=2)
        # time.sleep is patched for the whole process: count only the waits of this thread, not those of threads
        # left running by other tests.
        qui = threading.get_ident()
        attese = []
        with mock.patch.object(scheduler.time, "sleep", side_effect=lambda s: attese.append(s) if threading.get_ident() == qui else None):
            self.assertEqual(scheduler.run_schedule(sid, self.store, jobs), 0)
        self.assertEqual(len(attese), 2)
        self.assertEqual(len(jobs.calls), 1)


if __name__ == "__main__":
    unittest.main()
