"""Tests for the event viewer, live processes and services, and the registry editor."""
import tempfile
import unittest
import uuid
import winreg
from pathlib import Path

from wmm.agent import events, processes, registry

EVENT = ("<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='disk' EventSourceName='disk'/>"
         "<EventID Qualifiers='49156'>{id}</EventID><Level>{level}</Level><TimeCreated SystemTime='{time}'/><EventRecordID>9</EventRecordID>"
         "<Execution ProcessID='4' ThreadID='8'/><Channel>System</Channel><Computer>PC</Computer></System>"
         "<EventData><Data Name='device'>\\Device\\Harddisk0</Data></EventData>{rendering}</Event>")


class Events(unittest.TestCase):
    def test_parse_rendered_and_raw_events(self):
        testo = EVENT.format(id=7, level=2, time="2026-11-02T10:00:00Z",
                             rendering="<RenderingInfo Culture='en-US'><Message>Bad block on &lt;disk&gt;</Message></RenderingInfo>") + \
            EVENT.format(id=153, level=3, time="2026-11-02T09:00:00Z", rendering="")
        eventi = events.parse(testo, "System")
        self.assertEqual([e["id"] for e in eventi], [7, 153])
        self.assertEqual(eventi[0]["message"], "Bad block on <disk>")
        self.assertEqual(eventi[0]["level_name"], "error")
        self.assertIn("device=\\Device\\Harddisk0", eventi[1]["message"])

    def test_dtd_is_refused(self):
        with self.assertRaises(Exception):
            events.parse("<!DOCTYPE x [<!ENTITY a 'b'>]>" + EVENT.format(id=1, level=2, time="", rendering=""), "System")

    def test_query_building(self):
        q = events.build_query([1, 2], 24, ["disk", "Ntfs"], 7)
        self.assertIn("(Level=1 or Level=2)", q)
        self.assertIn("timediff(@SystemTime) <= 86400000", q)
        self.assertIn("Provider[@Name='disk' or @Name='Ntfs']", q)
        self.assertIn("(EventID=7)", q)
        self.assertIn("Level=0", events.build_query([4], None, [], None))  # classic sources log information as level 0

    def test_validation_refuses_injection_and_unknown_logs(self):
        for cattivo in ({"providers": "x' or 1=1"}, {"logs": "C:\\evil"}, {"levels": "9"}, {"hours": "-1"}, {"limit": "99999"}, {"id": "abc"}):
            with self.assertRaises(events.EventQueryError, msg=cattivo):
                events.validate(cattivo)
        self.assertEqual(events.validate({"preset": "hardware"})["logs"], ["System"])

    def test_reader_merges_logs_sorts_and_caches(self):
        chiamate = []

        def finto(log, query, limit):
            chiamate.append(log)
            orario = "2026-11-02T10:00:00Z" if log == "System" else "2026-11-02T11:00:00Z"
            return events.parse(EVENT.format(id=1, level=1, time=orario, rendering=""), log), ("Security: denied" if log == "Security" else None)
        lettore = events.EventReader(runner=finto)
        risposta = lettore.query({"logs": "System,Application,Security", "levels": "1"})
        self.assertEqual(risposta["events"][-1]["log"], "System")
        self.assertEqual(risposta["counts"]["critical"], 3)
        self.assertEqual(risposta["warnings"], ["Security: denied"])
        lettore.query({"logs": "System,Application,Security", "levels": "1"})
        self.assertEqual(len(chiamate), 3)  # second identical query served from the cache


class Processes(unittest.TestCase):
    def test_merge_joins_counters_by_instance(self):
        campioni = {"pid": {"chrome": 10, "chrome#1": 11, "Idle": 0, "_Total": 0, "lsass": 700},
                    "cpu": {"chrome": 400.0, "chrome#1": 100.0, "lsass": 0.0}, "memory": {"chrome": 104857600.0},
                    "threads": {"chrome": 20}}
        righe = processes.merge(campioni, 4, lambda pid: r"C:\Apps\chrome.exe" if pid in (10, 11) else "", {700: ["SamSs"]})
        self.assertEqual([r["pid"] for r in righe], [10, 11, 700])
        self.assertEqual(righe[0]["cpu"], 100.0)
        self.assertEqual(righe[0]["memory_mb"], 100.0)
        self.assertEqual(righe[2]["name"], "lsass.exe")
        self.assertTrue(righe[2]["critical"])
        self.assertEqual(righe[2]["services"], ["SamSs"])

    def test_end_process_rules(self):
        righe = [{"pid": 10, "name": "notepad.exe", "critical": False}, {"pid": 700, "name": "lsass.exe", "critical": True},
                 {"pid": 50, "name": "python.exe", "critical": False}]
        self.assertEqual(processes.check_end_process(righe, 10, "notepad.exe", [50])["pid"], 10)
        for pid, nome in ((700, "lsass.exe"), (50, "python.exe"), (10, "other.exe"), (99, "gone.exe")):
            with self.assertRaises(processes.ControlError, msg=(pid, nome)):
                processes.check_end_process(righe, pid, nome, [50])

    def test_service_rules(self):
        servizi = [{"name": "Spooler", "display": "Print Spooler", "start": "auto", "critical": False},
                   {"name": "RpcSs", "display": "RPC", "start": "auto", "critical": True},
                   {"name": "Fax", "display": "Fax", "start": "disabled", "critical": False}]
        self.assertEqual(processes.check_service(servizi, "spooler", "restart")["name"], "Spooler")
        self.assertEqual(processes.check_service(servizi, "RpcSs", "start")["name"], "RpcSs")
        for nome, op in (("RpcSs", "stop"), ("Fax", "start"), ("Nope", "stop"), ("x'; rm", "stop"), ("Spooler", "delete")):
            with self.assertRaises(processes.ControlError, msg=(nome, op)):
                processes.check_service(servizi, nome, op)
        self.assertIn("rpcss", processes.CRITICAL_SERVICES)


