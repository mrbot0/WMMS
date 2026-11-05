"""Tests for 2.6: Italian Toolbox, search by symptom, before/after checks, precise undo, network watch, router ports
(UPnP), Bluetooth trackers, Wi-Fi history, Windows Sandbox tests and the winget manifests. Nothing touches this PC:
registry, PowerShell, network and Sandbox are replaced by fakes."""
import base64
import json
import re
import sqlite3
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import wmm
from ottimizza_pc import Esito, Stato
from wmm import sandbox
from wmm.agent import actions, jobs, netscan, notify, radio, symptoms, undo, upnp, verify, watch
from wmm.agent.store import Store
from tests import test_api
from tests.test_disk_tools import FakeContext
from tools import winget_manifest

ROOT = Path(wmm.ROOT)


def tools_dictionary() -> dict:
    testo = (ROOT / "wmm" / "web" / "js" / "i18n_tools.js").read_text(encoding="utf-8")
    return json.loads(testo.split("window.I18N_TOOLS = ", 1)[1].rstrip().rstrip(";"))


class ItalianToolbox(unittest.TestCase):
    def test_every_tool_is_translated(self):
        dizionario = tools_dictionary()
        mancanti = [t for a in actions.CATALOG.values() for t in (a.title, a.description, a.warning) if t and t not in dizionario]
        self.assertEqual(mancanti, [])

    def test_translations_are_not_left_in_english(self):
        uguali = [k for k, v in tools_dictionary().items() if k == v and len(k) > 25]
        self.assertEqual(uguali, [])

    def test_page_loads_the_dictionary_before_i18n(self):
        html = (ROOT / "wmm" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("i18n_tools.js"), html.index("/i18n.js"))


class Symptoms(unittest.TestCase):
    def test_every_step_is_a_tool(self):
        self.assertEqual(list(symptoms.check(actions.CATALOG)), [])

    def test_common_phrases_find_their_symptom(self):
        attesi = {"non vedo gli altri PC": "lan_visibility", "Internet lento": "slow_internet", "Start non si apre": "start_menu",
                  "il disco è pieno": "disk_full", "my printer is not printing": "printer", "schermata blu": "bsod",
                  "Nessuna connessione Internet": "no_internet", "c'è un AirTag che mi segue": "tracked", "la stampante": "printer"}
        for testo, atteso in attesi.items():
            with self.subTest(testo=testo):
                trovati = symptoms.match(testo)
                self.assertTrue(trovati, testo)
                self.assertEqual(trovati[0][0].id, atteso)

    def test_unrelated_text_finds_nothing(self):
        self.assertEqual(symptoms.match("ciao"), [])
        self.assertEqual(symptoms.match("ab"), [])

    def test_reports_come_before_fixes(self):
        voce = symptoms.search("Internet lento", actions.CATALOG)[0]
        self.assertTrue(voce["reports"] and voce["fixes"])
        self.assertTrue(all(actions.CATALOG[a].kind == "report" for a in voce["reports"]))
        self.assertTrue(all(actions.CATALOG[a].kind != "report" for a in voce["fixes"]))
        self.assertTrue(voce["title_it"])


