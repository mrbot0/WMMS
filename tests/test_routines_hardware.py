"""Tests for routines (startup, sign-in, monthly schedules) and the hardware page (iteration 11)."""
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from wmm.agent import actions, hardware, routines, scheduler, scripts
from wmm.agent.store import Store

from tests import test_api
from tests.test_scheduler import FakeJobs


def schedule(**campi):
    base = {"id": 7, "action_id": "routine:startup_refresh", "kind": "startup", "at": "2026-11-05T00:00", "days": "", "delay": 5, "enabled": True}
    base.update(campi)
    return base


class Triggers(unittest.TestCase):
    def test_new_kinds_validate(self):
        for kind in ("startup", "logon", "monthly"):
            scheduler.validate(kind, "2026-11-05T03:00", "", 0)
        scheduler.validate("startup", "2026-11-05T00:00", "", scheduler.MAX_DELAY_MINUTES)

    def test_bad_delay_and_month_day_rejected(self):
        for delay in (-1, scheduler.MAX_DELAY_MINUTES + 1, "5", 2.5, True):
            with self.assertRaises(ValueError):
                scheduler.validate("startup", "2026-11-05T00:00", "", delay)
        with self.assertRaises(ValueError):
            scheduler.validate("monthly", "2026-11-29T03:00", "")
        scheduler.validate("monthly", "2026-11-28T03:00", "")

    def test_startup_and_logon_triggers(self):
        avvio = scheduler.trigger_xml(schedule())
        self.assertTrue(avvio.startswith("<BootTrigger>"))
        self.assertIn("<Delay>PT5M</Delay>", avvio)
        accesso = scheduler.trigger_xml(schedule(kind="logon", delay=0))
        self.assertTrue(accesso.startswith("<LogonTrigger>"))
        self.assertNotIn("<Delay>", accesso)
        self.assertNotIn("<UserId>", accesso)  # any user who signs in

    def test_monthly_trigger_every_month(self):
        xml = scheduler.trigger_xml(schedule(kind="monthly", at="2026-11-15T12:00"))
        self.assertIn("<Day>15</Day>", xml)
        for mese in scheduler.MONTHS:
            self.assertIn(f"<{mese} />", xml)

    def test_task_xml_for_routine(self):
        xml = scheduler.task_xml(schedule(), r"C:\Python\python.exe", r"C:\Program Files\WMM\wmm.py")
        self.assertIn("<BootTrigger>", xml)
        self.assertIn("--run-schedule 7", xml)

    def test_scripts_share_the_triggers(self):
        xml = scripts.task_xml("abcd1234", r"C:\x\a.bat", {"kind": "logon", "at": "2026-11-05T00:00", "days": "", "delay": 2})
        self.assertIn("<LogonTrigger>", xml)
        self.assertIn("<Delay>PT2M</Delay>", xml)

    def test_next_run(self):
        rif = datetime(2026, 12, 20, 9, 0)
        self.assertIsNone(scheduler.next_run(schedule(), rif))
        self.assertIsNone(scheduler.next_run(schedule(kind="logon"), rif))
        mensile = schedule(kind="monthly", at="2026-11-15T12:00")
        self.assertEqual(scheduler.next_run(mensile, rif), "2027-01-15T12:00")
        self.assertEqual(scheduler.next_run(mensile, datetime(2026, 11, 2)), "2026-11-15T12:00")


