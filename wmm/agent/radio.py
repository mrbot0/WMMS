"""Wi-Fi and Bluetooth scanners for the Network scanner page. They only listen: the Wi-Fi networks around (with security,
signal, channel and crowding) through the Windows Wi-Fi API and netsh, and the Bluetooth devices nearby or paired through
the Windows device enumeration. Nothing is joined, paired or changed."""
from __future__ import annotations

import ctypes
import json
import re
import subprocess
import time
from collections import Counter
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .netscan import VENDORS
from .tools import powershell_command

# ---------- Wi-Fi ----------


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _InterfaceInfo(ctypes.Structure):
    _fields_ = [("InterfaceGuid", _Guid), ("strInterfaceDescription", ctypes.c_wchar * 256), ("isState", ctypes.c_uint)]


class _InterfaceList(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wintypes.DWORD), ("dwIndex", wintypes.DWORD), ("InterfaceInfo", _InterfaceInfo * 1)]


def trigger_wifi_scan(attesa: float = 4.0, descrizione: Optional[str] = None) -> int:
    """Asks the Wi-Fi adapters (or only the one with this description) for a fresh scan: netsh alone shows the last one
    Windows made. Returns the adapters asked."""
    try:
        wlan = ctypes.windll.wlanapi
    except OSError:
        return 0
    handle, versione = wintypes.HANDLE(), wintypes.DWORD()
    if wlan.WlanOpenHandle(2, None, ctypes.byref(versione), ctypes.byref(handle)) != 0:
        return 0
    lista = ctypes.POINTER(_InterfaceList)()
    try:
        if wlan.WlanEnumInterfaces(handle, None, ctypes.byref(lista)) != 0 or not lista:
            return 0
        quante = lista.contents.dwNumberOfItems
        voci = ctypes.cast(ctypes.addressof(lista.contents.InterfaceInfo), ctypes.POINTER(_InterfaceInfo * quante)).contents if quante else []
        scelte = [v for v in voci if not descrizione or v.strInterfaceDescription == descrizione]
        for voce in scelte:
            wlan.WlanScan(handle, ctypes.byref(voce.InterfaceGuid), None, None, None)
        if scelte:
            time.sleep(attesa)  # the adapter answers in about 4 seconds
        return len(scelte)
    finally:
        if lista:
            wlan.WlanFreeMemory(lista)
        wlan.WlanCloseHandle(handle, None)


# netsh writes its labels in the language of Windows: the ones we need, in English and Italian.
KEYS = {
    "auth": r"Authentication|Autenticazione", "cipher": r"Encryption|Crittografia|Cipher", "signal": r"Signal|Segnale",
    "radio": r"Radio type|Tipo (?:di )?radio", "band": r"Band|Banda", "channel": r"Channel|Canale",
    "stations": r"Connected Stations|Stazioni connesse", "utilization": r"Channel Utilization|Utilizzo canale",
}


def _key(etichetta: str) -> Optional[str]:
    for nome, schema in KEYS.items():
        if re.fullmatch(schema, etichetta.strip(), re.I):
            return nome
    return None


def parse_wifi(testo: str) -> List[dict]:
    """`netsh wlan show networks mode=bssid` -> one row per access point (BSSID), with the security of its network."""
    righe, rete, ap = [], None, None
    for riga in (testo or "").splitlines():
        ssid = re.match(r"^SSID \d+\s*:\s?(.*)$", riga.strip())
        if ssid:
            rete = {"ssid": ssid.group(1).strip(), "auth": "", "cipher": ""}
            ap = None
            continue
        bssid = re.match(r"^BSSID \d+\s*:\s*([0-9a-fA-F:]{17})", riga.strip())
        if bssid and rete is not None:
            ap = dict(rete, bssid=bssid.group(1).upper(), signal=None, radio="", band="", channel=None, stations=None, utilization=None)
            righe.append(ap)
            continue
        campo = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", riga)
        if not campo or rete is None:
            continue
        chiave, valore = _key(campo.group(1)), campo.group(2)
        if ap is None:
            if chiave in ("auth", "cipher"):
                rete[chiave] = valore
            continue
        if chiave == "signal":
            numero = re.match(r"(\d+)", valore)
            ap["signal"] = int(numero.group(1)) if numero else None
        elif chiave == "channel" and valore.isdigit():
            ap["channel"] = int(valore)
        elif chiave in ("radio", "band"):
            ap[chiave] = valore
        elif chiave == "stations" and valore.isdigit():
            ap["stations"] = int(valore)
        elif chiave == "utilization":
            percento = re.search(r"\((\d+)\s*%\)", valore)
            ap["utilization"] = int(percento.group(1)) if percento else None
    for ap in righe:
        if not ap["band"] and ap["channel"]:
            ap["band"] = "2.4 GHz" if ap["channel"] <= 14 else "5 GHz"
    return righe


