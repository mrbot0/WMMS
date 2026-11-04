"""Agent features that live apart from the core API: Applications (scan, uninstall, leftovers, Store apps, browser
caches, updates, rules), System Restore, alerts by email and Telegram, program updates and the PCs of the network.
wmm/server/api.py mixes these classes into Agent and Handler and appends FEATURE_ROUTES to its routes."""
from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Dict

import hashlib
from concurrent.futures import ThreadPoolExecutor
import sys

import wmm

from ..agent import actions, advisor, apps, fleet, netscan, notify, radio, registry, restore, updater
from .errors import ApiError


class AgentFeatures:
    # ---------- applications ----------

    def apps(self, refresh: bool = False) -> dict:
        """The last applications scan; the first call (or refresh) scans, which takes a few seconds."""
        with self._apps_lock:
            if refresh or self._apps is None:
                self._apps = apps.scan(self._context())
                self._alert_unsafe(self._apps)
            return self._apps

    def _alert_unsafe(self, dati: dict) -> None:
        """An alert when the set of unsafe programs changes (the same set is not reported again for a day)."""
        rischio = [a for a in dati.get("apps", []) if a.get("status") == "risk"]
        if not rischio or self.preview:
            return
        nomi = sorted(f"{a['name']} {a.get('version', '')}".strip() for a in rischio)
        firma = hashlib.sha1("|".join(nomi).encode("utf-8")).hexdigest()[:12]
        testo = "Unsafe programs on this PC:\n" + "\n".join("- " + n for n in nomi[:20]) + "\n\nOpen Applications in the console to update or remove them."
        notify.safe_event(self.data_dir, "unsafe_apps", testo, gruppo=firma)

    def _alert_disk(self, system: dict) -> None:
        """An alert when the system drive has less than 10% or 10 GB free."""
        if self.preview:
            return
        for volume in system.get("volumes") or []:
            libero, totale = volume.get("free_gb"), volume.get("total_gb")
            if volume.get("letter") == "C" and libero is not None and totale and (libero < 10 or libero / totale < 0.10):
                notify.safe_event(self.data_dir, "disk_low", f"Drive C: has {libero:.1f} GB free of {totale:.0f} GB "
                                  f"({libero / totale:.0%}). Open Cleanup and Storage in the console to free space.", gruppo="C")

    # ---------- network scanner (read-only) ----------

    def network_devices(self) -> dict:
        return netscan.for_data_dir(self.data_dir).last() or {"devices": [], "networks": [], "scanned": None, "missing": []}

    def scan_interfaces(self) -> dict:
        """The interfaces each scanner can use, the active one marked as the default."""
        with ThreadPoolExecutor(max_workers=3) as pool:
            rete, wifi, bt = pool.submit(netscan.local_networks), pool.submit(radio.wifi_interfaces), pool.submit(radio.bluetooth_radios)
            return {"devices": rete.result(), "wifi": wifi.result(), "bluetooth": bt.result()}

    def network_scan(self, alias=None) -> dict:
        """Scans the local network of one adapter (the active one by default); read-only, so it also runs in preview mode."""
        if alias is not None and (not isinstance(alias, str) or len(alias) > 256):
            raise ApiError(400, "Invalid adapter name.")
        if not self._netscan_lock.acquire(blocking=False):
            raise ApiError(409, "A network scan is already running.")
        task_id = self.tasks.start("scan", "Network scan", 2)
        stato = "error"
        try:
            esito = netscan.for_data_dir(self.data_dir).run(progress=lambda testo: self.tasks.step(task_id, testo), alias=alias or None)
            stato = "ok"
            return esito
        except ValueError as errore:  # an adapter that is not there (unplugged since the page loaded)
            raise ApiError(400, str(errore)) from None
        except (OSError, subprocess.SubprocessError) as errore:
            raise ApiError(500, f"The network scan failed: {errore}") from None
        finally:
            self.tasks.finish(task_id, stato)
            self._netscan_lock.release()

    # ---------- Wi-Fi and Bluetooth scanners (read-only) ----------

    def radio_last(self, tipo: str) -> dict:
        scanner = radio.for_data_dir(self.data_dir)
        dati = scanner.last_wifi() if tipo == "wifi" else scanner.last_bluetooth()
        return dati or {"networks": [], "devices": [], "scanned": None}

    def radio_scan(self, tipo: str, nome=None) -> dict:
        """Listens for Wi-Fi networks or Bluetooth devices nearby; nothing is joined or paired, so it runs in preview too.
        Wi-Fi uses the chosen adapter (the connected one by default); Windows always searches Bluetooth with its active adapter."""
        if nome is not None and (not isinstance(nome, str) or len(nome) > 256):
            raise ApiError(400, "Invalid adapter name.")
        if not self._netscan_lock.acquire(blocking=False):
            raise ApiError(409, "Another scan is already running.")
        task_id = self.tasks.start("scan", "Wi-Fi scan" if tipo == "wifi" else "Bluetooth scan", 1)
        stato = "error"
        try:
            scanner = radio.for_data_dir(self.data_dir)
            esito = scanner.run_wifi(nome or None) if tipo == "wifi" else scanner.run_bluetooth()
            stato = "warning" if esito.get("error") else "ok"
            return esito
        except ValueError as errore:  # an adapter that is not there (unplugged since the page loaded)
            raise ApiError(400, str(errore)) from None
        except (OSError, subprocess.SubprocessError) as errore:
            raise ApiError(500, f"The scan failed: {errore}") from None
        finally:
            self.tasks.finish(task_id, stato)
            self._netscan_lock.release()

    # ---------- the PCs of the network (read-only summaries) ----------

    @property
    def fleet(self) -> fleet.Fleet:
        return fleet.for_data_dir(self.data_dir)

    def pc_summary(self) -> dict:
        """What this PC shares: scores, counts and free space; no files, users or settings, nothing that can change it."""
        ultime = self._latest()
        punteggi = {a: (s["score"] if s else None) for a, s in ultime.items()}
        presenti = {a: v for a, v in punteggi.items() if v is not None}
        try:
            problemi = len(self.recommendations(ultime))
        except Exception:  # noqa: BLE001 - a summary without the count is still useful
            problemi = None
        sistema = self.store.last_scan(self.machine_id, "system")
        volumi = ((sistema or {}).get("data") or {}).get("volumes") or []
        c = next((v for v in volumi if v.get("letter") == "C"), {})
        insicuri = [a["name"] for a in self._apps.get("apps", []) if a.get("status") == "risk"] if self._apps else None
        scansioni = [s["created"] for s in ultime.values() if s]
        return {
            "hostname": self.hostname, "machine_id": self.machine_id, "version": wmm.VERSION,
            "overall": advisor.overall_score(presenti) if presenti else None, "scores": punteggi, "open_issues": problemi,
            "unsafe_apps": insicuri, "c_free_gb": c.get("free_gb"), "c_total_gb": c.get("total_gb"),
            "last_scan": max(scansioni) if scansioni else None, "uptime_seconds": int(time.time() - self.started),
        }

    def start_fleet_share(self) -> None:
        """(Re)starts the summary server when sharing is on; never in preview mode."""
        vecchio = getattr(self, "_fleet_server", None)
        if vecchio is not None:
            vecchio.shutdown()
            vecchio.server_close()
            self._fleet_server = None
        stato = self.fleet.share()
        if not stato["enabled"] or self.preview:
            return
        try:
            self._fleet_server = fleet.summary_server(self.fleet, stato["port"], self.pc_summary)
        except OSError as errore:
            sys.stderr.write(f"PC summary sharing could not start on port {stato['port']}: {errore}\n")

    def fleet_view(self) -> dict:
        condivisione = dict(self.fleet.share(), running=getattr(self, "_fleet_server", None) is not None)
        return {"share": condivisione, "this_pc": self.pc_summary(), "pcs": self.fleet.gather()}

    def fleet_share(self, corpo: dict) -> dict:
        self._guard_changes()
        if self.preview:
            raise ApiError(409, "Sharing cannot be turned on in preview mode.")
        try:
            stato = self.fleet.set_share(corpo.get("enabled"), corpo.get("port"))
        except fleet.FleetError as errore:
            raise ApiError(400, str(errore)) from None
        self.start_fleet_share()
        return dict(stato, running=getattr(self, "_fleet_server", None) is not None)

    def fleet_key(self) -> dict:
        self._guard_changes()
        return {"key": self.fleet.new_key(), "note": "Shown only now: copy it into the console of the other PC."}

    def fleet_firewall(self) -> dict:
        porta = self.fleet.share()["port"]
        return self._logged_change("integrity.fleet_firewall", f"Allow the local network to read the PC summary (TCP {porta})",
                                   lambda: fleet.firewall_rule(porta))

    def fleet_add(self, corpo: dict) -> dict:
        self._guard_changes()
        try:
            return self.fleet.add(corpo.get("name"), corpo.get("address"), corpo.get("port"), corpo.get("key"))
        except fleet.FleetError as errore:
            raise ApiError(400, str(errore)) from None

    def fleet_remove(self, pc_id: str) -> dict:
        self._guard_changes()
        if not self.fleet.remove(pc_id):
            raise ApiError(404, "PC not found.")
        return {"ok": True}

    # ---------- program updates (GitHub releases) ----------

    def update_check(self) -> dict:
        try:
            return updater.check()
        except updater.UpdateError as errore:
            raise ApiError(502, str(errore)) from None

    def update_install(self) -> dict:
        self._guard_changes()
        rilascio = self.update_check()
        if not rilascio.get("available"):
            raise ApiError(409, rilascio.get("reason") or f"Version {rilascio.get('current')} is already the latest.")

        def cambia() -> dict:
            try:
                return updater.install(rilascio, self.data_dir)
            except (updater.UpdateError, ValueError) as errore:
                raise OSError(str(errore)) from None  # recorded in History as a failed update
        esito = self._logged_change("agent.update", f"Update Windows Maintenance Manager to {rilascio['version']}", cambia)
        return dict(esito, restart=not esito.get("preview"))

    # ---------- alerts by email and Telegram ----------

    @property
    def notifier(self) -> notify.Notifier:
        return notify.for_data_dir(self.data_dir)

    def notification_settings(self) -> dict:
        return self.notifier.settings()

    def save_notification_settings(self, corpo: dict) -> dict:
        self._guard_changes()
        try:
            return self.notifier.save(corpo)
        except (notify.NotifyError, OSError) as errore:
            raise ApiError(400, str(errore)) from None

    def test_notification(self) -> dict:
        self._guard_changes()
        if not self.notifier.channels(self.notifier._read()):
            raise ApiError(409, "Set up Telegram or email first.")
        esiti = self.notifier.send("Test alert", "If you read this, the alerts of Windows Maintenance Manager reach you.")
        return {"results": esiti, "ok": all(v == "ok" for v in esiti.values())}

    def _installed(self, app_id: str) -> dict:
        # Read again from the registry: the command that runs is the one Windows has now, never one sent by the page.
        voce = next((a for a in apps.read_installed() if a["id"] == app_id), None)
        if voce is None:
            raise ApiError(404, "Program not found: it may be already removed. Scan again.")
        return voce

    def app_uninstall(self, app_id: str, senza_punto: bool = False) -> dict:
        voce = self._installed(app_id)
        if not voce["uninstall"]:
            raise ApiError(409, f"{voce['name']} has no uninstaller: use Remove entry if the program is already gone.")
        esito = self._logged_change("apps.uninstall", f"Start the uninstaller of {voce['name']} {voce['version']}".strip(),
                                    lambda: apps.run_uninstaller(voce), punto=True, senza_punto=senza_punto)
        if not esito.get("preview"):
            self._uninstalls[app_id] = {"app": voce, "pid": esito.get("pid"), "started": time.time()}
        return esito

    def uninstall_status(self, app_id: str) -> dict:
        """Is the uninstaller still running, is the program gone, and what did it leave behind?"""
        voce = self._uninstalls.get(app_id)
        if voce is None:
            raise ApiError(404, "No uninstall of this program was started by this console.")
        in_corso = apps.is_running(voce["pid"])
        installati = apps.read_installed()
        rimosso = not any(a["id"] == app_id for a in installati)
        stato = {"running": in_corso, "removed": rimosso, "name": voce["app"]["name"], "seconds": int(time.time() - voce["started"])}
        if rimosso and not in_corso:
            if "leftovers" not in voce:
                voce["leftovers"] = apps.leftovers(voce["app"], installati)
                with self._apps_lock:
                    self._apps = None  # the next visit scans again
            stato["leftovers"] = voce["leftovers"]
        return stato

    def clean_leftovers(self, app_id: str, ids) -> dict:
        voce = self._uninstalls.get(app_id)
        if voce is None or "leftovers" not in voce:
            raise ApiError(409, "Leftovers are offered only after the program is gone.")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ApiError(400, "'ids' must be a list.")
        scelti = [l for l in voce["leftovers"] if l["id"] in ids]
        if not scelti:
            raise ApiError(400, "Select at least one leftover.")

        def cambia() -> dict:
            fatti, errori = [], []
            for voce_ in scelti:
                try:
                    if voce_["kind"] == "folder":
                        apps.recycle(voce_["path"])
                    else:
                        self.registry.delete_key(voce_["path"])
                    fatti.append(voce_["path"])
                except (OSError, ValueError, registry.RegistryError) as errore:
                    errori.append(f"{voce_['path']}: {errore}")
            voce["leftovers"] = [l for l in voce["leftovers"] if l["path"] not in fatti]
            return {"removed": fatti, "errors": errori}
        return self._logged_change("apps.leftovers", f"Remove {len(scelti)} leftover(s) of {voce['app']['name']}", cambia)

    def app_remove_entry(self, app_id: str) -> dict:
        voce = self._installed(app_id)
        if not voce["broken"]:
            raise ApiError(409, "Only entries whose uninstaller is gone can be removed this way: use Uninstall.")
        return self._logged_change("apps.remove_entry", f"Remove the leftover entry of {voce['name']}",
                                   lambda: self.registry.delete_key(voce["key"]))

    def app_open_folder(self, app_id: str) -> dict:
        voce = self._installed(app_id)
        if not voce["folder"] or not os.path.isdir(voce["folder"]):
            raise ApiError(404, "The install folder of this program is not known or no longer exists.")
        subprocess.Popen(["explorer.exe", voce["folder"]])
        return {"ok": True, "folder": voce["folder"]}

    def app_size(self, app_id: str) -> dict:
        voce = self._installed(app_id)
        return {"id": app_id, "size_mb": apps.folder_size(voce["folder"])}

    def store_remove(self, app_id: str, senza_punto: bool = False) -> dict:
        elenco = self.apps()["store"]
        voce = next((s for s in elenco if s["id"] == app_id), None)
        if voce is None:
            raise ApiError(404, "Store app not found. Scan again.")
        return self._logged_change("apps.store_remove", f"Remove the Store app {voce['name']}", lambda: apps.remove_store_app(voce["package"]),
                                   punto=True, senza_punto=senza_punto)

    def browser_clean(self, browser_id: str) -> dict:
        if browser_id not in {b[0] for b in apps.BROWSER_PROFILES}:
            raise ApiError(404, "Unknown browser.")
        nome = next(b[1] for b in apps.BROWSER_PROFILES if b[0] == browser_id)
        esito = self._logged_change("apps.browser_cache", f"Clear the {nome} cache", lambda: apps.clean_browser(browser_id))
        with self._apps_lock:
            if self._apps is not None:
                self._apps["browsers"] = apps.browser_caches()
        return esito

    def app_rules(self) -> dict:
        return dict(apps.RULES_INFO, url=apps.RULES_URL)

    def update_app_rules(self) -> dict:
        """Downloads the rules from the project repository (only data: patterns and dates, never code)."""
        try:
            esito = apps.update_rules()
        except (OSError, ValueError) as errore:
            raise ApiError(502, f"The rules could not be updated: {errore}") from None
        if esito.get("updated"):
            with self._apps_lock:
                self._apps = None  # the verdicts change: scan again on the next visit
        return esito

    def app_updates(self) -> dict:
        try:
            return {"updates": apps.winget_updates()}
        except subprocess.TimeoutExpired:
            raise ApiError(504, "winget did not answer within two minutes.") from None
        except OSError as errore:
            raise ApiError(409, str(errore)) from None

    def app_update(self, package_id) -> dict:
        if not isinstance(package_id, str) or not re.fullmatch(r"[\w.\-+]{2,128}", package_id):
            raise ApiError(400, "Invalid winget package id.")
        return self._logged_change("apps.update", f"Update {package_id} with winget", lambda: apps.winget_upgrade(package_id))

    # ---------- System Restore: list and way back ----------

    def restore_points(self) -> dict:
        if not self.admin:
            return {"points": [], "note": "Only a console running as administrator can read the restore points."}
        try:
            return {"points": restore.points()}
        except (OSError, subprocess.SubprocessError) as errore:
            raise ApiError(500, f"Could not read the restore points: {errore}") from None

    def open_system_restore(self) -> dict:
        def apri() -> dict:
            restore.open_wizard()
            return {"opened": "rstrui.exe"}
        return self._logged_change("integrity.system_restore", "Open System Restore", apri)