class Checks(unittest.TestCase):
    def test_checks_belong_to_fixes(self):
        for action_id in verify.CHECKS:
            with self.subTest(action_id=action_id):
                self.assertIn(action_id, actions.CATALOG)
                self.assertEqual(actions.CATALOG[action_id].kind, "fix")

    def test_verdicts(self):
        controllo = verify.Check("x", "", lambda v: v == "good")
        self.assertEqual(verify.verdict(controllo, "bad", "good"), "fixed")
        self.assertEqual(verify.verdict(controllo, "good", "good"), "already_ok")
        self.assertEqual(verify.verdict(controllo, "bad", "bad"), "not_fixed")
        self.assertEqual(verify.verdict(controllo, "good", "bad"), "worse")
        self.assertEqual(verify.verdict(controllo, None, "good"), "unknown")
        neutro = verify.Check("x", "")
        self.assertEqual(verify.verdict(neutro, "1", "2"), "changed")
        self.assertEqual(verify.verdict(neutro, "1", "1"), "unchanged")

    def test_probe_reads_before_and_after(self):
        letture = iter(["No internet, DNS fails", "Internet, DNS ok"])
        sonda = verify.Probe("network.flush_dns", runner=lambda script: next(letture))
        self.assertEqual(sonda.finish()["verdict"], "fixed")

    def test_probe_without_check_uses_the_registry_journal(self):
        sonda = verify.Probe("performance.visual_best", runner=lambda s: self.fail("no check expected"))
        self.assertIsNone(sonda.finish())
        self.assertEqual(sonda.finish([{"x": 1}], 2)["verdict"], "applied")
        self.assertEqual(sonda.finish([], 2)["verdict"], "already_set")

    def test_check_scripts_parse_as_powershell(self):
        # Every check is read-only PowerShell: a syntax error would make every verdict "Not verified". Parsed, never run.
        righe = ["$errori = @()"]
        for action_id, controllo in verify.CHECKS.items():
            codice = base64.b64encode(controllo.script.encode("utf-8")).decode()
            righe.append(f"$t = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{codice}')); $x = $null; "
                         f"[void][System.Management.Automation.Language.Parser]::ParseInput($t, [ref]$null, [ref]$x); "
                         f"if ($x) {{ $errori += '{action_id}' }}")
        righe.append("$errori -join ','")
        with tempfile.TemporaryDirectory() as cartella:  # too long for one command line: a script file
            script = Path(cartella) / "parse.ps1"
            script.write_text("\n".join(righe), encoding="utf-8-sig")
            uscita = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                    capture_output=True, text=True, timeout=120)
        self.assertEqual(uscita.stdout.strip(), "", uscita.stdout + uscita.stderr)


class Journal(unittest.TestCase):
    def setUp(self):
        self.registro = {("HKEY_CURRENT_USER", "k", "a"): (5, 4)}
        self.leggi = lambda r, k, n: self.registro.get((r, k, n))

    def test_records_first_sight_only(self):
        giornale = undo.Journal(self.leggi)
        giornale.record("HKEY_CURRENT_USER", "k", "a")
        self.registro[("HKEY_CURRENT_USER", "k", "a")] = (9, 4)
        giornale.record("HKEY_CURRENT_USER", "K", "A")
        giornale.record("HKEY_CURRENT_USER", "k", "new")
        giornale.record("HKEY_USERS", "k", "x")  # other hives are out of scope
        self.assertEqual(len(giornale.entries), 2)
        self.assertEqual(giornale.entries[0]["value"], 5)
        self.assertFalse(giornale.entries[1]["existed"])

    def test_changed_and_restore(self):
        giornale = undo.Journal(self.leggi)
        giornale.record("HKEY_CURRENT_USER", "k", "a")
        giornale.record("HKEY_CURRENT_USER", "k", "b")
        self.registro[("HKEY_CURRENT_USER", "k", "a")] = (9, 4)
        self.registro[("HKEY_CURRENT_USER", "k", "b")] = ("x", 1)
        cambiati = undo.changed(giornale.with_current())
        self.assertEqual(len(cambiati), 2)
        scritti, eliminati = [], []
        fatti, errori = undo.restore(cambiati, writer=lambda *a: scritti.append(a), deleter=lambda *a: eliminati.append(a))
        self.assertEqual((fatti, errori), (2, []))
        self.assertEqual(scritti, [("HKEY_CURRENT_USER", "k", "a", 5, 4)])
        self.assertEqual(eliminati, [("HKEY_CURRENT_USER", "k", "b")])

    def test_binary_values_survive_json(self):
        voce = {"root": "HKEY_CURRENT_USER", "key": "k", "name": "b", "existed": True}
        voce["type"], voce["value"] = undo.encode(b"\x00\x01", 3)
        voce = json.loads(json.dumps(voce))
        scritti = []
        undo.restore([voce], writer=lambda *a: scritti.append(a))
        self.assertEqual(scritti[0][3], b"\x00\x01")

    def test_write_helpers_feed_the_journal(self):
        from wmm.agent import tools
        giornale = undo.begin(self.leggi)
        try:
            with mock.patch("winreg.CreateKeyEx"), mock.patch("winreg.SetValueEx"):
                tools.write_dword("HKEY_CURRENT_USER", "k", "a", 1)
                tools.write_string("HKEY_CURRENT_USER", "k", "s", "x")
        finally:
            undo.end()
        self.assertEqual([v["name"] for v in giornale.entries], ["a", "s"])
        self.assertIs(jobs.op.REGISTRO_PRIMA_DI_SCRIVERE, undo.before_write)

    def test_declared_values_point_to_real_fixes(self):
        for action_id in undo.TOUCHES:
            self.assertIn(action_id, actions.CATALOG)