def parse_interfaces(testo: str) -> List[dict]:
    """Every Wi-Fi adapter in `netsh wlan show interfaces`, with the network it is connected to."""
    adattatori: List[dict] = []
    for riga in (testo or "").splitlines():
        campo = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", riga)
        if not campo:
            continue
        etichetta, valore = campo.group(1).strip().lower(), campo.group(2)
        if etichetta in ("name", "nome"):
            adattatori.append({"name": valore})
            continue
        if not adattatori:
            continue
        voce = adattatori[-1]
        if etichetta in ("state", "stato"):
            voce["state"] = valore
            voce["connected"] = bool(re.fullmatch(r"connected|connessa|connesso", valore, re.I))
        elif etichetta == "ssid":
            voce["ssid"] = valore
        elif etichetta in ("ap bssid", "bssid ap"):
            voce["bssid"] = valore.upper()
        elif etichetta == "rssi":
            voce["rssi"] = int(valore) if re.fullmatch(r"-?\d+", valore) else None
        elif re.fullmatch(r"description|descrizione", etichetta):
            voce["adapter"] = valore
    attiva = next((i for i, a in enumerate(adattatori) if a.get("connected")), 0)
    for i, a in enumerate(adattatori):
        a["default"] = i == attiva
    return adattatori


def wifi_interfaces() -> List[dict]:
    try:
        testo = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [{"name": a["name"], "description": a.get("adapter", ""), "connected": a.get("connected", False), "ssid": a.get("ssid", ""),
             "default": a["default"]} for a in parse_interfaces(testo)]


def parse_interface(testo: str) -> dict:
    """The network this PC is connected to, from `netsh wlan show interfaces`."""
    connessa = {}
    for riga in (testo or "").splitlines():
        campo = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", riga)
        if not campo:
            continue
        etichetta, valore = campo.group(1).strip().lower(), campo.group(2)
        if etichetta == "ssid":
            connessa["ssid"] = valore
        elif etichetta in ("ap bssid", "bssid ap"):
            connessa["bssid"] = valore.upper()
        elif etichetta == "rssi":
            connessa["rssi"] = int(valore) if re.fullmatch(r"-?\d+", valore) else None
        elif re.fullmatch(r"description|descrizione", etichetta):
            connessa["adapter"] = valore
    return connessa


def security(auth: str, cipher: str) -> dict:
    """How safe a network is, from its authentication and cipher."""
    testo = f"{auth} {cipher}".lower()
    if re.search(r"open|aperta|none|nessuna", auth.lower()) and "owe" not in testo:
        return {"level": "risk", "label": "Open", "text": "No password: anyone nearby can join and read unencrypted traffic."}
    if "wep" in testo:
        return {"level": "risk", "label": "WEP", "text": "WEP is broken: it can be cracked in minutes."}
    if "tkip" in testo:
        return {"level": "review", "label": "WPA (TKIP)", "text": "TKIP is outdated: set the router to WPA2 (AES/CCMP) or WPA3."}
    if "wpa3" in testo or "sae" in testo:
        return {"level": "ok", "label": "WPA3", "text": "The current standard."}
    if "wpa2" in testo:
        return {"level": "ok", "label": "WPA2", "text": "Safe with a strong password; WPA3 is better when the devices support it."}
    if "owe" in testo:
        return {"level": "review", "label": "Enhanced Open", "text": "Encrypted but without a password."}
    return {"level": "review", "label": auth or "Unknown", "text": "Security not recognised."}


