"""Watching the network over time. Four read-only Toolbox reports that are meant to be scheduled (Schedules page):
- network.watch: scans the devices of the network and sends an alert (e-mail / Telegram) when one never seen before joins;
- network.bt_watch: listens for Bluetooth devices and alerts when an unknown tracker keeps showing up in scans at different times;
- network.wifi_watch: records signal, channel and crowding of the connected Wi-Fi, to see when and why it drops;
- network.upnp_report: lists the ports the router opened to the internet through UPnP and the device behind each one.
They change nothing on the PC or the network, so they run without a restore point and in preview mode too."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import wmm
from ottimizza_pc import Esito, Stato

from . import securestore
from . import netscan, notify, radio, upnp

DATA_DIR = Path(wmm.ROOT) / "dati"  # the same folder wmm.py gives the agent


def _data_dir(data_dir: Optional[Path]) -> Path:
    return Path(data_dir) if data_dir else DATA_DIR


def network_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    cartella = _data_dir(data_dir)
    dati = netscan.for_data_dir(cartella).run(progress=lambda testo: ctx.scrivi(f"  {testo}"))
    dispositivi = dati.get("devices", [])
    nuovi = [d for d in dispositivi if d.get("new")]
    ctx.scrivi(f"{len(dispositivi)} devices on {', '.join(r.get('network', '') for r in dati.get('networks') or []) or 'the network'}.")
    for d in nuovi:
        ctx.scrivi(f"  NEW  {d.get('ip')}  {d.get('mac') or ''}  {d.get('name') or d.get('kind') or d.get('vendor') or 'unknown device'}")
    if nuovi:
        testo = "Devices never seen before on the network:\n" + "\n".join(
            f"- {d.get('ip')} {d.get('mac') or ''} {d.get('name') or d.get('kind') or d.get('vendor') or ''}".rstrip() for d in nuovi[:20]) + \
            "\n\nOpen Network › Devices in the console to see them."
        notify.safe_event(cartella, "new_device", testo, gruppo=",".join(sorted(d.get("mac") or d.get("ip") or "" for d in nuovi))[:200])
        return Esito(Stato.AVVISO, f"{len(nuovi)} new devices on the network")
    return Esito(Stato.OK, "no new devices")


def bluetooth_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    cartella = _data_dir(data_dir)
    dati = radio.for_data_dir(cartella).run_bluetooth()
    if dati.get("error"):
        return Esito(Stato.AVVISO, dati["error"])
    seguaci = [d for d in dati.get("devices", []) if d.get("follower")]
    ctx.scrivi(f"{len(dati.get('devices', []))} Bluetooth devices nearby.")
    for d in seguaci:
        ctx.scrivi(f"  FOLLOWING?  {d['address']}  {d.get('name') or d.get('kind')}  seen in {d.get('sightings')} scans over "
                   f"{d.get('span_minutes')} minutes, {d.get('distance') or 'distance unknown'}")
    if seguaci:
        testo = ("Unknown Bluetooth devices keep showing up near this PC in scans taken at different times "
                 "(possible trackers such as AirTag, Tile or SmartTag):\n" +
                 "\n".join(f"- {d['address']} {d.get('name') or d.get('kind')}, {d.get('sightings')} scans in {d.get('span_minutes')} min"
                           for d in seguaci[:10]) +
                 "\n\nIf one is yours or a neighbour's, mark it as known in Network › Bluetooth.")
        notify.safe_event(cartella, "bt_follower", testo, gruppo=",".join(sorted(d["address"] for d in seguaci))[:200])
        return Esito(Stato.AVVISO, f"{len(seguaci)} unknown devices keep showing up")
    return Esito(Stato.OK, "no device seems to follow this PC")


def wifi_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    scanner = radio.for_data_dir(_data_dir(data_dir))
    dati = scanner.run_wifi()  # also records the sample in the Wi-Fi history
    if dati.get("error"):
        return Esito(Stato.AVVISO, dati["error"])
    campione = radio.wifi_sample(dati)
    if not campione:
        return Esito(Stato.AVVISO, "not connected to a Wi-Fi network: nothing recorded")
    ctx.scrivi(f"{campione['ssid']}: signal {campione['signal']}%, channel {campione['channel']} ({campione['band']}), "
               f"{campione['same_channel']} other networks on the same channel, {campione['networks']} networks around.")
    storia = scanner.wifi_history()
    if storia.get("worst_hour"):
        ctx.scrivi(f"Weakest hour so far: {storia['worst_hour']['hour']}:00 (average signal {storia['worst_hour']['signal']}%).")
    return Esito(Stato.OK, f"sample {len(storia['samples'])} recorded")


# ---------- 2.7: connection log ----------

KEEP_CONNECTION_SAMPLES = 5000
SLOW_MS = 150


def _connection_path(data_dir: Optional[Path]) -> Path:
    return _data_dir(data_dir) / "connection_history.json"


def connection_sample(pinger=None, resolver=None, gateway: Optional[str] = None) -> dict:
    """One reading: the router, a public server and name resolution, each with its time in ms (None when it fails)."""
    import socket
    import time
    from datetime import datetime
    if gateway is None:
        try:
            reti = netscan.local_networks()
            scelta = next((r for r in reti if r.get("default")), reti[0] if reti else {})
            gateway = scelta.get("gateway") or ""
        except (OSError, ValueError, IndexError):
            gateway = ""
    prova = pinger or (lambda ip: netscan.ping(ip, 1000))

    def risolvi():
        inizio = time.perf_counter()
        socket.getaddrinfo("www.microsoft.com", 443)
        return round((time.perf_counter() - inizio) * 1000)
    try:
        dns = (resolver or risolvi)()
    except OSError:
        dns = None
    internet = prova("1.1.1.1")
    if internet is None:
        internet = prova("8.8.8.8")
    return {"t": datetime.now().isoformat(timespec="seconds"), "gateway": gateway, "gateway_ms": prova(gateway) if gateway else None,
            "internet_ms": internet, "dns_ms": dns}


def classify(campione: dict) -> str:
    """Where the problem is in one reading."""
    if campione.get("gateway") and campione.get("gateway_ms") is None:
        return "local"      # the router does not answer: Wi-Fi, cable or router
    if campione.get("internet_ms") is None:
        return "provider"   # the router answers, the internet does not
    if campione.get("dns_ms") is None:
        return "dns"
    if campione["internet_ms"] >= SLOW_MS:
        return "slow"
    return "ok"


def connection_history(data_dir: Optional[Path] = None) -> dict:
    try:
        campioni = json.loads(securestore.read_text(_connection_path(data_dir))).get("samples", [])
    except (OSError, ValueError):
        campioni = []
    cadute, aperta = [], None
    for c in campioni:
        stato = classify(c)
        if stato in ("local", "provider", "dns"):
            if aperta and aperta["cause"] == stato:
                aperta["until"], aperta["samples"] = c["t"], aperta["samples"] + 1
            else:
                aperta = {"from": c["t"], "until": c["t"], "cause": stato, "samples": 1}
                cadute.append(aperta)
        else:
            aperta = None
    conta = {}
    for c in campioni:
        stato = classify(c)
        conta[stato] = conta.get(stato, 0) + 1
    tempi = [c["internet_ms"] for c in campioni if isinstance(c.get("internet_ms"), (int, float))]
    return {"samples": campioni[-2000:], "outages": cadute[-100:], "by_state": conta,
            "average_ms": round(sum(tempi) / len(tempi)) if tempi else None}


def record_connection(data_dir: Optional[Path] = None, campione: Optional[dict] = None) -> dict:
    campione = campione or connection_sample()
    percorso = _connection_path(data_dir)
    try:
        campioni = json.loads(securestore.read_text(percorso)).get("samples", [])
    except (OSError, ValueError):
        campioni = []
    percorso.parent.mkdir(parents=True, exist_ok=True)
    securestore.write_text(percorso, json.dumps({"samples": (campioni + [campione])[-KEEP_CONNECTION_SAMPLES:]}), encoding="utf-8")
    return campione


CAUSES = {"local": "the router does not answer (Wi-Fi, cable or router)", "provider": "the router answers but the internet does not (provider)",
          "dns": "name resolution fails (DNS)", "slow": "the internet answers slowly", "ok": "all good"}


def connection_watch(ctx, data_dir: Optional[Path] = None) -> Esito:
    campione = record_connection(data_dir)
    stato = classify(campione)
    ctx.scrivi(f"Router {campione['gateway'] or '?'}: {campione['gateway_ms']} ms · internet: {campione['internet_ms']} ms · DNS: {campione['dns_ms']} ms")
    storia = connection_history(data_dir)
    ctx.scrivi(f"{len(storia['samples'])} readings, {len(storia['outages'])} outages recorded.")
    # The alert for an outage goes out when the connection is back (during it, e-mail and Telegram cannot be reached).
    campioni = storia["samples"]
    if stato in ("ok", "slow") and len(campioni) >= 2 and storia["outages"] and storia["outages"][-1]["until"] == campioni[-2]["t"]:
        caduta = storia["outages"][-1]
        notify.safe_event(_data_dir(data_dir), "connection_down",
                          f"The connection dropped from {caduta['from']} to {caduta['until']} ({caduta['samples']} readings): {CAUSES[caduta['cause']]}.",
                          gruppo=caduta["from"])
    return Esito(Stato.OK if stato in ("ok", "slow") else Stato.AVVISO, CAUSES[stato])


def upnp_report(ctx, data_dir: Optional[Path] = None) -> Esito:
    ultimi = netscan.for_data_dir(_data_dir(data_dir)).last() or {}
    dati = upnp.read(ultimi.get("devices"))
    for riga in upnp.report_lines(dati):
        ctx.scrivi(riga)
    if dati.get("risky"):
        return Esito(Stato.AVVISO, dati["note"])
    return Esito(Stato.OK, dati.get("note", ""))
