"""Router exposure: the ports the router opens to the internet through UPnP IGD, and which device asked for them.
A camera, a NAS or a game console often opens ports by itself, and that is how most of them end up reachable from
anywhere. Read-only: SSDP discovery on the local network, the router's description XML, and the GetGenericPortMappingEntry
query of its WANIPConnection / WANPPPConnection service. Nothing is added or removed."""
from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

SSDP = ("239.255.255.250", 1900)
SEARCH_TARGETS = ("urn:schemas-upnp-org:device:InternetGatewayDevice:1", "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
                  "urn:schemas-upnp-org:service:WANIPConnection:1")
SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANPPPConnection:1")
MAX_MAPPINGS = 256
HTTP_TIMEOUT = 4
MAX_BODY = 512 * 1024

# Ports that should almost never be open to the internet, and why.
RISKY_PORTS: Dict[int, str] = {
    21: "FTP sends passwords in clear text", 22: "SSH is a constant target of password guessing", 23: "Telnet has no encryption at all",
    80: "a web admin page (cameras, NAS, printers) reachable from the internet", 443: "a web admin page reachable from the internet",
    445: "Windows file sharing (SMB): the way ransomware spreads", 139: "old Windows file sharing (NetBIOS)", 554: "a camera video stream (RTSP)",
    1883: "MQTT for smart-home devices, often without a password", 3389: "Remote Desktop, the most attacked service on the internet",
    5000: "a NAS admin page (Synology DSM)", 5001: "a NAS admin page (Synology DSM)", 5900: "VNC remote control", 8000: "a camera or DVR web page",
    8080: "a web admin page of a device", 8443: "a web admin page of a device", 8888: "a device admin page", 9000: "a device admin page",
    37777: "a Dahua camera or DVR", 34567: "a cheap DVR or camera (often with known flaws)",
}


def _private(host: str) -> bool:
    try:
        indirizzo = ipaddress.ip_address(host)
    except ValueError:
        return False
    return indirizzo.is_private and not indirizzo.is_loopback


def discover(timeout: float = 3.0, sender: Optional[Callable] = None) -> List[str]:
    """LOCATION URLs of the Internet gateways that answer the SSDP search, on the local network only."""
    if sender is not None:
        risposte = sender()
    else:
        risposte = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(0.5)
            for st in SEARCH_TARGETS:
                messaggio = (f"M-SEARCH * HTTP/1.1\r\nHOST: {SSDP[0]}:{SSDP[1]}\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\nST: {st}\r\n\r\n").encode()
                sock.sendto(messaggio, SSDP)
            fine = time.monotonic() + timeout
            while time.monotonic() < fine:
                try:
                    dati, _ = sock.recvfrom(8192)
                except socket.timeout:
                    continue
                risposte.append(dati.decode("utf-8", "replace"))
        finally:
            sock.close()
    luoghi = []
    for testo in risposte:
        trovato = re.search(r"^location:\s*(\S+)", testo, re.I | re.M)
        if trovato:
            url = trovato.group(1).strip()
            if urlsplit(url).scheme == "http" and _private(urlsplit(url).hostname or "") and url not in luoghi:
                luoghi.append(url)
    return luoghi


