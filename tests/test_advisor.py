"""Tests for scores and recommendations."""
import unittest
from datetime import datetime

from wmm.agent import advisor

GB = 1024 ** 3
MB = 1024 ** 2


def cleanup(recuperabile=0, libero=200.0, categorie=None):
    return {
        "categories": categorie or [{"id": "user_temp", "name": "User temp", "bytes": recuperabile, "files": 1}],
        "recoverable_bytes": recuperabile,
        "volumes": [{"letter": "C", "free_gb": libero, "total_gb": 400.0, "health": "Healthy"}],
        "errors": [],
    }


def integrity(**sostituzioni):
    dati = {
        "disks": [{"name": "SSD", "media": "HDD", "health": "Healthy", "wear": 1, "read_errors": 0}],
        "stability": {"unexpected_shutdowns": 0, "whea": 0, "disk_errors": 0},
        "security": {"defender": True, "firewall_off": False, "signature_age_days": 0},
        "reboot_pending": False,
        "bios_age_days": 100,
        "checks": {"integrity.sfc": {"status": "ok", "finished": datetime.now().isoformat(timespec="seconds")}},
        "errors": [],
    }
    dati.update(sostituzioni)
    return dati


def services(non_disabilitati=0, avvio=5):
    gestiti = [{"name": f"S{i}", "group": "safe", "start": "auto" if i < non_disabilitati else "disabled", "running": False} for i in range(11)]
    return {"managed": gestiti, "startup": [f"P{i}" for i in range(avvio)], "errors": []}


class Scores(unittest.TestCase):
    def test_healthy_system_scores_100(self):
        self.assertEqual(advisor.assess_cleanup(cleanup())[0], 100)
        self.assertEqual(advisor.assess_integrity(integrity())[0], 100)
        self.assertEqual(advisor.assess_services(services())[0], 100)

    def test_volume_below_15_percent(self):
        punteggio, raccomandazioni = advisor.assess_cleanup(cleanup(libero=40.0))
        self.assertLessEqual(punteggio, 75)
        self.assertEqual(raccomandazioni[0].impact, "high")

    def test_recoverable_space_penalty_and_temp_recommendation(self):
        punteggio, raccomandazioni = advisor.assess_cleanup(cleanup(recuperabile=2 * GB))
        self.assertEqual(punteggio, 96)
        self.assertIn("cleanup.temp", [r.action_id for r in raccomandazioni])

    def test_unhealthy_disk(self):
        dischi = [{"name": "HDD", "media": "HDD", "health": "Warning", "wear": None, "read_errors": None}]
        self.assertLessEqual(advisor.assess_integrity(integrity(disks=dischi))[0], 60)

    def test_old_bios_is_advice_only(self):
        punteggio, raccomandazioni = advisor.assess_integrity(integrity(bios_age_days=1000))
        self.assertEqual(punteggio, 95)
        bios = [r for r in raccomandazioni if r.id == "integrity.bios"]
        self.assertIsNone(bios[0].action_id)

    def test_shutdowns_recommend_dism_and_sfc(self):
        _, raccomandazioni = advisor.assess_integrity(integrity(stability={"unexpected_shutdowns": 6, "whea": 0, "disk_errors": 0}))
        azioni = [r.action_id for r in raccomandazioni]
        self.assertIn("integrity.dism", azioni)
        self.assertIn("integrity.sfc", azioni)

    def test_missing_sfc_check_recommends_sfc(self):
        _, raccomandazioni = advisor.assess_integrity(integrity(checks={}))
        self.assertIn("integrity.sfc", [r.action_id for r in raccomandazioni])

    def test_score_never_negative(self):
        dati = integrity(
            disks=[{"name": "D", "media": "SSD", "health": "Unhealthy", "wear": 95, "read_errors": 4}],
            stability={"unexpected_shutdowns": 50, "whea": 50, "disk_errors": 50},
            security={"defender": False, "firewall_off": True, "signature_age_days": 30},
            reboot_pending=True, bios_age_days=2000,
        )
        self.assertEqual(advisor.assess_integrity(dati)[0], 0)

    def test_services_penalties(self):
        punteggio, raccomandazioni = advisor.assess_services(services(non_disabilitati=3, avvio=30))
        self.assertEqual(punteggio, 100 - 9 - 20)
        self.assertEqual({r.action_id for r in raccomandazioni}, {"services.safe", None})

    def test_overall_score(self):
        # Only scanned areas count; weights cleanup 0.12, integrity 0.18, services 0.08.
        self.assertEqual(advisor.overall_score({"cleanup": 100, "integrity": 0, "services": 100}), 53)
        self.assertEqual(advisor.overall_score({"cleanup": 80, "network": None}), 80)
        self.assertEqual(sum(advisor.WEIGHTS.values()), 1.0)

    def test_recommendations_sorted_by_impact(self):
        _, raccomandazioni = advisor.assess_cleanup(cleanup(recuperabile=2 * GB, libero=40.0))
        self.assertEqual([r.priority for r in raccomandazioni], sorted(r.priority for r in raccomandazioni))

    def test_collection_errors_cap_score_and_lead_recommendations(self):
        dati = integrity(disks=[], errors=["System inventory: timed out"])
        punteggio, raccomandazioni = advisor.assess("integrity", dati)
        self.assertLessEqual(punteggio, 50)
        self.assertEqual(raccomandazioni[0].id, "integrity.incomplete")
        self.assertIn("timed out", raccomandazioni[0].reason)

    def test_assess_without_errors_is_unchanged(self):
        self.assertEqual(advisor.assess("integrity", integrity())[0], 100)


