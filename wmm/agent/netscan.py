"""Network scanner: every device on the local networks of this PC, with its name, MAC, maker, open ports, web page
and a guess of what it is. It only reads: a ping (Windows ICMP API), the ARP table, name lookups and a TCP connect
to a few well-known ports. Only private networks of adapters with a gateway are scanned, at most 1022 addresses."""
from __future__ import annotations

import concurrent.futures as cf
import ctypes
import ipaddress
import json
import re
import socket
import ssl
import struct
import subprocess
import time
import urllib.request
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import securestore
from .tools import powershell_command

MAX_HOSTS = 1022
PING_TIMEOUT_MS = 400
PORT_TIMEOUT = 0.35
PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 135: "Windows RPC", 139: "NetBIOS", 443: "HTTPS", 445: "Windows file sharing",
    515: "Printer (LPD)", 548: "Apple file sharing", 554: "Video stream (RTSP)", 631: "Printer (IPP)", 1883: "MQTT", 3389: "Remote Desktop",
    5000: "NAS / web", 5001: "NAS (HTTPS)", 5900: "VNC", 7000: "AirPlay", 8008: "Chromecast", 8009: "Chromecast",
    8080: "Web (alternate)", 8443: "HTTPS (alternate)", 9100: "Printer (raw)", 32400: "Plex", 62078: "iPhone / iPad sync",
}
# MAC prefixes of makers whose devices are common at home and in small offices (IEEE OUI).
VENDORS = {
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi", "E4:5F:01": "Raspberry Pi", "D8:3A:DD": "Raspberry Pi", "28:CD:C1": "Raspberry Pi",
    "00:17:88": "Philips Hue (Signify)", "00:11:32": "Synology", "00:08:9B": "QNAP", "24:5E:BE": "QNAP",
    "00:50:56": "VMware", "00:0C:29": "VMware", "00:05:69": "VMware", "00:15:5D": "Microsoft Hyper-V", "08:00:27": "VirtualBox", "52:54:00": "QEMU / KVM",
    "00:1B:63": "Apple", "3C:07:54": "Apple", "F0:18:98": "Apple", "A4:83:E7": "Apple",
    "00:1A:11": "Google", "F4:F5:D8": "Google", "54:60:09": "Google",
    "FC:A6:67": "Amazon", "44:65:0D": "Amazon", "74:C2:46": "Amazon",
    "00:0E:58": "Sonos", "48:A6:B8": "Sonos", "B8:E9:37": "Sonos",
    "00:1B:A9": "Brother", "30:05:5C": "Brother", "00:00:48": "Epson", "64:EB:8C": "Epson", "00:1E:8F": "Canon", "00:00:85": "Canon",
    "3C:D9:2B": "HP", "00:1F:29": "HP", "A0:D3:C1": "HP",
    "50:C7:BF": "TP-Link", "F4:F2:6D": "TP-Link", "C0:06:C3": "TP-Link", "98:DA:C4": "TP-Link",
    "24:A4:3C": "Ubiquiti", "F0:9F:C2": "Ubiquiti", "78:8A:20": "Ubiquiti", "80:2A:A8": "Ubiquiti",
    "24:0A:C4": "Espressif (smart device)", "30:AE:A4": "Espressif (smart device)", "A4:CF:12": "Espressif (smart device)", "84:F3:EB": "Espressif (smart device)",
    "00:1D:BA": "Sony", "00:24:BE": "Sony",
}


# ---------- networks ----------

# Every connected adapter with an IPv4 address; the one with a gateway and the lowest metric is the one Windows uses.
SCRIPT_NETWORKS = r"""
@(Get-NetIPConfiguration | Where-Object { $_.IPv4Address -and $_.NetAdapter.Status -eq 'Up' } | ForEach-Object {
  [ordered]@{ alias = "$($_.InterfaceAlias)"; description = "$($_.InterfaceDescription)"; ip = "$($_.IPv4Address[0].IPAddress)";
              prefix = [int]$_.IPv4Address[0].PrefixLength; gateway = "$(@($_.IPv4DefaultGateway)[0].NextHop)";
              metric = [int]$_.NetIPv4Interface.InterfaceMetric } }) | ConvertTo-Json -Compress
"""