def dbm(segnale: Optional[int]) -> Optional[int]:
    """netsh quality (0-100%) to an approximate dBm, as Windows computes it."""
    return None if segnale is None else round(segnale / 2 - 100)


def best_channel(reti: List[dict], banda: str) -> Optional[int]:
    """The least crowded channel of a band: on 2.4 GHz only 1, 6 and 11 (they do not overlap), counting neighbours."""
    if banda == "2.4 GHz":
        peso = {c: 0.0 for c in (1, 6, 11)}
        for r in reti:
            if r.get("band") == "2.4 GHz" and r.get("channel"):
                for c in peso:
                    distanza = abs(r["channel"] - c)
                    if distanza < 5:  # 2.4 GHz channels overlap with the four next to them
                        peso[c] += (5 - distanza) / 5 * (1 + (r.get("signal") or 0) / 100)
        return min(peso, key=peso.get)
    usati = Counter(r["channel"] for r in reti if str(r.get("band", "")).startswith("5") and r.get("channel"))
    candidati = (36, 40, 44, 48, 149, 153, 157, 161)
    return min(candidati, key=lambda c: (usati.get(c, 0), c)) if usati else None


def wifi_advice(reti: List[dict], connessa: dict) -> List[dict]:
    consigli = []
    # Your network once per band: 2.4 and 5 GHz have their own channel and neighbours.
    per_banda: Dict[str, dict] = {}
    for r in reti:
        if r["own"] and r["band"] not in per_banda:
            per_banda[r["band"]] = r
    for i, r in enumerate(per_banda.values()):
        if i == 0 and r["security"]["level"] != "ok":
            consigli.append({"level": r["security"]["level"], "text": f"Your network {r['ssid']}: {r['security']['text']}"})
        if r["signal"] is not None and r["signal"] < 50:
            consigli.append({"level": "review", "text": f"The {r['band']} signal of {r['ssid']} here is weak ({r['signal']}%): move closer to the router "
                                                         "or add a mesh point or repeater."})
        migliore = best_channel(reti, r["band"])
        sovrapposto = r["band"] == "2.4 GHz" and r["channel"] not in (1, 6, 11)
        if migliore and migliore != r["channel"] and (r["same_channel"] >= 3 or sovrapposto):
            motivo = (f"channel {r['channel']} overlaps with its neighbours (on 2.4 GHz only 1, 6 and 11 do not)" if sovrapposto
                      else f"{r['same_channel']} other access points share channel {r['channel']}")
            consigli.append({"level": "info", "text": f"Your network on {r['band']}: {motivo}. Channel {migliore} is less crowded here (router settings)."})
    aperte = sorted({r["ssid"] or "(hidden)" for r in reti if r["security"]["level"] == "risk" and not r["own"]})
    if aperte:
        consigli.append({"level": "info", "text": "Open or weak networks nearby: " + ", ".join(aperte[:6]) + ". Do not join them without a VPN."})
    if not connessa.get("ssid"):
        consigli.append({"level": "info", "text": "This PC is not connected to Wi-Fi now (cable or Wi-Fi off)."})
    return consigli