class RunnerWithChecks(unittest.TestCase):
    """A fake fix through the real job runner: the check, the journal, History and the precise undo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "wmm.db")
        self.registro = {}

        def fix(ctx):
            undo.before_write("HKEY_CURRENT_USER", "Software\\Test", "Value")
            self.registro[("HKEY_CURRENT_USER", "Software\\Test", "Value")] = (1, 4)
            return Esito(Stato.OK, "done")

        azione = actions.Action("network.flush_dns", "network", "Flush", "", "safe", 0.1, fix)
        letture = iter(["No internet, DNS fails", "Internet, DNS ok"])
        self.patches = [
            mock.patch.dict(actions.CATALOG, {"network.flush_dns": azione}, clear=True),
            mock.patch.object(jobs, "free_bytes", return_value=0),
            mock.patch.object(jobs.JobManager, "probe", staticmethod(lambda a: verify.Probe(a, runner=lambda s: next(letture)))),
            mock.patch.object(undo, "read_value", side_effect=lambda r, k, n: self.registro.get((r, k, n))),
        ]
        for patch in self.patches:
            patch.start()
        self.manager = jobs.JobManager(self.store, "PC-1")

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def test_verdict_and_undo_are_recorded(self):
        risultato = self.manager.run_sync(["network.flush_dns"], "manual", False)["results"][0]
        self.assertEqual(risultato["verify"]["verdict"], "fixed")
        self.assertEqual(risultato["undo_count"], 1)
        riga = self.store.runs("PC-1")[0]
        self.assertEqual(riga["verify"]["verdict"], "fixed")
        self.assertEqual(riga["undo_count"], 1)
        with mock.patch.object(undo, "_delete_value") as elimina:
            esito = self.manager.undo_run(riga["id"])
        self.assertEqual(esito["restored"], 1)
        elimina.assert_called_once_with("HKEY_CURRENT_USER", "Software\\Test", "Value")
        self.assertTrue(self.store.runs("PC-1")[0]["undone"])
        with self.assertRaises(ValueError):
            self.manager.undo_run(riga["id"])

    def test_preview_runs_no_check(self):
        anteprima = jobs.JobManager(self.store, "PC-1", preview=True)
        with mock.patch.object(jobs.JobManager, "probe", staticmethod(lambda a: self.fail("no check in preview"))):
            risultato = anteprima.run_sync(["network.flush_dns"], "manual", False)["results"][0]
        self.assertIsNone(risultato["verify"])


class StoreMigration(unittest.TestCase):
    def test_old_database_gets_the_new_columns(self):
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "wmm.db"
            db = sqlite3.connect(percorso)
            db.executescript("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT NOT NULL, action_id TEXT NOT NULL, "
                             "area TEXT NOT NULL, origin TEXT NOT NULL, started TEXT NOT NULL, finished TEXT, status TEXT NOT NULL DEFAULT 'running', "
                             "note TEXT NOT NULL DEFAULT '', bytes_freed INTEGER NOT NULL DEFAULT 0, log TEXT NOT NULL DEFAULT '');"
                             "INSERT INTO runs (machine_id, action_id, area, origin, started, status) VALUES ('M', 'cleanup.temp', 'cleanup', 'manual', '2026-01-01', 'ok');")
            db.commit()
            db.close()
            riga = Store(percorso).runs("M")[0]
        self.assertIsNone(riga["verify"])
        self.assertEqual(riga["undo_count"], 0)


class BluetoothTrackers(unittest.TestCase):
    def scan(self, quando, precedente, nome=""):
        return radio.mark_new({"scanned": quando, "devices": [{"address": "AA:BB:CC:00:00:01", "name": nome, "paired": False, "connected": False,
                                                              "kind": "Unnamed device"}]}, precedente)

    def test_unknown_device_seen_over_an_hour_is_flagged(self):
        dati = self.scan("2026-11-04T10:00:00", None)
        dati = self.scan("2026-11-04T10:40:00", dati)
        self.assertFalse(dati["devices"][0]["follower"])
        dati = self.scan("2026-11-04T11:10:00", dati)
        self.assertTrue(dati["devices"][0]["follower"])
        self.assertEqual(dati["followers"], ["AA:BB:CC:00:00:01"])

    def test_paired_and_known_devices_are_not_flagged(self):
        dati = None
        for ora in ("10:00", "11:00", "12:00"):
            dati = radio.mark_new({"scanned": f"2026-11-04T{ora}:00", "devices": [{"address": "AA:BB:CC:00:00:02", "paired": True, "kind": "Phone"}]}, dati)
        self.assertNotIn("follower", dati["devices"][0])
        dati = None
        for ora in ("10:00", "11:00", "12:00"):
            dati = self.scan(f"2026-11-04T{ora}:00", dati)
            dati["ignored"] = ["AA:BB:CC:00:00:01"]
        self.assertFalse(dati["devices"][0]["follower"])

    def test_mark_as_known(self):
        with tempfile.TemporaryDirectory() as cartella:
            scanner = radio.for_data_dir(Path(cartella))
            dati = None
            for ora in ("10:00", "11:00", "12:00"):
                dati = self.scan(f"2026-11-04T{ora}:00", dati)
            scanner._save(scanner.bt_path, dati)
            dopo = scanner.ignore_bluetooth("AA:BB:CC:00:00:01")
        self.assertEqual(dopo["followers"], [])
        self.assertIn("AA:BB:CC:00:00:01", dopo["ignored"])


class WifiHistory(unittest.TestCase):
    def test_samples_and_trends(self):
        with tempfile.TemporaryDirectory() as cartella:
            scanner = radio.for_data_dir(Path(cartella))
            for minuto, (ora, segnale, canale) in enumerate((("09", 80, 6), ("09", 70, 6), ("21", 30, 11))):
                scanner.add_wifi_sample({"scanned": f"2026-11-04T{ora}:{minuto:02d}:00", "connected": {"ssid": "Casa"},
                                         "networks": [{"connected": True, "ssid": "Casa", "bssid": "aa", "channel": canale, "band": "2.4 GHz",
                                                       "signal": segnale, "same_channel": 2}]})
            storia = scanner.wifi_history()
        self.assertEqual(len(storia["samples"]), 3)
        self.assertEqual(storia["worst_hour"]["hour"], 21)
        self.assertEqual(len(storia["changes"]), 1)

    def test_not_connected_records_nothing(self):
        self.assertIsNone(radio.wifi_sample({"networks": [{"connected": False}]}))


DESCRIPTION = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><friendlyName>FRITZ!Box</friendlyName>
<manufacturer>AVM</manufacturer><deviceList><device><serviceList><service><serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
<controlURL>/ctl/IPConn</controlURL></service></serviceList></device></deviceList></device></root>"""


