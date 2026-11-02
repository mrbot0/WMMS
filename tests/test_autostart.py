"""Tests for Start with Windows (schtasks and whoami mocked)."""
import subprocess
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from wmm.agent import autostart, scheduler

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
SID = "S-1-5-21-1-2-3-1001"


def done(code=0, out=b""):
    return subprocess.CompletedProcess([], code, out, b"")


class TaskXml(unittest.TestCase):
    def test_logon_task_for_this_user_with_highest_rights(self):
        xml = autostart.task_xml(SID, r"C:\Program Files\Python313\python.exe", r"C:\Program Files\WMM & Co\wmm.py", 8765)
        radice = ET.fromstring(xml.replace('encoding="UTF-16"', ""))
        self.assertEqual(radice.find("t:Triggers/t:LogonTrigger/t:UserId", NS).text, SID)
        principale = radice.find("t:Principals/t:Principal", NS)
        self.assertEqual(principale.find("t:RunLevel", NS).text, "HighestAvailable")
        self.assertEqual(principale.find("t:LogonType", NS).text, "InteractiveToken")
        argomenti = radice.find("t:Actions/t:Exec/t:Arguments", NS).text
        self.assertEqual(argomenti, r'-I "C:\Program Files\WMM & Co\wmm.py" --no-browser --port 8765')


class Lifecycle(unittest.TestCase):
    def test_enable_refuses_an_unprotected_program_before_creating_anything(self):
        with mock.patch.object(scheduler, "ensure_protected", side_effect=scheduler.UnprotectedProgram("writable")), \
                mock.patch.object(scheduler, "_schtasks") as schtasks:
            with self.assertRaises(scheduler.UnprotectedProgram):
                autostart.enable("python.exe", r"C:\x\wmm.py", 8765)
        schtasks.assert_not_called()

    def test_enable_creates_the_task(self):
        with mock.patch.object(scheduler, "ensure_protected"), mock.patch.object(autostart, "current_user_sid", return_value=SID), \
                mock.patch.object(scheduler, "_schtasks", return_value=done()) as schtasks:
            autostart.enable("python.exe", r"C:\x\wmm.py", 8765)
        argomenti = schtasks.call_args[0]
        self.assertEqual(argomenti[:4], ("/Create", "/F", "/TN", autostart.TASK))

    def test_enable_reports_a_refusal(self):
        with mock.patch.object(scheduler, "ensure_protected"), mock.patch.object(autostart, "current_user_sid", return_value=SID), \
                mock.patch.object(scheduler, "_schtasks", return_value=done(1, b"Access is denied.")):
            with self.assertRaisesRegex(RuntimeError, "Access is denied"):
                autostart.enable("python.exe", r"C:\x\wmm.py", 8765)

    def test_disable_deletes_only_an_existing_task(self):
        with mock.patch.object(scheduler, "_schtasks", return_value=done(1)) as schtasks:
            autostart.disable()
        self.assertEqual([c[0][0] for c in schtasks.call_args_list], ["/Query"])
        with mock.patch.object(scheduler, "_schtasks", return_value=done(0)) as schtasks:
            autostart.disable()
        self.assertEqual([c[0][0] for c in schtasks.call_args_list], ["/Query", "/Delete"])

    def test_sid_from_whoami(self):
        with mock.patch.object(subprocess, "run", return_value=done(0, b'"pc\\marco","' + SID.encode() + b'"\r\n')):
            self.assertEqual(autostart.current_user_sid(), SID)
        with mock.patch.object(subprocess, "run", return_value=done(1, b"")):
            with self.assertRaises(RuntimeError):
                autostart.current_user_sid()


if __name__ == "__main__":
    unittest.main()