class Registry(unittest.TestCase):
    def setUp(self):
        self.nome = "WMM-Test-" + uuid.uuid4().hex[:8]
        self.base = "HKCU\\Software\\" + self.nome
        winreg.CloseKey(winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\" + self.nome))
        self.tmp = tempfile.TemporaryDirectory()
        self.editor = registry.RegistryEditor(Path(self.tmp.name))

    def tearDown(self):
        try:
            registry._delete_tree(winreg.HKEY_CURRENT_USER, "Software\\" + self.nome)
        except OSError:
            pass
        self.tmp.cleanup()

    def test_paths_and_protection(self):
        self.assertEqual(registry.parse_path(r"Computer\HKEY_LOCAL_MACHINE\SOFTWARE")[0::2], ("HKLM", "SOFTWARE"))
        with self.assertRaises(registry.RegistryError):
            registry.parse_path(r"C:\Windows")
        for chiave in (r"HKLM", r"HKLM\SOFTWARE", r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
                       r"HKLM\SYSTEM\CurrentControlSet\Services\disk", r"HKLM\SYSTEM\ControlSet001\Control\x", r"HKCU\Software"):
            self.assertTrue(registry.is_protected(chiave), chiave)
        self.assertFalse(registry.is_protected(self.base))

    def test_convert(self):
        self.assertEqual(registry.convert("REG_DWORD", "0x10"), (winreg.REG_DWORD, 16))
        self.assertEqual(registry.convert("REG_BINARY", "01 ff")[1], b"\x01\xff")
        self.assertEqual(registry.convert("REG_MULTI_SZ", "a\nb")[1], ["a", "b"])
        for tipo, dato in (("REG_DWORD", "-1"), ("REG_DWORD", str(1 << 32)), ("REG_BINARY", "zz"), ("REG_NONE", ""), ("REG_X", "1")):
            with self.assertRaises(registry.RegistryError, msg=(tipo, dato)):
                registry.convert(tipo, dato)

    def test_full_edit_cycle_with_backups(self):
        self.editor.create_key(self.base, "Child")
        esito = self.editor.set_value(self.base, "Speed", "REG_DWORD", "42")
        self.assertTrue(esito["backup"].endswith(".reg"))
        self.editor.set_value(self.base, "", "REG_SZ", "default text")
        vista = registry.list_key(self.base)
        self.assertEqual([s["name"] for s in vista["subkeys"]], ["Child"])
        valori = {v["name"]: v for v in vista["values"]}
        self.assertEqual(valori["Speed"]["data"], 42)
        self.assertEqual(valori[""]["display"], "default text")
        self.editor.rename_value(self.base, "Speed", "Velocity")
        self.assertIn("Velocity", [v["name"] for v in registry.list_key(self.base)["values"]])
        trovati = self.editor.search(self.base, "velo")
        self.assertEqual(trovati["results"][0]["name"], "Velocity")
        self.editor.delete_value(self.base, "Velocity")
        self.editor.delete_key(self.base + "\\Child")
        self.assertEqual(registry.list_key(self.base)["subkeys"], [])
        copie = self.editor.backups()
        self.assertGreaterEqual(len(copie), 4)
        self.assertIn(self.nome, copie[0]["key"])

    def test_restore_brings_a_deleted_value_back(self):
        self.editor.set_value(self.base, "Keep", "REG_SZ", "me")
        copia = self.editor.delete_value(self.base, "Keep")["backup"]
        self.editor.restore(copia)
        self.assertIn("Keep", [v["name"] for v in registry.list_key(self.base)["values"]])

    def test_protected_key_cannot_be_deleted_and_bad_backup_names_refused(self):
        with self.assertRaises(registry.RegistryError):
            self.editor.delete_key(r"HKCU\Software")
        for nome in ("..\\x.reg", "x.reg", "20260101-000000-000-a.reg"):
            with self.assertRaises(registry.RegistryError):
                self.editor.backup_file(nome)


if __name__ == "__main__":
    unittest.main()
