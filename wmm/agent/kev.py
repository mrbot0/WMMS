"""Device firmware against known exploited vulnerabilities. The network scanner already knows the maker and often the
model of routers, NAS, cameras and printers (MAC vendor, device name, web page title, UPnP description). This compares
them with CISA's Known Exploited Vulnerabilities catalog (public JSON, downloaded at most once a day) and lists the
devices whose maker and product appear there: for those a firmware update is urgent. A match is a hint to check the
firmware, not proof that the device is vulnerable (the catalog has no firmware versions to compare)."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ottimizza_pc import Esito, Stato

FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
MAX_AGE = 24 * 3600
MAX_BYTES = 30 * 1024 * 1024
# Words too generic to identify a product on their own.
GENERIC = frozenset("""router routers firmware devices device multiple products product web server management interface network camera cameras
ip nas storage system systems os software firmwares series and the for of""".split())
# The names a maker has in the catalog when it differs from the name of its MAC block or web page.
ALIASES = {"tp-link": "tplink", "tplink": "tplink", "d-link": "dlink", "dlink": "dlink", "hikvision": "hikvision", "dahua": "dahua",
           "netgear": "netgear", "zyxel": "zyxel", "synology": "synology", "qnap": "qnap", "asus": "asus", "asustek": "asus", "ubiquiti": "ubiquiti",
           "mikrotik": "mikrotik", "fortinet": "fortinet", "sonicwall": "sonicwall", "draytek": "draytek", "tenda": "tenda", "linksys": "linksys",
           "zte": "zte", "huawei": "huawei", "avm": "avm", "fritz": "avm", "western digital": "westerndigital", "wd": "westerndigital",
           "buffalo": "buffalo", "axis": "axis", "reolink": "reolink", "hp": "hp", "hewlett": "hp", "canon": "canon", "xerox": "xerox",
           "cisco": "cisco", "juniper": "juniper", "realtek": "realtek", "sophos": "sophos", "arris": "arris", "sagemcom": "sagemcom"}


def _norm(testo: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (testo or "").lower())


def vendor_key(testo: str) -> str:
    basso = (testo or "").lower()
    for nome, chiave in ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(nome) + r"(?![a-z0-9])", basso):
            return chiave
    return _norm(basso.split(",")[0].split(" ")[0]) if basso else ""


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "kev.json"


def catalog(data_dir: Path, fetch: Optional[Callable[[], bytes]] = None, force: bool = False) -> dict:
    """The KEV catalog, from the local copy when it is less than a day old."""
    percorso = _path(data_dir)
    if not force and percorso.is_file() and time.time() - percorso.stat().st_mtime < MAX_AGE:
        try:
            return json.loads(percorso.read_text(encoding="utf-8"))
        except ValueError:
            pass

    def scarica() -> bytes:
        richiesta = urllib.request.Request(FEED, headers={"User-Agent": "WindowsMaintenanceManager"})
        with urllib.request.urlopen(richiesta, timeout=30) as risposta:  # noqa: S310 (fixed https URL)
            return risposta.read(MAX_BYTES)
    try:
        dati = json.loads((fetch or scarica)().decode("utf-8"))
    except (OSError, ValueError) as errore:
        if percorso.is_file():  # offline: the old copy is better than nothing
            return json.loads(percorso.read_text(encoding="utf-8"))
        raise OSError(f"The vulnerability catalog could not be downloaded: {errore}") from None
    voci = [{k: str(v.get(k, ""))[:400] for k in ("cveID", "vendorProject", "product", "vulnerabilityName", "dateAdded", "shortDescription",
                                                   "requiredAction", "knownRansomwareCampaignUse")}
            for v in dati.get("vulnerabilities", []) if isinstance(v, dict)]
    ridotto = {"catalogVersion": str(dati.get("catalogVersion", "")), "dateReleased": str(dati.get("dateReleased", "")), "vulnerabilities": voci}
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(ridotto), encoding="utf-8")
    return ridotto


def _device_text(d: dict) -> str:
    return " ".join(str(d.get(k) or "") for k in ("vendor", "name", "title", "type", "kind", "model", "manufacturer"))


def product_words(prodotto: str) -> List[str]:
    return [p for p in re.findall(r"[a-z0-9][a-z0-9.\-]+", (prodotto or "").lower()) if p not in GENERIC and len(p) >= 3]


def match(devices: List[dict], vulnerabilita: List[dict]) -> List[dict]:
    """Devices whose maker is in the catalog and whose name, page title or model contains the product."""
    per_vendor: Dict[str, List[dict]] = {}
    for v in vulnerabilita:
        per_vendor.setdefault(vendor_key(v["vendorProject"]), []).append(v)
    risultati = []
    for d in devices:
        chiave = vendor_key(d.get("vendor") or d.get("manufacturer") or "") or vendor_key(_device_text(d))
        candidati = per_vendor.get(chiave) if chiave else None
        if not candidati:
            continue
        testo = _device_text(d).lower()
        compatto = _norm(testo)
        trovate = []
        for v in candidati:
            parole = product_words(v["product"])
            if parole and all(p in testo or _norm(p) in compatto for p in parole):
                trovate.append(v)
        if trovate:
            trovate.sort(key=lambda v: v.get("dateAdded", ""), reverse=True)
            risultati.append({"ip": d.get("ip", ""), "device": d.get("name") or d.get("title") or d.get("vendor") or "", "vendor": d.get("vendor", ""),
                              "matches": trovate[:10], "count": len(trovate),
                              "ransomware": any(v.get("knownRansomwareCampaignUse") == "Known" for v in trovate)})
    return risultati


def check(data_dir: Path, devices: Optional[List[dict]] = None, fetch=None, force: bool = False) -> dict:
    from . import netscan
    cartella = Path(data_dir)
    if devices is None:
        devices = list((netscan.for_data_dir(cartella).last() or {}).get("devices", []))
        try:  # the router described by UPnP (model and maker) counts as one more device
            router = (json.loads((cartella / "upnp.json").read_text(encoding="utf-8")) or {}).get("router")
            if router:
                devices.append({"ip": "router", "name": router.get("model") or router.get("name"), "vendor": router.get("manufacturer"),
                                "model": router.get("model")})
        except (OSError, ValueError):
            pass
    dati = catalog(cartella, fetch, force)
    trovati = match(devices, dati.get("vulnerabilities", []))
    return {"checked": datetime.now().isoformat(timespec="seconds"), "catalog_version": dati.get("catalogVersion"),
            "catalog_entries": len(dati.get("vulnerabilities", [])), "devices_checked": len(devices), "found": trovati}


def kev_report(ctx, data_dir: Optional[Path] = None) -> Esito:
    from .watch import DATA_DIR
    esito = check(Path(data_dir) if data_dir else DATA_DIR)
    ctx.scrivi(f"{esito['devices_checked']} devices compared with {esito['catalog_entries']} known exploited vulnerabilities "
               f"(CISA catalog {esito['catalog_version']}).")
    for d in esito["found"]:
        ctx.scrivi(f"  {d['ip']}  {d['device']} ({d['vendor']}): {d['count']} known exploited vulnerabilities"
                   + (", used by ransomware" if d["ransomware"] else ""))
        for v in d["matches"][:5]:
            ctx.scrivi(f"      {v['cveID']}  {v['vulnerabilityName'][:90]}")
    if esito["found"]:
        return Esito(Stato.AVVISO, f"{len(esito['found'])} devices to check: update their firmware")
    return Esito(Stato.OK, "no device of the network matches the catalog")
