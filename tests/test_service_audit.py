"""Tests for the service analysis: rules that work on any PC, what is never touched, applying and the API."""
import unittest
from unittest import mock

import ottimizza_pc as op
from tests import test_api
from wmm.agent import actions, advisor, service_audit

MS = "Microsoft Corporation"
W = r"C:\Windows\System32\svchost.exe"


def svc(name, start="Auto", state="Running", company=MS, path=W, display=None, memory=0, shared=1, delayed=False):
    return {"name": name, "display": display or name, "start": start, "state": state, "company": company, "path": path,
            "memory_mb": memory, "shared": shared, "delayed": delayed}


CASA = {"printers": 1, "bluetooth": 1, "biometric": 1, "scanners": 1, "smartcard": 0, "xbox": True, "phone_link": True,
        "domain": False, "mdm": False, "ssd": True}


def analizza(servizi, **contesto):
    return service_audit.analyze({"services": servizi, "context": dict(CASA, **contesto)})


def per_nome(analisi):
    return {f["name"]: f for f in analisi["findings"]}


class Rules(unittest.TestCase):
    def test_microsoft_telemetry_and_unused_are_selected(self):
        r = per_nome(analizza([svc("DiagTrack"), svc("RetailDemo", "Manual", "Stopped"), svc("Fax", "Manual", "Stopped"),
                               svc("RemoteRegistry", "Manual", "Stopped"), svc("Spooler")]))
        self.assertEqual((r["DiagTrack"]["category"], r["DiagTrack"]["target"], r["DiagTrack"]["selected"]), ("telemetry", "disabled", True))
        self.assertEqual(r["RemoteRegistry"]["category"], "insecure")
        self.assertTrue(r["Fax"]["selected"] and r["RetailDemo"]["selected"])
        self.assertNotIn("Spooler", r)  # this PC has a printer

    def test_nothing_from_a_fixed_list_of_one_pc(self):
        # The services of the PC the suite was written on are judged like any other.
        self.assertEqual(op.SERVIZI_MANUALI, ())
        r = per_nome(analizza([svc("AorusLcdService", company="", path=r"C:\Program Files\GIGABYTE\Control Center\Lib\GBT_VGA\Service\AorusLcdService.exe"),
                               svc("AsusCertService", company="Asustek Computer Inc.", path=r"C:\Program Files (x86)\ASUS\AsusCertService\AsusCertService.exe")]))
        self.assertEqual(r, {})  # hardware makers' tools stay

    def test_already_at_target_is_not_proposed(self):
        self.assertEqual(analizza([svc("DiagTrack", "Disabled", "Stopped"), svc("edgeupdate", "Manual", "Stopped")])["findings"], [])

    def test_protected_and_security_software_are_never_proposed(self):
        servizi = [svc("WinDefend"), svc("wuauserv"), svc("BITS"),
                   svc("MBAMService", company="Malwarebytes", path=r"C:\Program Files\Malwarebytes\Anti-Malware\MBAMService.exe", memory=400),
                   svc("AvastUpdate", company="Avast Software", path=r"C:\Program Files\Avast\update.exe", display="Avast Update Service"),
                   svc("vgc", company="Riot Games, Inc.", path=r"C:\Program Files\Riot Vanguard\vgc.exe"),
                   svc("VBoxSDS", company="Oracle", path=r"C:\Program Files\Oracle\VirtualBox\VBoxSDS.exe"),
                   svc("DbxSvc", company="Dropbox, Inc.", path=r"C:\Program Files\Dropbox\Client\DbxSvc.exe", display="Dropbox Service"),
                   svc("RtkAudioUniversalService", company="Realtek Semiconductor", path=r"C:\Windows\System32\RtkAudUService64.exe")]
        self.assertEqual(analizza(servizi)["findings"], [])

    def test_third_party_updaters_go_to_manual(self):
        r = per_nome(analizza([svc("gupdate", "Auto", "Stopped", "Google LLC", r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe", delayed=True),
                               svc("AdobeARMservice", company="Adobe Inc.", path=r"C:\Program Files (x86)\Common Files\Adobe\ARM\1.0\armsvc.exe",
                                   display="Adobe Acrobat Update Service"),
                               svc("MozillaMaintenance", "Manual", "Stopped", "Mozilla Foundation", r"C:\Program Files (x86)\Mozilla Maintenance Service\maintenanceservice.exe"),
                               svc("edgeupdate", delayed=True, path=r"C:\Program Files (x86)\Microsoft\EdgeUpdate\MicrosoftEdgeUpdate.exe")]))
        self.assertEqual({n: (f["category"], f["start"], f["target"], f["selected"]) for n, f in r.items()},
                         {"gupdate": ("updater", "delayed-auto", "demand", True), "AdobeARMservice": ("updater", "auto", "demand", True),
                          "edgeupdate": ("updater", "delayed-auto", "demand", True)})  # Mozilla is already Manual

    def test_hardware_makers_telemetry_goes_but_their_tools_stay(self):
        r = per_nome(analizza([svc("NvTelemetryContainer", company="NVIDIA Corporation", path=r"C:\Program Files\NVIDIA Corporation\NvTelemetry\NvTelemetryContainer.exe",
                                   display="NVIDIA Telemetry Container"),
                               svc("HpTouchpointAnalyticsService", company="HP Inc.", path=r"C:\Windows\System32\DriverStore\FileRepository\hpa\TouchpointAnalyticsClientService.exe"),
                               svc("NvContainerLocalSystem", company="NVIDIA Corporation", path=r"C:\Program Files\NVIDIA Corporation\NvContainer\nvcontainer.exe", memory=300)]))
        self.assertEqual(sorted(r), ["HpTouchpointAnalyticsService", "NvTelemetryContainer"])
        self.assertTrue(all(f["category"] == "telemetry" and f["target"] == "disabled" for f in r.values()))

    def test_review_only_findings_are_not_ticked(self):
        r = per_nome(analizza([svc("TeamViewer", company="TeamViewer Germany GmbH", path=r"C:\Program Files\TeamViewer\TeamViewer_Service.exe"),
                               svc("odd", company="", path=r"C:\Users\x\AppData\Roaming\odd\svc.exe"),
                               svc("BigSvc", company="Some Vendor", path=r"C:\Program Files\Some Vendor\big.exe", memory=400),
                               svc("SharedBig", company="Some Vendor", path=r"C:\Program Files\Some Vendor\shared.exe", memory=400, shared=3),
                               svc("SysMain")], ssd=True))
        self.assertEqual({n: (f["category"], f["selected"]) for n, f in r.items()},
                         {"TeamViewer": ("remote", False), "odd": ("suspicious", False), "BigSvc": ("heavy", False), "SysMain": ("heavy", False)})
        self.assertNotIn("SysMain", per_nome(analizza([svc("SysMain")], ssd=False)))  # it helps a hard disk

    def test_hardware_and_apps_this_pc_does_not_have(self):
        servizi = [svc("bthserv", "Auto", "Running"), svc("BTAGService", "Manual", "Running"), svc("WbioSrvc", "Auto", "Stopped"), svc("XblAuthManager", "Manual", "Stopped"),
                   svc("XboxGipSvc", "Manual", "Stopped"), svc("PhoneSvc", "Manual", "Stopped"), svc("Spooler"), svc("SCardSvr", "Manual", "Stopped")]
        r = per_nome(analizza(servizi, bluetooth=0, biometric=0, xbox=False, phone_link=False, printers=0))
        self.assertEqual((r["bthserv"]["target"], r["WbioSrvc"]["target"]), ("demand", "demand"))
        self.assertEqual(r["XblAuthManager"]["target"], "disabled")
        self.assertNotIn("XboxGipSvc", r)  # Xbox controllers work without the app
        self.assertNotIn("SCardSvr", r)  # already Manual and not running: nothing to gain
        self.assertNotIn("BTAGService", r)  # already Manual: its start type cannot go lower without disabling Bluetooth audio for good
        self.assertFalse(r["Spooler"]["selected"])  # Print to PDF needs it: review only
        self.assertTrue(r["PhoneSvc"]["selected"])
        # The same services on a PC with that hardware and those apps: nothing.
        self.assertEqual(analizza(servizi)["findings"], [])

    def test_company_pcs_leave_updaters_and_remote_management_to_it(self):
        servizi = [svc("RemoteRegistry", "Manual", "Stopped"), svc("WinRM"), svc("dmwappushservice", "Manual", "Stopped"), svc("DiagTrack"),
                   svc("gupdate", company="Google LLC", path=r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe")]
        a = analizza(servizi, domain=True)
        r = per_nome(a)
        self.assertTrue(a["managed"])
        self.assertFalse(r["RemoteRegistry"]["selected"] or r["gupdate"]["selected"])
        self.assertNotIn("WinRM", r)
        self.assertNotIn("dmwappushservice", r)
        self.assertTrue(r["DiagTrack"]["selected"])
        self.assertTrue(per_nome(analizza(servizi))["WinRM"]["selected"])  # the same on a home PC

    def test_microsoft_detection(self):
        self.assertTrue(service_audit.is_microsoft(svc("x", company="Windows (R) Win 7 DDK provider")))
        self.assertTrue(service_audit.is_microsoft(svc("x", company="", path=r"C:\WINDOWS\system32\x.exe")))
        self.assertFalse(service_audit.is_microsoft(svc("x", company="", path=r"C:\Program Files\x\x.exe")))
        # A service whose program cannot be read is not judged.
        self.assertEqual(analizza([svc("LSM", "Unknown", company="", path="")])["findings"], [])
        # Word boundaries: GameInputRedistService is not a Redis database.
        self.assertIsNone(service_audit.KEEP_ALWAYS.search("GameInputRedistService"))
        self.assertIsNotNone(service_audit.KEEP_ALWAYS.search("MySQL80"))

    def test_bad_input(self):
        self.assertEqual(service_audit.analyze(None)["findings"], [])
        # A single service comes from PowerShell as an object, not a list.
        uno = service_audit.analyze({"services": {"name": "DiagTrack", "start": "Auto", "company": MS, "path": W}, "context": None})
        self.assertEqual(uno["findings"][0]["name"], "DiagTrack")


class Applying(unittest.TestCase):
    def test_each_finding_goes_to_its_own_target_through_the_backup(self):
        a = analizza([svc("DiagTrack"), svc("gupdate", company="Google LLC", path=r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe"),
                      svc("TeamViewer", company="TeamViewer", path=r"C:\Program Files\TeamViewer\TeamViewer_Service.exe")])
        ctx = op.Contesto(anteprima=True)
        with mock.patch.object(op, "imposta_servizi", return_value=(1, 0)) as imposta:
            esito = service_audit.apply(ctx, a["findings"])
        self.assertEqual(sorted((c.args[1], c.args[2]) for c in imposta.call_args_list), [(["DiagTrack"], "disabled"), (["gupdate"], "demand")])
        self.assertEqual(esito.stato, op.Stato.ANTEPRIMA)
        with mock.patch.object(op, "imposta_servizi", return_value=(1, 0)) as imposta:
            service_audit.apply(ctx, a["findings"], ["TeamViewer"])  # a review item, chosen by the user
        self.assertEqual(imposta.call_args.args[1:], (["TeamViewer"], "demand"))
        self.assertEqual(service_audit.apply(ctx, []).stato, op.Stato.OK)

    def test_the_action_analyses_this_pc_first(self):
        a = analizza([svc("DiagTrack")])
        with mock.patch.object(service_audit, "collect", return_value=a) as raccolta, \
                mock.patch.object(op, "imposta_servizi", return_value=(1, 0)) as imposta:
            actions.CATALOG["services.safe"].run(op.Contesto(anteprima=True))
        raccolta.assert_called_once()
        self.assertEqual(imposta.call_args.args[1:], (["DiagTrack"], "disabled"))

    def test_advisor_counts_what_the_analysis_would_change(self):
        a = analizza([svc("DiagTrack"), svc("TeamViewer", company="TeamViewer", path=r"C:\Program Files\TeamViewer\TeamViewer_Service.exe")])
        punteggio, racc = advisor.assess_services({"audit": a, "startup": [], "errors": []})
        self.assertEqual(punteggio, 97)  # only the ticked one counts
        self.assertTrue(racc[0].reason.startswith("1 services can be turned off"))


class AuditApi(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request
    admin = True

    def test_analysis_and_applying_only_what_it_proposes(self):
        a = analizza([svc("DiagTrack"), svc("gupdate", company="Google LLC", path=r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe")])
        with mock.patch.object(service_audit, "collect", return_value=a):
            stato, dati, _ = self.request("GET", "/api/v1/services/audit")
            self.assertEqual((stato, [f["name"] for f in dati["findings"]]), (200, ["DiagTrack", "gupdate"]))
            with mock.patch.object(op, "imposta_servizi", return_value=(1, 0)) as imposta:
                stato, dati, _ = self.request("POST", "/api/v1/services/audit/apply", {"services": ["DiagTrack"]})
            self.assertEqual((stato, dati["changed"]), (200, ["DiagTrack"]))
            self.assertEqual(imposta.call_args.args[1:], (["DiagTrack"], "disabled"))
            self.assertEqual(dati["restore_point"], 7)
            # A service the analysis does not propose (here: Windows Update) cannot be changed through this route.
            stato, dati, _ = self.request("POST", "/api/v1/services/audit/apply", {"services": ["wuauserv"]})
            self.assertEqual(stato, 400)
            self.assertIn("wuauserv", dati["error"])
            self.assertEqual(self.request("POST", "/api/v1/services/audit/apply", {"services": []})[0], 400)
            self.assertEqual(self.request("POST", "/api/v1/services/audit/apply", {"services": "DiagTrack"})[0], 400)


if __name__ == "__main__":
    unittest.main()