def wifi_scan(fresco: bool = True, nome: Optional[str] = None) -> dict:
    """The Wi-Fi networks heard by one adapter: the chosen one, or the connected one by default."""
    try:
        interfaccia = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=30,
                                     encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError) as errore:
        return {"error": f"netsh could not be run: {errore}", "networks": []}
    adattatori = parse_interfaces(interfaccia)
    scelto = next((a for a in adattatori if a["name"] == nome), None) if nome else next((a for a in adattatori if a["default"]), None)
    if nome and scelto is None:
        raise ValueError(f"There is no Wi-Fi adapter called {nome}.")
    comando = ["netsh", "wlan", "show", "networks", "mode=bssid"] + ([f"interface={scelto['name']}"] if scelto else [])
    quanti = trigger_wifi_scan(descrizione=scelto.get("adapter") if scelto else None) if fresco else 0
    try:
        reti_testo = subprocess.run(comando, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError) as errore:
        return {"error": f"netsh could not be run: {errore}", "networks": []}
    if re.search(r"location permission|autorizzazione.*posizione|posizione.*autorizzazione", reti_testo, re.I):
        return {"error": "Windows needs Location turned on to list Wi-Fi networks: Settings › Privacy & security › Location.", "networks": [],
                "settings": "ms-settings:privacy-location"}
    if not re.search(r"SSID \d+", reti_testo) and re.search(r"wlansvc|not running|non è in esecuzione|no wireless|nessuna interfaccia",
                                                           reti_testo + interfaccia, re.I):
        return {"error": "This PC has no Wi-Fi adapter, or the WLAN AutoConfig service is not running.", "networks": []}
    connessa = {k: scelto.get(k) for k in ("ssid", "bssid", "rssi", "adapter") if scelto.get(k) is not None} if scelto else {}
    reti = parse_wifi(reti_testo)
    for r in reti:
        r.update(security=security(r["auth"], r["cipher"]), dbm=dbm(r["signal"]), vendor=VENDORS.get(r["bssid"][:8], ""),
                 hidden=not r["ssid"], connected=r["bssid"] == connessa.get("bssid"), own=bool(r["ssid"]) and r["ssid"] == connessa.get("ssid"))
    reti.sort(key=lambda r: (not r["connected"], not r["own"], -(r["signal"] or 0)))
    canali = Counter((r["band"], r["channel"]) for r in reti if r["channel"])
    for r in reti:
        r["same_channel"] = canali.get((r["band"], r["channel"]), 1) - 1
    return {"networks": reti, "connected": connessa, "adapters": quanti, "interface": scelto["name"] if scelto else "",
            "scanned": datetime.now().isoformat(timespec="seconds"),
            "channels": [{"band": b, "channel": c, "count": n} for (b, c), n in sorted(canali.items(), key=lambda x: (x[0][0], x[0][1]))],
            "best": {"2.4 GHz": best_channel(reti, "2.4 GHz"), "5 GHz": best_channel(reti, "5 GHz")}, "advice": wifi_advice(reti, connessa)}


# ---------- Bluetooth ----------

# The Bluetooth adapters (radios): not the paired devices and services, which the same device class also lists.
SCRIPT_RADIOS = r"""
@(Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -notmatch '^(BTHENUM|BTHLEDEVICE|BTHLE|BTH|SWD)\\' } |
  ForEach-Object { [ordered]@{ name = "$($_.FriendlyName)"; status = "$($_.Status)" } }) | ConvertTo-Json -Compress
"""


def parse_radios(testo: str) -> List[dict]:
    try:
        dati = json.loads(testo or "[]")
    except ValueError:
        return []
    voci = [v for v in (dati if isinstance(dati, list) else [dati]) if isinstance(v, dict) and v.get("name")]
    radio = [{"name": str(v["name"])[:100], "status": str(v.get("status") or ""), "active": str(v.get("status")) == "OK"} for v in voci]
    radio.sort(key=lambda v: not v["active"])
    for i, v in enumerate(radio):
        v["default"] = i == 0
    return radio


def bluetooth_radios() -> List[dict]:
    try:
        return parse_radios(subprocess.run(powershell_command(SCRIPT_RADIOS), capture_output=True, text=True, timeout=60).stdout)
    except (OSError, subprocess.SubprocessError):
        return []


SCRIPT_BLUETOOTH = r'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType = WindowsRuntime] | Out-Null
$props = [System.Collections.Generic.List[string]]@('System.Devices.Aep.DeviceAddress', 'System.Devices.Aep.IsPaired', 'System.Devices.Aep.IsConnected',
  'System.Devices.Aep.SignalStrength', 'System.Devices.Aep.Category')