def performance(**s):
    dati = {"memory": {"total_gb": 32, "load_pct": 40, "commit_pct": 40}, "power": {"plan": "high"},
            "pagefile": {"automatic": True, "files": [{"name": "C:\\pagefile.sys"}]}, "uptime_hours": 10,
            "fast_startup": False, "game_dvr": False, "visual_effects": 2, "battery": False, "errors": []}
    dati.update(s)
    return dati


def storage(**s):
    dati = {"categories": [], "windows_old_bytes": 0, "storage_sense": True, "shadow": [], "volumes": [],
            "checks": {"storage.optimize_all": {"status": "ok", "finished": datetime.now().isoformat(timespec="seconds")}}, "errors": []}
    dati.update(s)
    return dati


def network(**s):
    dati = {"adapters": [{"name": "Ethernet", "status": "Up", "speed_mbps": 1000, "media": "802.3"}],
            "targets": [{"name": "Router", "avg": 1, "jitter": 0.5, "lost": 0, "sent": 4},
                        {"name": "Cloudflare", "avg": 10, "jitter": 1, "lost": 0, "sent": 4}],
            "dns_ms": 30, "dns_ok": True, "errors": []}
    dati.update(s)
    return dati


def security(**s):
    recente = datetime.now().isoformat(timespec="seconds")
    dati = {"defender": {"realtime": True, "signature_age_days": 0, "quick_scan_age_days": 1},
            "firewall": [{"name": "Domain", "enabled": True}], "uac": {"enabled": True}, "smartscreen": "Warn",
            "secure_boot": True, "tpm": {"present": True, "ready": True}, "bitlocker": [{"mount": "C:", "protection": "On"}],
            "rdp_enabled": False, "smb1": False, "admins": ["A"], "guest_enabled": False,
            "restore_points": [{"description": "x", "created": recente}], "errors": []}
    dati.update(s)
    return dati


def updates(**s):
    dati = {"search_ok": True, "pending": [], "problem_devices": [], "drivers": [], "reboot_required": False, "errors": []}
    dati.update(s)
    return dati