def _fetch(url: str, data: Optional[bytes] = None, headers: Optional[dict] = None) -> Tuple[int, str]:
    if urlsplit(url).scheme != "http" or not _private(urlsplit(url).hostname or ""):
        raise ValueError("The router must be on the local network.")
    richiesta = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(richiesta, timeout=HTTP_TIMEOUT) as risposta:  # noqa: S310 (local http only, checked above)
            return risposta.status, risposta.read(MAX_BODY).decode("utf-8", "replace")
    except urllib.error.HTTPError as errore:  # a SOAP fault comes back as HTTP 500
        return errore.code, errore.read(MAX_BODY).decode("utf-8", "replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse(xml: str):
    """A router answer as XML. Documents with a DOCTYPE (entities) are refused: UPnP never needs one."""
    if re.search(r"<!DOCTYPE|<!ENTITY", xml or "", re.I):
        raise ET.ParseError("DOCTYPE not allowed")
    return ET.fromstring(xml)


def parse_description(xml: str, location: str) -> Optional[dict]:
    """The router name and the control URL of its WAN connection service."""
    try:
        radice = _parse(xml)
    except ET.ParseError:
        return None

    def primo(nome: str, predefinito: str = "") -> str:
        return next((e.text.strip() for e in radice.iter() if _local(e.tag) == nome and e.text and e.text.strip()), predefinito)

    base = primo("URLBase", location)
    servizi = []
    for servizio in radice.iter():
        if _local(servizio.tag) != "service":
            continue
        campi = {_local(c.tag): (c.text or "").strip() for c in servizio}
        if campi.get("serviceType") in SERVICES and campi.get("controlURL"):
            servizi.append((SERVICES.index(campi["serviceType"]), campi["serviceType"], urljoin(base, campi["controlURL"])))
    if not servizi:
        return None
    _, tipo, controllo = sorted(servizi)[0]
    return {"name": primo("friendlyName"), "model": primo("modelName"), "manufacturer": primo("manufacturer"), "service": tipo,
            "control": controllo, "location": location}


def _soap(router: dict, azione: str, argomenti: Dict[str, object], fetch=_fetch) -> Tuple[int, Dict[str, str]]:
    corpo = "".join(f"<{k}>{v}</{k}>" for k, v in argomenti.items())
    busta = (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
             f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{azione} xmlns:u="{router["service"]}">{corpo}'
             f"</u:{azione}></s:Body></s:Envelope>")
    stato, testo = fetch(router["control"], busta.encode(), {"Content-Type": 'text/xml; charset="utf-8"',
                                                            "SOAPAction": f'"{router["service"]}#{azione}"'})
    try:
        radice = _parse(testo)
    except ET.ParseError:
        return stato, {}
    return stato, {_local(e.tag): (e.text or "").strip() for e in radice.iter() if not list(e)}


def risk(mapping: dict) -> str:
    try:
        interna = int(mapping.get("internal_port") or 0)
        esterna = int(mapping.get("external_port") or 0)
    except (TypeError, ValueError):
        return ""
    return RISKY_PORTS.get(interna) or RISKY_PORTS.get(esterna) or ""


def port_mappings(router: dict, fetch=_fetch) -> List[dict]:
    voci = []
    for indice in range(MAX_MAPPINGS):
        stato, campi = _soap(router, "GetGenericPortMappingEntry", {"NewPortMappingIndex": indice}, fetch)
        if stato != 200 or "NewExternalPort" not in campi:
            break  # 713 SpecifiedArrayIndexInvalid: the end of the list
        voce = {"protocol": campi.get("NewProtocol", ""), "external_port": campi.get("NewExternalPort", ""),
                "internal_client": campi.get("NewInternalClient", ""), "internal_port": campi.get("NewInternalPort", ""),
                "description": campi.get("NewPortMappingDescription", "")[:120], "enabled": campi.get("NewEnabled", "1") in ("1", "true"),
                "remote_host": campi.get("NewRemoteHost", ""), "lease_seconds": campi.get("NewLeaseDuration", "")}
        voce["risk"] = risk(voce)
        voci.append(voce)
    return voci


def read(devices: Optional[List[dict]] = None, sender=None, fetch=_fetch) -> dict:
    """The router, its public address and every port it opened through UPnP, with the device behind each one."""
    istante = datetime.now().isoformat(timespec="seconds")
    luoghi = discover(sender=sender)
    if not luoghi:
        return {"scanned": istante, "router": None, "mappings": [], "risky": 0,
                "note": "No router answered the UPnP search: UPnP is off on the router (good), or this network blocks the search."}
    router, altri = None, []
    for luogo in luoghi:
        try:
            stato, xml = fetch(luogo)
        except (OSError, ValueError):
            continue
        if stato == 200:
            router = parse_description(xml, luogo)
            if router:
                break
            nome = re.search(r"<friendlyName>([^<]{1,80})</friendlyName>", xml)
            altri.append(nome.group(1).strip() if nome else urlsplit(luogo).hostname)
    if router is None:
        # Smart bulbs, TVs and NAS answer every UPnP search: only a router has the port mapping service.
        return {"scanned": istante, "router": None, "mappings": [], "risky": 0, "answered": altri,
                "note": "No router answered with a port mapping service: UPnP looks off on the router (good). "
                        "Only other devices answered: " + ", ".join(altri) + "."}
    try:
        _, campi = _soap(router, "GetExternalIPAddress", {}, fetch)
        router["external_ip"] = campi.get("NewExternalIPAddress", "")
        voci = port_mappings(router, fetch)
    except (OSError, ValueError) as errore:
        return {"scanned": istante, "router": router, "mappings": [], "risky": 0, "note": f"The router did not answer the port query: {errore}"}
    per_ip = {d.get("ip"): d for d in devices or []}
    for voce in voci:
        dispositivo = per_ip.get(voce["internal_client"]) or {}
        voce["device"] = dispositivo.get("name") or dispositivo.get("kind") or dispositivo.get("vendor") or ""
        voce["device_kind"] = dispositivo.get("kind", "")
    rischiose = [v for v in voci if v["risk"] and v["enabled"]]
    nota = (f"{len(voci)} ports opened through UPnP, {len(rischiose)} worth closing." if voci
            else "UPnP is on, but no device opened a port right now.")
    return {"scanned": istante, "router": router, "mappings": voci, "risky": len(rischiose), "note": nota}


def report_lines(dati: dict) -> List[str]:
    righe = []
    router = dati.get("router")
    if router:
        righe.append(f"Router: {router.get('name') or router.get('model') or 'unknown'} ({router.get('manufacturer', '')}), "
                     f"public address {router.get('external_ip') or 'unknown'}")
    for v in dati.get("mappings", []):
        dove = v["internal_client"] + (f" ({v['device']})" if v.get("device") else "")
        riga = f"  {v['protocol']} {v['external_port']} -> {dove}:{v['internal_port']}  {v['description']}"
        if v.get("risk"):
            riga += f"  ! {v['risk']}"
        righe.append(riga)
    righe.append(dati.get("note", ""))
    return righe