class HandlerFeatures:
    def radio_get(self, query, tipo):
        self._json(200, self.agent.radio_last(tipo))

    def radio_scan_post(self, query, tipo):
        self._json(200, self.agent.radio_scan(tipo, self._body().get("interface")))

    def scan_interfaces_get(self, query):
        self._json(200, self.agent.scan_interfaces())

    def network_devices(self, query):
        self._json(200, self.agent.network_devices())

    def network_scan(self, query):
        self._json(200, self.agent.network_scan(self._body().get("interface")))

    def fleet_get(self, query):
        self._json(200, self.agent.fleet_view())

    def fleet_share_put(self, query):
        self._json(200, self.agent.fleet_share(self._body()))

    def fleet_key_post(self, query):
        self._json(200, self.agent.fleet_key())

    def fleet_firewall_post(self, query):
        self._json(200, self.agent.fleet_firewall())

    def fleet_add_post(self, query):
        self._json(201, self.agent.fleet_add(self._body()))

    def fleet_remove_delete(self, query, pc_id):
        self._json(200, self.agent.fleet_remove(pc_id))

    def update_check(self, query):
        self._json(200, self.agent.update_check())

    def update_install(self, query):
        self._json(200, self.agent.update_install())

    def notification_get(self, query):
        self._json(200, self.agent.notification_settings())

    def notification_put(self, query):
        self._json(200, self.agent.save_notification_settings(self._body()))

    def notification_test(self, query):
        self._json(200, self.agent.test_notification())

    def app_list(self, query):
        self._json(200, self.agent.apps(refresh=query.get("refresh") == "1"))

    def app_operation(self, query, app_id, operazione):
        if operazione == "uninstall":
            self._json(200, self.agent.app_uninstall(app_id, self._body().get("no_restore_point") is True))
            return
        metodo = {"remove-entry": self.agent.app_remove_entry, "open-folder": self.agent.app_open_folder, "size": self.agent.app_size}[operazione]
        self._json(200, metodo(app_id))

    def uninstall_status(self, query, app_id):
        self._json(200, self.agent.uninstall_status(app_id))

    def clean_leftovers(self, query, app_id):
        self._json(200, self.agent.clean_leftovers(app_id, self._body().get("ids")))

    def store_remove(self, query, app_id):
        self._json(200, self.agent.store_remove(app_id, self._body().get("no_restore_point") is True))

    def restore_list(self, query):
        self._json(200, self.agent.restore_points())

    def restore_open(self, query):
        self._json(200, self.agent.open_system_restore())

    def browser_clean(self, query, browser_id):
        self._json(200, self.agent.browser_clean(browser_id))

    def app_updates(self, query):
        self._json(200, self.agent.app_updates())

    def app_rules(self, query):
        self._json(200, self.agent.app_rules())

    def update_app_rules(self, query):
        self._json(200, self.agent.update_app_rules())

    def app_update(self, query):
        self._json(200, self.agent.app_update(self._body().get("id")))