class NewAreas(unittest.TestCase):
    def test_healthy_new_areas_score_100(self):
        self.assertEqual(advisor.assess_performance(performance())[0], 100)
        self.assertEqual(advisor.assess_storage(storage())[0], 100)
        self.assertEqual(advisor.assess_network(network())[0], 100)
        self.assertEqual(advisor.assess_startup({"items": [], "errors": []})[0], 100)
        self.assertEqual(advisor.assess_security(security())[0], 100)
        self.assertEqual(advisor.assess_updates(updates())[0], 100)

    def test_performance_power_saver_and_memory(self):
        punteggio, racc = advisor.assess_performance(performance(power={"plan": "saver"}, memory={"total_gb": 8, "load_pct": 92, "commit_pct": 50}))
        self.assertEqual(punteggio, 100 - 15 - 20)
        self.assertIn("performance.power_balanced", [r.action_id for r in racc])

    def test_storage_browser_cache_and_windows_old(self):
        dati = storage(categories=[{"id": "browser_cache", "bytes": 900 * 1024 ** 2}], windows_old_bytes=5 * 1024 ** 3)
        punteggio, racc = advisor.assess_storage(dati)
        self.assertEqual(punteggio, 85)
        self.assertIn("storage.browser_cache", [r.action_id for r in racc])

    def test_network_loss_and_slow_dns(self):
        dati = network(dns_ms=300)
        dati["targets"][1]["lost"] = 2
        punteggio, racc = advisor.assess_network(dati)
        self.assertEqual(punteggio, 80)
        self.assertIn("network.dns_cloudflare", [r.action_id for r in racc])

    def test_network_offline(self):
        self.assertLessEqual(advisor.assess_network(network(adapters=[{"name": "Wi-Fi", "status": "Disconnected"}]))[0], 40)

    def test_startup_many_enabled(self):
        items = [{"name": f"P{i}", "enabled": i < 12} for i in range(15)]
        self.assertEqual(advisor.assess_startup({"items": items, "errors": []})[0], 88)

    def test_security_smb1_and_old_signatures(self):
        punteggio, racc = advisor.assess_security(security(smb1=True, defender={"realtime": True, "signature_age_days": 9, "quick_scan_age_days": 1}))
        self.assertEqual(punteggio, 75)
        azioni = [r.action_id for r in racc]
        self.assertIn("security.disable_smb1", azioni)
        self.assertIn("security.update_signatures", azioni)

    def test_security_no_recent_restore_point(self):
        punteggio, racc = advisor.assess_security(security(restore_points=[]))
        self.assertEqual(punteggio, 90)
        self.assertIn("security.restore_point", [r.action_id for r in racc])

    def test_firewall_off_has_one_click_fix(self):
        _, racc = advisor.assess_security(security(firewall=[{"name": "Public", "enabled": False}]))
        self.assertIn("security.firewall_on", [r.action_id for r in racc])

    def test_worn_battery_is_reported(self):
        punteggio, racc = advisor.assess_performance(performance(battery=True, battery_info={"health_pct": 55, "charge_pct": 80}))
        self.assertEqual(punteggio, 95)
        self.assertIn("performance.battery", [r.id for r in racc])

    def test_many_error_events_are_reported(self):
        punteggio, racc = advisor.assess_integrity(integrity(events={"total": 120, "top": [{"source": "disk", "count": 100}]}))
        self.assertEqual(punteggio, 95)
        self.assertIn("integrity.events", [r.id for r in racc])

    def test_updates_pending_and_devices(self):
        dati = updates(pending=[{"title": "Sec", "severity": "Critical"}, {"title": "Other", "severity": ""}],
                       problem_devices=[{"name": "USB"}], reboot_required=True)
        punteggio, racc = advisor.assess_updates(dati)
        self.assertEqual(punteggio, 100 - 10 - 3 - 10 - 10)
        self.assertIn("updates.install", [r.action_id for r in racc])


if __name__ == "__main__":
    unittest.main()