class Catalog(unittest.TestCase):
    def test_routines_use_known_actions_and_valid_frequencies(self):
        ids = [r["id"] for r in routines.ROUTINES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)
        for r in routines.ROUTINES:
            self.assertTrue(all(a in actions.CATALOG for a in r["actions"]), r["id"])
            self.assertIn(r["group"], routines.GROUPS)
            sug = r["suggested"]
            giorno = sug.get("day", 1)
            scheduler.validate(sug["kind"], f"2026-11-{giorno:02d}T{sug.get('time', '00:00')}", sug.get("days", ""), sug.get("delay", 0))
        self.assertTrue(any(r["suggested"]["kind"] == "startup" for r in routines.ROUTINES))

    def test_expand(self):
        self.assertEqual(routines.expand("cleanup.temp"), ["cleanup.temp"])
        self.assertEqual(routines.expand("routine:startup_network"), ["network.flush_dns", "network.purge_netbios"])
        self.assertEqual(routines.expand("playbook:print_fix"), ["services.clear_print_queue", "services.restart_spooler"])
        for sconosciuto in ("routine:nope", "playbook:nope", "nope.action"):
            with self.assertRaises(KeyError):
                routines.expand(sconosciuto)

    def test_describe_uses_the_highest_risk(self):
        self.assertEqual(routines.describe("routine:monthly_repair")["risk"], "moderate")
        self.assertEqual(routines.describe("routine:startup_network")["risk"], "safe")
        self.assertEqual(routines.describe("playbook:quick")["routine"], "playbook")
        self.assertEqual(routines.describe("routine:gone")["area"], "unknown")

    def test_catalog_lists_routines_and_playbooks(self):
        dati = routines.catalog()
        self.assertEqual(len(dati["routines"]), len(routines.ROUTINES))
        self.assertEqual(len(dati["playbooks"]), len(actions.PLAYBOOKS))
        salute = next(r for r in dati["routines"] if r["id"] == "monthly_health")
        self.assertTrue(salute["reports_only"])
        self.assertTrue(all("ref" in r and r["actions"] for r in dati["routines"]))


class StoreAndRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "wmm.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_database_gains_the_delay_column(self):
        db = sqlite3.connect(self.path)
        try:
            db.execute("CREATE TABLE schedules (id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL, kind TEXT NOT NULL, at TEXT NOT NULL, "
                       "days TEXT NOT NULL DEFAULT '', confirmed INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, "
                       "last_status TEXT, last_run TEXT)")
            db.execute("INSERT INTO schedules (action_id, kind, at, created) VALUES ('cleanup.temp', 'daily', '2026-11-05T03:00', 'x')")
            db.commit()
        finally:
            db.close()
        store = Store(self.path)
        self.assertEqual(store.schedules()[0]["delay"], 0)
        sid = store.create_schedule("routine:startup_refresh", "startup", "2026-11-05T00:00", "", False, 5)
        self.assertEqual(store.schedule(sid)["delay"], 5)

    def test_run_schedule_expands_a_routine(self):
        store = Store(self.path)
        sid = store.create_schedule("routine:startup_network", "startup", "2026-11-05T00:00", "", False, 2)
        jobs = FakeJobs()
        self.assertEqual(scheduler.run_schedule(sid, store, jobs), 0)
        self.assertEqual(jobs.calls, [(["network.flush_dns", "network.purge_netbios"], "schedule", False)])
        self.assertTrue(store.schedule(sid)["enabled"])

    def test_run_schedule_of_a_removed_routine_fails_cleanly(self):
        store = Store(self.path)
        sid = store.create_schedule("routine:removed", "daily", "2026-11-05T03:00", "", False)
        jobs = FakeJobs()
        self.assertEqual(scheduler.run_schedule(sid, store, jobs), 2)
        self.assertEqual(jobs.calls, [])
        self.assertEqual(store.schedule(sid)["last_status"], "error")