$kinds = @(@('Classic', '{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}'), @('Low Energy', '{bb7bb05e-5972-42b5-94fc-76eaa7084d49}'))
# Both searches run at the same time: each one listens for about 30 seconds.
$tasks = foreach ($k in $kinds) {
  $op = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync("System.Devices.Aep.ProtocolId:=""$($k[1])""", $props,
    [Windows.Devices.Enumeration.DeviceInformationKind]::AssociationEndpoint)
  $asTask.MakeGenericMethod([Windows.Devices.Enumeration.DeviceInformationCollection]).Invoke($null, @($op))
}
[System.Threading.Tasks.Task]::WaitAll([System.Threading.Tasks.Task[]]$tasks, 45000) | Out-Null
$out = for ($i = 0; $i -lt $tasks.Count; $i++) {
  if ($tasks[$i].Status -ne 'RanToCompletion') { continue }
  foreach ($d in $tasks[$i].Result) {
    $p = @{}; foreach ($kv in $d.Properties) { $p[$kv.Key] = $kv.Value }
    [ordered]@{ kind = $kinds[$i][0]; name = "$($d.Name)"; address = "$($p['System.Devices.Aep.DeviceAddress'])"; paired = [bool]$p['System.Devices.Aep.IsPaired']
      connected = [bool]$p['System.Devices.Aep.IsConnected']; rssi = $p['System.Devices.Aep.SignalStrength']; category = "$($p['System.Devices.Aep.Category'])" }
  }
}
$radio = @(Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match 'Adapter|Radio|Wireless Bluetooth|Bluetooth\(R\)|Intel' } |
  Select-Object -First 1 | ForEach-Object { [ordered]@{ name = "$($_.FriendlyName)"; status = "$($_.Status)" } })
