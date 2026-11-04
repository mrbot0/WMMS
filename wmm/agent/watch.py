"""Watching the network over time. Four read-only Toolbox reports that are meant to be scheduled (Schedules page):
- network.watch: scans the devices of the network and sends an alert (e-mail / Telegram) when one never seen before joins;
- network.bt_watch: listens for Bluetooth devices and alerts when an unknown tracker keeps showing up in scans at different times;
- network.wifi_watch: records signal, channel and crowding of the connected Wi-Fi, to see when and why it drops;
- network.upnp_report: lists the ports the router opened to the internet through UPnP and the device behind each one.
They change nothing on the PC or the network, so they run without a restore point and in preview mode too."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import wmm
from ottimizza_pc import Esito, Stato

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


def upnp_report(ctx, data_dir: Optional[Path] = None) -> Esito:
    ultimi = netscan.for_data_dir(_data_dir(data_dir)).last() or {}
    dati = upnp.read(ultimi.get("devices"))
    for riga in upnp.report_lines(dati):
        ctx.scrivi(riga)
    if dati.get("risky"):
        return Esito(Stato.AVVISO, dati["note"])
    return Esito(Stato.OK, dati.get("note", ""))