class RoutineApi(unittest.TestCase):
    """The agent over HTTP, with Task Scheduler mocked (same setup as test_api)."""
    admin = True
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_routine_catalog(self):
        stato, dati, _ = self.request("GET", "/api/v1/routines")
        self.assertEqual(stato, 200)
        self.assertEqual(len(dati["routines"]), len(routines.ROUTINES))
        self.assertEqual(dati["routines"][0]["scheduled"], [])

    def test_schedule_a_startup_routine(self):
        corpo = {"action_id": "routine:startup_refresh", "kind": "startup", "at": "2026-11-05T00:00", "delay": 5, "confirmed": False}
        stato, dati, _ = self.request("POST", "/api/v1/schedules", corpo)
        self.assertEqual(stato, 201)
        voce = self.agent.store.schedule(dati["id"])
        self.assertEqual((voce["kind"], voce["delay"]), ("startup", 5))
        _, elenco, _ = self.request("GET", "/api/v1/schedules")
        self.assertEqual(elenco["schedules"][0]["title"], "Fresh start")
        self.assertEqual(elenco["schedules"][0]["routine"], "routine")
        _, catalogo, _ = self.request("GET", "/api/v1/routines")
        fresca = next(r for r in catalogo["routines"] if r["id"] == "startup_refresh")
        self.assertEqual(fresca["scheduled"][0]["kind"], "startup")

    def test_routine_with_moderate_steps_needs_confirmation(self):
        corpo = {"action_id": "routine:monthly_repair", "kind": "monthly", "at": "2026-12-01T11:00", "confirmed": False}
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        corpo["confirmed"] = True
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 201)

    def test_bad_routine_and_delay(self):
        corpo = {"action_id": "routine:nope", "kind": "daily", "at": "2026-11-05T03:00", "confirmed": False}
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        corpo.update(action_id="routine:startup_refresh", kind="startup", delay="soon")
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        corpo.update(delay=999)
        self.assertEqual(self.request("POST", "/api/v1/schedules", corpo)[0], 400)
        self.assertEqual(self.agent.store.schedules(), [])

    def test_hardware_endpoints(self):
        finti = {"temperatures": [], "fans": [], "other": [], "gpus": [], "monitor_tool": "", "hottest": None, "read_at": "x", "monitor_installed": False}
        with mock.patch.object(self.agent.hardware, "sensors", return_value=finti):
            stato, dati, _ = self.request("GET", "/api/v1/hardware/sensors")
        self.assertEqual((stato, dati["hottest"]), (200, None))
        self.assertEqual(self.request("POST", "/api/v1/hardware/monitor-tool", {"action": "format"})[0], 400)
        errore = hardware.MonitorToolError("LibreHardwareMonitor is not installed.")
        with mock.patch.object(test_api.api.hardware, "start_monitor_tool", side_effect=errore):
            stato, dati, _ = self.request("POST", "/api/v1/hardware/monitor-tool", {"action": "start"})
        self.assertEqual(stato, 409)
        self.assertIn("not installed", dati["error"])


