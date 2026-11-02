"""Tests for the power button: which processes are WMM ones (nothing is really stopped)."""
import json
import unittest
from unittest import mock

from wmm.agent import scheduler, shutdown


class Matching(unittest.TestCase):
    def test_wmm_command_lines(self):
        for riga in (r'"C:\Program Files\Python313\python.exe" -I "C:\Program Files\WindowsMaintenanceManager\wmm.py" --run-schedule 3',
                     r"C:\Python313\python.exe C:\Users\x\Desktop\WMM\wmm.py --no-browser",
                     "python wmm.py --preview", "py WMM.PY", r'pythonw.exe "D:\tools\wmm.py"'):
            self.assertTrue(shutdown.is_wmm(riga), riga)

    def test_other_python_programs(self):
        for riga in ("", None, "python -m http.server", r"python C:\x\notwmm.py", r"python C:\x\wmm.pyc", r"python C:\wmm.py.bak\run.py",
                     "python my_wmm.py"):
            self.assertFalse(shutdown.is_wmm(riga), riga)


class Processes(unittest.TestCase):
    def test_lists_other_wmm_processes_only(self):
        elenco = [{"pid": 10, "command": r"python C:\a\wmm.py"}, {"pid": 11, "command": "python other.py"},
                  {"pid": 12, "command": r"python C:\a\wmm.py --run-schedule 1"}]
        with mock.patch.object(scheduler, "_powershell", return_value=json.dumps(elenco)):
            self.assertEqual([p["pid"] for p in shutdown.wmm_processes(own_pid=10)], [12])

    def test_single_object_and_broken_output(self):
        with mock.patch.object(scheduler, "_powershell", return_value=json.dumps({"pid": 5, "command": "python wmm.py"})):
            self.assertEqual(len(shutdown.wmm_processes(own_pid=1)), 1)
        with mock.patch.object(scheduler, "_powershell", return_value="not json"):
            self.assertEqual(shutdown.wmm_processes(own_pid=1), [])

    def test_stop_others_kills_each_tree(self):
        with mock.patch.object(shutdown, "wmm_processes", return_value=[{"pid": 7}, {"pid": 8}]), \
                mock.patch.object(shutdown, "kill_tree", side_effect=[True, False]) as kill:
            self.assertEqual(shutdown.stop_others(own_pid=1), [7])
        self.assertEqual([c[0][0] for c in kill.call_args_list], [7, 8])


if __name__ == "__main__":
    unittest.main()