[ordered]@{ devices = @($out); radio = $radio } | ConvertTo-Json -Depth 4 -Compress
'''

CATEGORIES = [
    (r"input\.gaming", "Game controller"), (r"communication\.phone", "Phone"), (r"audio\.(headphone|headset|earbud)", "Headphones"),
    (r"audio\.speaker", "Speaker"), (r"^audio", "Audio device"), (r"input\.keyboard", "Keyboard"), (r"input\.mouse", "Mouse"), (r"^input", "Input device"),
    (r"computer", "Computer"), (r"wearable|watch", "Watch or wearable"), (r"health|fitness", "Health or fitness device"), (r"printer", "Printer"),
    (r"display|television", "TV or display"),
]
NAMES = [
    (r"airpods|buds|earbuds|headphone|wh-1000|jbl (tune|live)|bose qc", "Headphones"), (r"iphone|galaxy|pixel|redmi|xiaomi|oneplus", "Phone"),
    (r"watch|\bband\b|fitbit|garmin|amazfit", "Watch or wearable"), (r"dualsense|dualshock|xbox wireless|controller|joy-con", "Game controller"),
    (r"govee|\bhue\b|lamp|light|bulb|\bled\b", "Smart light"), (r"jbl|sonos|speaker|boombox|soundbar|echo", "Speaker"), (r"keyboard|mx keys|k380", "Keyboard"),
    (r"mouse|mx master|mx anywhere", "Mouse"), (r"\btv\b|bravia", "TV or display"), (r"airtag|\btile\b|smarttag", "Tracker"),
]


def bt_kind(device: dict) -> str:
    categoria = (device.get("category") or "").lower()
    for schema, nome in CATEGORIES:
        if re.search(schema, categoria):
            return nome
    testo = (device.get("name") or "").lower()
    for schema, nome in NAMES:
        if re.search(schema, testo):
            return nome
    return "Unnamed device" if not device.get("name") else "Bluetooth device"


def distance(rssi) -> str:
    """A rough distance from the signal strength (walls and bodies change it a lot)."""
    if not isinstance(rssi, (int, float)) or isinstance(rssi, bool):
        return ""
    return "very close (< 1 m)" if rssi >= -55 else "near (1–3 m)" if rssi >= -70 else "in the room or next door" if rssi >= -85 else "far"


def parse_bluetooth(testo: str) -> dict:
    try:
        dati = json.loads(testo or "{}")
    except ValueError:
        return {"devices": [], "radio": None}
    voci = dati.get("devices") or []
    voci = voci if isinstance(voci, list) else [voci]
    radio = dati.get("radio") or []
    radio = (radio if isinstance(radio, list) else [radio])[:1]
    dispositivi = {}
    for v in voci:
        if not isinstance(v, dict):
            continue
        indirizzo = str(v.get("address") or "").upper()
        if not re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", indirizzo):
            continue
        rssi = v.get("rssi") if isinstance(v.get("rssi"), (int, float)) and not isinstance(v.get("rssi"), bool) else None
        voce = {"address": indirizzo, "name": str(v.get("name") or "")[:80], "type": str(v.get("kind") or ""), "paired": bool(v.get("paired")),
                "connected": bool(v.get("connected")), "rssi": rssi, "category": str(v.get("category") or "")[:60]}
        voce.update(kind=bt_kind(voce), distance=distance(rssi), vendor=VENDORS.get(indirizzo[:8], ""))
        vecchia = dispositivi.get(indirizzo)
        if vecchia is None or (rssi is not None and (vecchia["rssi"] is None or rssi > vecchia["rssi"])):
            dispositivi[indirizzo] = voce
    elenco = sorted(dispositivi.values(), key=lambda d: (not d["connected"], not d["paired"], -(d["rssi"] if d["rssi"] is not None else -999)))
    return {"devices": elenco, "radio": radio[0] if radio else None}


def bluetooth_scan() -> dict:
    inizio = time.time()
    try:
        risultato = subprocess.run(powershell_command(SCRIPT_BLUETOOTH), capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"error": "The Bluetooth search did not finish within 90 seconds.", "devices": [], "scanned": datetime.now().isoformat(timespec="seconds")}
    except OSError as errore:
        return {"error": f"PowerShell could not be run: {errore}", "devices": [], "scanned": datetime.now().isoformat(timespec="seconds")}
    dati = parse_bluetooth(risultato.stdout)
    if not dati["devices"] and not dati["radio"]:
        dati["error"] = "No Bluetooth adapter answered: it may be turned off (Settings › Bluetooth & devices) or missing."
    dati.update(scanned=datetime.now().isoformat(timespec="seconds"), seconds=round(time.time() - inizio, 1))
    return dati


def mark_new(risultato: dict, precedente: Optional[dict]) -> dict:
    """First time each Bluetooth device was seen; unpaired ones new since the previous scan (the first scan is the baseline)."""
    noti: Dict[str, str] = dict((precedente or {}).get("known", {}))
    primo = not noti
    for d in risultato.get("devices", []):
        d["first_seen"] = noti.get(d["address"], risultato["scanned"])
        d["new"] = d["address"] not in noti and not primo and not d["paired"]
        noti.setdefault(d["address"], risultato["scanned"])
    risultato["known"] = dict(list(noti.items())[-1000:])
    return risultato


class RadioScanner:
    def __init__(self, data_dir: Path):
        self.wifi_path = Path(data_dir) / "wifi_scan.json"
        self.bt_path = Path(data_dir) / "bluetooth_scan.json"

    @staticmethod
    def _read(percorso: Path) -> Optional[dict]:
        try:
            return json.loads(percorso.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _save(percorso: Path, dati: dict) -> dict:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(json.dumps(dati), encoding="utf-8")
        return dati

    def last_wifi(self) -> Optional[dict]:
        return self._read(self.wifi_path)

    def last_bluetooth(self) -> Optional[dict]:
        return self._read(self.bt_path)

    def run_wifi(self, nome: Optional[str] = None) -> dict:
        return self._save(self.wifi_path, wifi_scan(nome=nome))

    def run_bluetooth(self) -> dict:
        return self._save(self.bt_path, mark_new(bluetooth_scan(), self.last_bluetooth()))


def for_data_dir(data_dir: Path) -> RadioScanner:
    return RadioScanner(data_dir)