class HardwareParsing(unittest.TestCase):
    def test_pci_and_usb_ids(self):
        pci = hardware.parse_hwid(r"PCI\VEN_10DE&DEV_2488&SUBSYS_404C1458&REV_A1\4&1D81E16&0&0019")
        self.assertEqual((pci["vendor"], pci["vendor_id"], pci["device_id"], pci["subsys"], pci["rev"]), ("NVIDIA", "10DE", "2488", "404C1458", "A1"))
        self.assertEqual(pci["search"], r"PCI\VEN_10DE&DEV_2488")
        self.assertEqual(pci["lookup"], "pci/10DE/2488")
        usb = hardware.parse_hwid(r"USB\VID_046D&PID_C52B&MI_02\7&2A1B3C4D&0&0002")
        self.assertEqual((usb["vendor"], usb["search"], usb["lookup"]), ("Logitech", r"USB\VID_046D&PID_C52B", "usb/046D/C52B"))

    def test_other_ids(self):
        acpi = hardware.parse_hwid(r"ACPI\PNP0A08\0")
        self.assertEqual((acpi["bus"], acpi["search"], acpi["lookup"]), ("ACPI", r"ACPI\PNP0A08", ""))
        self.assertEqual(hardware.parse_hwid("")["search"], "")
        self.assertEqual(hardware.parse_hwid("garbage")["bus"], "")

    def test_kelvin(self):
        self.assertEqual(hardware.kelvin_tenths_to_c(3131.5), 40.0)
        self.assertIsNone(hardware.kelvin_tenths_to_c(0))
        self.assertIsNone(hardware.kelvin_tenths_to_c("x"))

    def test_nvidia_smi_output(self):
        schede = hardware.parse_nvidia("NVIDIA GeForce RTX 3070, 62, 45, 30, 120.5, 1710, 2000, 8192\nbad line\nGPU, 50, [N/A], 0, [N/A], 300, 1, 2")
        self.assertEqual(len(schede), 2)
        self.assertEqual((schede[0]["celsius"], schede[0]["fan_percent"], schede[0]["watts"]), (62.0, 45.0, 120.5))
        self.assertIsNone(schede[1]["fan_percent"])

    def test_summarize_sensors(self):
        raw = {"zones": [{"name": r"\_TZ.TZ00", "tenths_k": 3231.5, "throttle": 100}],
               "disks": [{"name": "Samsung SSD 980", "index": "0", "celsius": 41, "max_celsius": 60, "wear": 2, "hours": 1200}],
               "fans": [], "lhm_source": "LibreHardwareMonitor",
               "lhm": [{"name": "Core (Tctl/Tdie)", "type": "Temperature", "value": 88.0, "max": 92.0, "parent": "/amdcpu/0"},
                       {"name": "Fan #1", "type": "Fan", "value": 1150.0, "max": 1400.0, "parent": "/lpc/nct6798d"},
                       {"name": "CPU Total", "type": "Load", "value": 12.5, "max": 100.0, "parent": "/amdcpu/0"}]}
        gpu = [{"name": "RTX", "celsius": 70.0, "fan_percent": 40.0, "load_percent": 10.0, "watts": 50.0}]
        dati = hardware.summarize_sensors(raw, gpu)
        gruppi = {t["name"]: (t["group"], t["state"]) for t in dati["temperatures"]}
        self.assertEqual(gruppi["Core (Tctl/Tdie)"], ("Processor", "warning"))
        self.assertEqual(gruppi["Samsung SSD 980"], ("Disks", "ok"))
        self.assertEqual(gruppi["Thermal zone TZ00"][0], "Motherboard / ACPI")
        self.assertEqual(gruppi["RTX"][0], "Graphics")
        ventole = {f["name"]: f for f in dati["fans"]}
        self.assertEqual(ventole["Fan #1"]["group"], "Motherboard")
        self.assertEqual(ventole["RTX fan"]["percent"], 40.0)
        self.assertEqual(dati["hottest"], 88.0)
        self.assertEqual(dati["monitor_tool"], "LibreHardwareMonitor")
        self.assertEqual(dati["other"][0]["type"], "Load")

    def test_sensor_tool_starts_only_from_protected_program_files(self):
        programmi = r"C:\Program Files"
        dentro = programmi + r"\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe\LibreHardwareMonitor.exe"
        with mock.patch.dict(hardware.os.environ, {"ProgramFiles": programmi}), \
                mock.patch.object(hardware, "monitor_tool_running", return_value=False), \
                mock.patch.object(hardware.subprocess, "Popen") as avvia:
            with mock.patch.object(hardware, "monitor_tool_path", return_value=r"C:\Users\x\AppData\Local\LibreHardwareMonitor.exe"):
                with self.assertRaises(hardware.MonitorToolError):
                    hardware.start_monitor_tool(unprotected=lambda percorsi: [])
            with mock.patch.object(hardware, "monitor_tool_path", return_value=dentro):
                visti = []
                with self.assertRaises(hardware.MonitorToolError):
                    hardware.start_monitor_tool(unprotected=lambda percorsi: visti.extend(percorsi) or [percorsi[1]])
                self.assertEqual(visti[0], dentro)
                self.assertEqual(visti[-1], programmi)  # the file and every folder up to Program Files
                avvia.assert_not_called()
                self.assertEqual(hardware.start_monitor_tool(unprotected=lambda percorsi: []), dentro)
                avvia.assert_called_once()
            with mock.patch.object(hardware, "monitor_tool_path", return_value=None):
                with self.assertRaises(hardware.MonitorToolError):
                    hardware.start_monitor_tool(unprotected=lambda percorsi: [])

    def test_empty_sensors(self):
        dati = hardware.summarize_sensors(None, [])
        self.assertEqual((dati["temperatures"], dati["fans"], dati["hottest"]), ([], [], None))


if __name__ == "__main__":
    unittest.main()