def parse_networks(testo: str) -> List[dict]:
    """The networks to scan: private only; a network larger than /22 is reduced to the /24 of this PC."""
    try:
        dati = json.loads(testo or "[]")
    except ValueError:
        return []
    voci = dati if isinstance(dati, list) else [dati]
    reti = []
    for v in voci:
        try:
            ip = ipaddress.ip_address(v["ip"])
            rete = ipaddress.ip_network(f"{v['ip']}/{int(v['prefix'])}", strict=False)
        except (KeyError, ValueError, TypeError):
            continue
        if not ip.is_private or ip.is_link_local or ip.is_loopback:
            continue
        if rete.num_addresses - 2 > MAX_HOSTS:
            rete = ipaddress.ip_network(f"{v['ip']}/24", strict=False)
        try:
            metrica = int(v.get("metric") or 9999)
        except (TypeError, ValueError):
            metrica = 9999
        reti.append({"alias": str(v.get("alias") or ""), "description": str(v.get("description") or ""), "ip": str(ip),
                     "gateway": str(v.get("gateway") or ""), "network": str(rete), "metric": metrica})
    # The active one first: a gateway, then the lowest metric (the route Windows prefers).
    reti.sort(key=lambda r: (not r["gateway"], r["metric"]))
    for i, r in enumerate(reti):
        r["default"] = i == 0
    return reti


def local_networks() -> List[dict]:
    uscita = subprocess.run(powershell_command(SCRIPT_NETWORKS), capture_output=True, text=True, timeout=60).stdout
    return parse_networks(uscita)


# ---------- discovery ----------

class _Options(ctypes.Structure):
    _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte), ("OptionsSize", ctypes.c_ubyte),
                ("OptionsData", ctypes.c_void_p)]


class _Reply(ctypes.Structure):
    _fields_ = [("Address", wintypes.ULONG), ("Status", wintypes.ULONG), ("RoundTripTime", wintypes.ULONG), ("DataSize", wintypes.USHORT),
                ("Reserved", wintypes.USHORT), ("Data", ctypes.c_void_p), ("Options", _Options)]


def ping(ip: str, timeout_ms: int = PING_TIMEOUT_MS) -> Optional[int]:
    """Round trip in ms, or None. Uses the Windows ICMP API: no console window, no administrator rights."""
    iphlpapi = ctypes.windll.iphlpapi
    iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
    handle = iphlpapi.IcmpCreateFile()
    if not handle or handle == wintypes.HANDLE(-1).value:
        return None
    try:
        dati = b"wmm-scan"
        buffer = ctypes.create_string_buffer(ctypes.sizeof(_Reply) + len(dati) + 8)
        destinazione = struct.unpack("<I", socket.inet_aton(ip))[0]
        risposte = iphlpapi.IcmpSendEcho(wintypes.HANDLE(handle), wintypes.ULONG(destinazione), dati, len(dati), None, buffer, len(buffer), timeout_ms)
        if not risposte:
            return None
        risposta = _Reply.from_buffer(buffer)
        return int(risposta.RoundTripTime) if risposta.Status == 0 else None
    finally:
        iphlpapi.IcmpCloseHandle(wintypes.HANDLE(handle))


def parse_arp(testo: str) -> Dict[str, str]:
    """IP -> MAC from `arp -a` (any Windows language): unicast entries only."""
    tabella = {}
    for ip, mac in re.findall(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})\b", testo or "", re.M):
        mac = mac.upper().replace("-", ":")
        if mac != "FF:FF:FF:FF:FF:FF" and not mac.startswith("01:00:5E"):
            tabella[ip] = mac
    return tabella


def arp_table() -> Dict[str, str]:
    try:
        return parse_arp(subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=20).stdout)
    except (OSError, subprocess.SubprocessError):
        return {}


def vendor(mac: str) -> str:
    if not mac:
        return ""
    if int(mac[:2], 16) & 0x02:
        return "Random MAC (phone or privacy mode)"
    return VENDORS.get(mac[:8], "")


def _port_open(ip: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(PORT_TIMEOUT)
        return s.connect_ex((ip, porta)) == 0


def open_ports(ip: str, porte: Iterable[int] = PORTS) -> List[int]:
    elenco = list(porte)
    with cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="wmm-port") as pool:
        return [p for p, aperta in zip(elenco, pool.map(lambda p: _port_open(ip, p), elenco)) if aperta]