def soap(**campi):
    corpo = "".join(f"<{k}>{v}</{k}>" for k, v in campi.items())
    return f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:R xmlns:u="x">{corpo}</u:R></s:Body></s:Envelope>'


class RouterPorts(unittest.TestCase):
    def fetch(self, url, data=None, headers=None):
        if data is None:
            return 200, DESCRIPTION
        azione = headers["SOAPAction"].split("#")[1].rstrip('"')
        if azione == "GetExternalIPAddress":
            return 200, soap(NewExternalIPAddress="203.0.113.7")
        indice = int(re.search(r"<NewPortMappingIndex>(\d+)<", data.decode()).group(1))
        voci = [dict(NewProtocol="TCP", NewExternalPort="8000", NewInternalClient="192.168.1.20", NewInternalPort="80",
                     NewPortMappingDescription="IPCam", NewEnabled="1"),
                dict(NewProtocol="UDP", NewExternalPort="3074", NewInternalClient="192.168.1.30", NewInternalPort="3074",
                     NewPortMappingDescription="Xbox", NewEnabled="1")]
        return (200, soap(**voci[indice])) if indice < len(voci) else (500, soap(errorCode="713"))

    def test_reads_every_forward_with_its_device(self):
        risposta = ["HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.1:49000/igd.xml\r\nST: x\r\n\r\n",
                    "HTTP/1.1 200 OK\r\nLOCATION: http://8.8.8.8/evil.xml\r\n\r\n"]
        dati = upnp.read([{"ip": "192.168.1.20", "name": "Camera"}], sender=lambda: risposta, fetch=self.fetch)
        self.assertEqual(dati["router"]["external_ip"], "203.0.113.7")
        self.assertEqual(dati["router"]["control"], "http://192.168.1.1:49000/ctl/IPConn")
        self.assertEqual([m["external_port"] for m in dati["mappings"]], ["8000", "3074"])
        self.assertEqual(dati["mappings"][0]["device"], "Camera")
        self.assertTrue(dati["mappings"][0]["risk"])
        self.assertEqual(dati["risky"], 1)

    def test_public_locations_are_ignored(self):
        self.assertEqual(upnp.discover(sender=lambda: ["LOCATION: http://8.8.8.8/x.xml\r\n"]), [])
        self.assertIsNone(upnp.read(sender=lambda: [], fetch=self.fetch)["router"])

    def test_doctype_is_refused(self):
        with self.assertRaises(ET.ParseError):
            upnp._parse('<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
        self.assertIsNone(upnp.parse_description('<!DOCTYPE x><root/>', "http://192.168.1.1/"))

    def test_fetch_refuses_hosts_outside_the_network(self):
        with self.assertRaises(ValueError):
            upnp._fetch("http://93.184.216.34/igd.xml")


class Watch(unittest.TestCase):
    def test_new_device_raises_an_alert(self):
        dati = {"devices": [{"ip": "192.168.1.50", "mac": "aa", "name": "", "new": True}], "networks": [], "known": [1]}
        with tempfile.TemporaryDirectory() as cartella, mock.patch.object(netscan.NetworkScanner, "run", return_value=dati), \
                mock.patch.object(notify, "safe_event") as evento:
            esito = watch.network_watch(FakeContext(), Path(cartella))
        self.assertEqual(esito.stato, Stato.AVVISO)
        self.assertEqual(evento.call_args[0][1], "new_device")

    def test_watch_reports_are_scheduled_reads(self):
        for action_id in actions.WATCH_26:
            self.assertEqual(actions.CATALOG[action_id].kind, "report")
        self.assertIn("new_device", notify.EVENTS)
        self.assertIn("bt_follower", notify.EVENTS)


class Sandbox(unittest.TestCase):
    def test_selection(self):
        tutti = sandbox.select(actions.CATALOG)
        self.assertTrue(all(actions.CATALOG[a].kind == "fix" for a in tutti))
        self.assertNotIn("security.offline_scan", tutti)
        self.assertLess(len(sandbox.select(actions.CATALOG, quick=True)), len(tutti))
        self.assertEqual(sandbox.select(actions.CATALOG, ["cleanup.temp"]), ["cleanup.temp"])
        with self.assertRaises(KeyError):
            sandbox.select(actions.CATALOG, ["nope"])

    def test_configuration_maps_the_program_read_only(self):
        with tempfile.TemporaryDirectory() as cartella:
            wsb = sandbox.prepare(["cleanup.temp", "network.flush_dns"], Path(cartella))
            radice = ET.fromstring(wsb.read_text(encoding="utf-8"))
            ids = (wsb.parent / "out" / sandbox.IDS_FILE).read_text(encoding="utf-8").split()
        cartelle = {m.findtext("SandboxFolder"): m.findtext("ReadOnly") for m in radice.iter("MappedFolder")}
        self.assertEqual(cartelle, {sandbox.BOX_REPO: "true", sandbox.BOX_PYTHON: "true", sandbox.BOX_OUT: "false"})
        self.assertIn("sandbox.py --run", radice.findtext("LogonCommand/Command"))
        self.assertEqual(ids, ["cleanup.temp", "network.flush_dns"])

    def test_inside_run_writes_results_and_tests_the_undo(self):
        with tempfile.TemporaryDirectory() as cartella:
            store = Store(Path(cartella) / "db.sqlite")
            registro = {}

            def fix(ctx):
                undo.before_write("HKEY_CURRENT_USER", "k", "v")
                registro[("HKEY_CURRENT_USER", "k", "v")] = (1, 4)
                return Esito(Stato.OK, "")

            catalogo = {"cleanup.x": actions.Action("cleanup.x", "cleanup", "X", "", "moderate", 0.1, fix)}
            with mock.patch.dict(actions.CATALOG, catalogo, clear=True), mock.patch.object(jobs, "free_bytes", return_value=0), \
                    mock.patch.object(jobs.op, "punto_ripristino", return_value=Esito(Stato.SALTATO, "")), \
                    mock.patch.object(undo, "read_value", side_effect=lambda r, k, n: registro.get((r, k, n))), \
                    mock.patch.object(undo, "_delete_value", side_effect=lambda r, k, n: registro.pop((r, k, n), None)):
                risultati = sandbox.run_inside(Path(cartella) / "out", ["cleanup.x"], manager=jobs.JobManager(store, "SB"))
                dati = json.loads((Path(cartella) / "out" / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(risultati[0]["status"], "ok")
        self.assertTrue(risultati[0]["undo_ok"])
        self.assertTrue(dati["finished"])
        self.assertEqual(dati["summary"]["undo_tested"], 1)

    def test_launch_without_sandbox_explains_how_to_turn_it_on(self):
        with mock.patch.object(sandbox, "sandbox_exe", return_value=None), mock.patch("builtins.print") as stampa:
            self.assertEqual(sandbox.launch(), 2)
        self.assertIn("Containers-DisposableClientVM", stampa.call_args[0][0])

    def test_launch_waits_for_the_results(self):
        def avvia(wsb):
            sandbox._write(wsb.parent / "out", [{"action_id": "cleanup.temp", "status": "ok"}], True)
        with tempfile.TemporaryDirectory() as cartella, mock.patch("builtins.print"):
            codice = sandbox.launch(["cleanup.temp"], data_dir=Path(cartella), starter=avvia, poll=0.01)
            self.assertTrue((Path(cartella) / "sandbox" / "report.txt").is_file())
        self.assertEqual(codice, 0)


class Winget(unittest.TestCase):
    HASH = "ab" * 32

    def test_manifests(self):
        file = winget_manifest.manifests("2.6.0", "https://github.com/mrbot0/WMMS/releases/download/v2.6.0/s.exe", self.HASH)
        self.assertEqual(len(file), 3)
        installer = file["mrbot0.WindowsMaintenanceManager.installer.yaml"]
        self.assertIn("InstallerType: inno", installer)
        self.assertIn("InstallerSha256: " + self.HASH.upper(), installer)
        self.assertIn("Python.Python.3.12", installer)
        for testo in file.values():
            self.assertIn("PackageVersion: 2.6.0", testo)
            self.assertIn("ManifestVersion: 1.6.0", testo)

    def test_bad_input_is_refused(self):
        for argomenti in (("2.6", "https://x", self.HASH), ("2.6.0", "http://x", self.HASH), ("2.6.0", "https://x", "zz")):
            with self.assertRaises(ValueError):
                winget_manifest.manifests(*argomenti)

    def test_layout(self):
        with tempfile.TemporaryDirectory() as cartella:
            percorso = winget_manifest.write(Path(cartella), "2.6.0", "https://x/s.exe", self.HASH)
            self.assertEqual(percorso.relative_to(cartella).as_posix(), "manifests/m/mrbot0/WindowsMaintenanceManager/2.6.0")

    def test_setup_script_installs_into_program_files(self):
        iss = (ROOT / "packaging" / "WindowsMaintenanceManager.iss").read_text(encoding="utf-8")
        self.assertIn(r"DefaultDirName={autopf}\WindowsMaintenanceManager", iss)
        self.assertIn("SignedUninstaller=yes", iss)
        self.assertIn("uninsneveruninstall", iss)


class V26Api(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_symptoms(self):
        stato, dati, _ = self.request("GET", "/api/v1/symptoms?q=Internet%20lento")
        self.assertEqual(stato, 200)
        self.assertEqual(dati["matches"][0]["id"], "slow_internet")
        _, dati, _ = self.request("GET", "/api/v1/symptoms")
        self.assertEqual(len(dati["symptoms"]), len(symptoms.SYMPTOMS))

    def test_actions_carry_their_check(self):
        _, dati, _ = self.request("GET", "/api/v1/actions")
        per_id = {a["id"]: a for a in dati["actions"]}
        self.assertTrue(per_id["network.flush_dns"]["check"])
        self.assertEqual(per_id["cleanup.temp"]["check"], "")

    def test_undo_of_unknown_run(self):
        stato, _, _ = self.request("POST", "/api/v1/history/runs/999999/undo")
        self.assertEqual(stato, 404)

    def test_bluetooth_ignore_validates_the_address(self):
        stato, _, _ = self.request("POST", "/api/v1/network/bluetooth/ignore", {"address": "nope"})
        self.assertEqual(stato, 400)
        stato, dati, _ = self.request("POST", "/api/v1/network/bluetooth/ignore", {"address": "aa:bb:cc:dd:ee:ff"})
        self.assertEqual(stato, 200)
        self.assertIn("AA:BB:CC:DD:EE:FF", dati["ignored"])

    def test_wifi_history_and_upnp_start_empty(self):
        stato, dati, _ = self.request("GET", "/api/v1/network/wifi/history")
        self.assertEqual((stato, dati["samples"]), (200, []))
        stato, dati, _ = self.request("GET", "/api/v1/network/upnp")
        self.assertEqual((stato, dati["mappings"]), (200, []))

    def test_upnp_scan_stores_the_result(self):
        with mock.patch.object(upnp, "read", return_value={"scanned": "2026-11-04T10:00:00", "router": None, "mappings": [], "risky": 0, "note": "x"}):
            stato, _, _ = self.request("POST", "/api/v1/network/upnp/scan")
        self.assertEqual(stato, 200)
        _, dati, _ = self.request("GET", "/api/v1/network/upnp")
        self.assertEqual(dati["note"], "x")


if __name__ == "__main__":
    unittest.main()