# (method, path pattern under /api/v1, handler)
FEATURE_ROUTES = [
    ("GET", "/network/interfaces", HandlerFeatures.scan_interfaces_get),
    ("GET", r"/network/(wifi|bluetooth)", HandlerFeatures.radio_get),
    ("POST", r"/network/(wifi|bluetooth)/scan", HandlerFeatures.radio_scan_post),
    ("GET", "/network/devices", HandlerFeatures.network_devices),
    ("POST", "/network/scan", HandlerFeatures.network_scan),
    ("GET", "/fleet", HandlerFeatures.fleet_get),
    ("PUT", "/fleet/share", HandlerFeatures.fleet_share_put),
    ("POST", "/fleet/share/key", HandlerFeatures.fleet_key_post),
    ("POST", "/fleet/share/firewall", HandlerFeatures.fleet_firewall_post),
    ("POST", "/fleet/pcs", HandlerFeatures.fleet_add_post),
    ("DELETE", r"/fleet/pcs/([0-9a-f]{12})", HandlerFeatures.fleet_remove_delete),
    ("GET", "/update/check", HandlerFeatures.update_check),
    ("POST", "/update/install", HandlerFeatures.update_install),
    ("GET", "/notifications", HandlerFeatures.notification_get),
    ("PUT", "/notifications", HandlerFeatures.notification_put),
    ("POST", "/notifications/test", HandlerFeatures.notification_test),
    ("GET", "/restore-points", HandlerFeatures.restore_list),
    ("POST", "/restore-points/open", HandlerFeatures.restore_open),
    ("GET", "/apps", HandlerFeatures.app_list),
    ("GET", "/apps/updates", HandlerFeatures.app_updates),
    ("GET", "/apps/rules", HandlerFeatures.app_rules),
    ("POST", "/apps/rules/update", HandlerFeatures.update_app_rules),
    ("POST", "/apps/update", HandlerFeatures.app_update),
    ("POST", r"/apps/([0-9a-f]{16})/(uninstall|remove-entry|open-folder|size)", HandlerFeatures.app_operation),
    ("GET", r"/apps/([0-9a-f]{16})/uninstall-status", HandlerFeatures.uninstall_status),
    ("POST", r"/apps/([0-9a-f]{16})/leftovers", HandlerFeatures.clean_leftovers),
    ("POST", r"/apps/store/([0-9a-f]{16})/remove", HandlerFeatures.store_remove),
    ("POST", r"/apps/browsers/([a-z]{3,10})/clean", HandlerFeatures.browser_clean),
]