def name_of(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return ""


def web_title(ip: str, porta: int) -> str:
    """The title of the device's web page (router, printer, NAS); certificates are not checked, only the title is read."""
    schema = "https" if porta in (443, 5001, 8443) else "http"
    contesto = ssl._create_unverified_context() if schema == "https" else None  # noqa: S323 - read-only title of a LAN device
    try:
        with urllib.request.urlopen(f"{schema}://{ip}:{porta}/", timeout=1.5, context=contesto) as risposta:
            testo = risposta.read(32768).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - no title is a normal answer
        return ""
    trovato = re.search(r"<title[^>]*>(.*?)</title>", testo, re.S | re.I)
    return re.sub(r"\s+", " ", trovato.group(1)).strip()[:80] if trovato else ""


def guess(device: dict) -> str:
    porte = set(device.get("ports") or [])
    testo = f"{device.get('name', '')} {device.get('vendor', '')} {device.get('title', '')}".lower()
    if device.get("gateway"):
        return "Router / gateway"
    if device.get("this_pc"):
        return "This PC"
    if porte & {9100, 631, 515} or re.search(r"printer|laserjet|officejet|brother|epson|canon|kyocera", testo):
        return "Printer"
    if porte & {5000, 5001} or re.search(r"synology|qnap|diskstation|\bnas\b", testo):
        return "NAS"
    if 554 in porte or re.search(r"camera|ipcam|hikvision|dahua|reolink", testo):
        return "Camera"
    if porte & {8008, 8009} or re.search(r"chromecast|android-tv|bravia|smart ?tv|webos|tizen", testo):
        return "TV / media"
    if 62078 in porte or re.search(r"iphone|ipad", testo):
        return "iPhone / iPad"
    if re.search(r"\bhue\b|philips hue|espressif|shelly|tasmota|sonoff|tuya|smart device|roborock|vacuum|roomba|dyson|nest|\bring\b|meross|wiz", testo):
        return "Smart home device"
    if re.search(r"amazon|echo|alexa|fire-?tv|kindle", testo):
        return "Amazon device (Echo, Fire TV, Kindle)"
    if re.search(r"samsung|lgwebos|\blg\b|philips-tv|hisense|sony", testo):
        return "TV, phone or appliance"
    if porte & {445, 135, 3389}:
        return "Windows PC"
    if 548 in porte or "apple" in testo or "macbook" in testo:
        return "Mac / Apple device"
    if 22 in porte and re.search(r"raspberry|linux|ubuntu|debian", testo):
        return "Linux / Raspberry Pi"
    if "random mac" in testo or re.search(r"android|galaxy|phone|xiaomi|redmi", testo):
        return "Phone or tablet"
    if porte & {80, 443, 8080}:
        return "Device with a web page"
    return "Unknown"


def risks(device: dict) -> List[str]:
    """Open services worth a look on a home or office network."""
    porte = set(device.get("ports") or [])
    note = []
    if 23 in porte:
        note.append("Telnet is open: an old, unencrypted remote access. Turn it off on the device.")
    if 21 in porte:
        note.append("FTP is open: files and passwords travel unencrypted.")
    if 5900 in porte:
        note.append("VNC is open: make sure it has a strong password.")
    if 3389 in porte and not device.get("this_pc"):
        note.append("Remote Desktop is reachable from the network.")
    return note


# ---------- the scan ----------

def choose(reti: List[dict], alias: Optional[str]) -> List[dict]:
    """The network of the chosen adapter, or the active one when none is chosen."""
    if alias:
        scelte = [r for r in reti if r["alias"] == alias]
        if not scelte:
            raise ValueError(f"The adapter {alias} has no local network to scan (disconnected or without an IPv4 address).")
        return scelte
    return [r for r in reti if r.get("default")][:1] or reti[:1]


def scan(this_ip: Optional[str] = None, networks: Optional[List[dict]] = None, progress=None, alias: Optional[str] = None) -> dict:
    inizio = time.time()
    reti = choose(networks if networks is not None else local_networks(), alias)
    indirizzi: List[str] = []
    for r in reti:
        indirizzi += [str(h) for h in ipaddress.ip_network(r["network"]).hosts()]
    indirizzi = list(dict.fromkeys(indirizzi))[:MAX_HOSTS * 2]
    miei = {r["ip"] for r in reti} | ({this_ip} if this_ip else set())
    gateway = {r["gateway"] for r in reti}
    if progress:
        progress(f"Pinging {len(indirizzi)} addresses")
    with cf.ThreadPoolExecutor(max_workers=64, thread_name_prefix="wmm-ping") as pool:
        tempi = dict(zip(indirizzi, pool.map(ping, indirizzi)))
    arp = arp_table()  # after the pings: devices that ignore ping still answered ARP
    vivi = sorted({ip for ip, t in tempi.items() if t is not None} | {ip for ip in arp if ip in tempi} | (miei & set(tempi)),
                  key=lambda x: tuple(int(p) for p in x.split(".")))
    if progress:
        progress(f"Reading {len(vivi)} devices")

    def dettagli(ip: str) -> dict:
        mac = arp.get(ip, "")
        voce = {"ip": ip, "mac": mac, "vendor": vendor(mac), "latency_ms": tempi.get(ip), "this_pc": ip in miei, "gateway": ip in gateway,
                "name": name_of(ip), "ports": open_ports(ip)}
        voce["services"] = [PORTS[p] for p in voce["ports"]]
        web = next((p for p in (80, 443, 8080, 5000, 5001, 8443) if p in voce["ports"]), None)
        voce["web"] = f"{'https' if web in (443, 5001, 8443) else 'http'}://{ip}{'' if web in (80, 443) else f':{web}'}/" if web else ""
        voce["title"] = web_title(ip, web) if web else ""
        voce["type"] = guess(voce)
        voce["notes"] = risks(voce)
        return voce
    with cf.ThreadPoolExecutor(max_workers=32, thread_name_prefix="wmm-probe") as pool:
        dispositivi = list(pool.map(dettagli, vivi))
    return {"networks": reti, "devices": dispositivi, "scanned": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(time.time() - inizio, 1), "addresses": len(indirizzi)}


def merge_history(risultato: dict, precedente: Optional[dict]) -> dict:
    """First and last time each device was seen (by MAC, else IP), and which ones are new since the previous scan.
    Only the devices of the networks just scanned are compared: scanning another adapter does not make the others missing."""
    reti = []
    for r in risultato.get("networks") or []:
        try:
            reti.append(ipaddress.ip_network(r["network"], strict=False))
        except (KeyError, TypeError, ValueError):
            pass

    def qui(v: dict) -> bool:
        if not reti:
            return True
        try:
            return any(ipaddress.ip_address(v.get("ip") or "") in rete for rete in reti)
        except ValueError:
            return False

    noti = (precedente or {}).get("known", [])
    altrove = [v for v in noti if not qui(v)]  # other networks: kept as they are
    visti = {v["key"]: v for v in noti if qui(v)}
    primo_scan = not visti
    for d in risultato["devices"]:
        chiave = d["mac"] or d["ip"]
        noto = visti.get(chiave)
        d["first_seen"] = noto["first_seen"] if noto else risultato["scanned"]
        d["new"] = not noto and not primo_scan
        visti[chiave] = {"key": chiave, "first_seen": d["first_seen"], "last_seen": risultato["scanned"], "ip": d["ip"], "name": d["name"]}
    presenti = {d["mac"] or d["ip"] for d in risultato["devices"]}
    risultato["missing"] = [v for k, v in visti.items() if k not in presenti][:100]
    risultato["known"] = sorted(list(visti.values()) + [v for v in altrove if v["key"] not in visti], key=lambda v: v["last_seen"], reverse=True)[:500]
    return risultato


class NetworkScanner:
    def __init__(self, path: Path):
        self.path = Path(path)

    def last(self) -> Optional[dict]:
        try:
            return json.loads(securestore.read_text(self.path))
        except (OSError, ValueError):
            return None

    def run(self, this_ip: Optional[str] = None, progress=None, alias: Optional[str] = None) -> dict:
        risultato = merge_history(scan(this_ip, progress=progress, alias=alias), self.last())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        securestore.write_text(self.path, json.dumps(risultato), encoding="utf-8")
        return risultato


def for_data_dir(data_dir: Path) -> NetworkScanner:
    return NetworkScanner(Path(data_dir) / "network_scan.json")
