"""Precise undo for registry fixes. While a fix runs, every registry value it is about to write or delete is read
first and kept in a journal (value and type, or "absent"). Undo puts back exactly those values and nothing else,
while a restore point would take the whole PC back.

The journal fills itself through the write helpers (tools.write_dword / write_string / delete_value and
ottimizza_pc.scrivi_registro call before_write). Fixes that change the registry from a PowerShell script declare
the values they touch in TOUCHES, so the runner can read them before the script starts."""
from __future__ import annotations

import base64
import re
import subprocess
import threading
from typing import Dict, List, Optional, Sequence, Tuple

HKLM, HKCU = "HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER"
ROOTS = (HKLM, HKCU)
MAX_ENTRIES = 200

# Fixes whose registry writes happen inside a PowerShell script: (root, key, value name).
_NCSI = r"SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet"
_SEARCH = r"Software\Microsoft\Windows\CurrentVersion\Search"
TOUCHES: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "updates.delivery_lan_only": ((HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config", "DODownloadMode"),),
    "security.rdp_nla_on": ((HKLM, r"SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp", "UserAuthentication"),),
    "network.prefer_ipv4": ((HKLM, r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents"),),
    "network.ipv6_default": ((HKLM, r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents"),),
    "network.ncsi_reset": tuple((HKLM, _NCSI, n) for n in (
        "EnableActiveProbing", "ActiveWebProbeHost", "ActiveWebProbePath", "ActiveWebProbeContent", "ActiveDnsProbeHost",
        "ActiveDnsProbeContent", "ActiveWebProbeHostV6", "ActiveWebProbePathV6", "ActiveWebProbeContentV6", "ActiveDnsProbeHostV6",
        "ActiveDnsProbeContentV6")) + tuple((HKLM, r"SOFTWARE\Policies\Microsoft\Windows\NetworkConnectivityStatusIndicator", n)
                                            for n in ("NoActiveProbe", "DisablePassivePolling", "UseGlobalDNS")),
    "security.show_extensions": ((HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "HideFileExt"),),
    "security.remote_assistance_off": ((HKLM, r"SYSTEM\CurrentControlSet\Control\Remote Assistance", "fAllowToGetHelp"),),
    "performance.web_search_off": ((HKCU, _SEARCH, "BingSearchEnabled"), (HKCU, _SEARCH, "CortanaConsent"),
                                   (HKCU, r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions")),
    "performance.mpo_off": ((HKLM, r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode"),),
    "performance.mpo_default": ((HKLM, r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode"),),
    "performance.end_task_on": ((HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings", "TaskbarEndTask"),),
}

_local = threading.local()


class Journal:
    """The previous state of every value a fix touched (registry values, and since 2.7 power settings, the active
    power plan and service start types), first sight only."""

    def __init__(self, reader=None):
        self.entries: List[dict] = []
        self._seen = set()
        self._read = reader or read_value

    def record(self, root: str, key: str, name: str) -> None:
        marca = (root, key.lower(), name.lower())
        if root not in ROOTS or marca in self._seen or len(self.entries) >= MAX_ENTRIES:
            return
        self._seen.add(marca)
        dato = self._read(root, key, name)
        voce = {"root": root, "key": key, "name": name, "existed": dato is not None}
        if dato is not None:
            voce["type"], voce["value"] = encode(*dato)
        self.entries.append(voce)

    def record_other(self, kind: str, ident: dict, value) -> None:
        """A power setting, the active power plan or the start type of a service (2.7), first sight only."""
        marca = (kind,) + tuple(str(v).lower() for v in ident.values())
        if marca in self._seen or len(self.entries) >= MAX_ENTRIES:
            return
        self._seen.add(marca)
        self.entries.append(dict(ident, kind=kind, existed=value is not None, value=value))

    def with_current(self, reader=None) -> List[dict]:
        """The entries with the value each one has now ("after"), to show what the fix changed."""
        leggi = reader or self._read
        risultato = []
        for voce in self.entries:
            copia = dict(voce)
            if voce.get("kind") in OTHER_READERS:
                ora = OTHER_READERS[voce["kind"]](voce)
                copia.update(after_existed=ora is not None, after_value=ora)
            else:
                ora = leggi(voce["root"], voce["key"], voce["name"])
                copia["after_existed"] = ora is not None
                if ora is not None:
                    copia["after_type"], copia["after_value"] = encode(*ora)
            risultato.append(copia)
        return risultato


def begin(reader=None) -> Journal:
    _local.journal = Journal(reader)
    return _local.journal


def end() -> Optional[Journal]:
    journal = getattr(_local, "journal", None)
    _local.journal = None
    return journal


def before_write(root: str, key: str, name: str) -> None:
    """Called by the registry write helpers just before they change a value."""
    journal = getattr(_local, "journal", None)
    if journal is not None:
        try:
            journal.record(root, key, name)
        except Exception:  # the journal must never stop the fix itself
            pass


def declare(action_id: str, journal: Journal) -> None:
    for root, key, name in TOUCHES.get(action_id, ()):
        journal.record(root, key, name)
    for servizio in SERVICE_TOUCHES.get(action_id, ()):
        _safe(lambda: journal.record_other("service", {"name": servizio}, read_service({"name": servizio})))


# ---------- 2.7: power settings, power plan and service start types ----------

# PowerShell fixes that change the start type of services (the Python helpers of ottimizza_pc keep their own backup).
SERVICE_TOUCHES: Dict[str, Tuple[str, ...]] = {
    "network.discovery_on": ("FDResPub", "fdPHost", "SSDPSRV", "upnphost"),
    "updates.bits_reset": ("BITS",),
    "integrity.reregister_msi": ("msiserver",),
    "integrity.restart_vss": ("VSS", "swprv"),
    "integrity.time_sync": ("W32Time",),
    "services.search_manual": ("WSearch",),
    "services.sysmain_manual": ("SysMain",),
}
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _run(comando: List[str]) -> str:
    finito = subprocess.run(comando, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return finito.stdout or ""


RUN = _run  # replaced in tests


def _safe(funzione) -> None:
    try:
        funzione()
    except Exception:  # the journal must never stop the fix itself
        pass


def parse_power_query(testo: str) -> Optional[List[int]]:
    """AC and DC index of one setting from `powercfg /query`: in every language they are the last two hex numbers."""
    numeri = re.findall(r":\s*0x([0-9a-fA-F]+)\s*$", testo or "", re.M)
    return [int(numeri[-2], 16), int(numeri[-1], 16)] if len(numeri) >= 2 else None


def read_power(voce: dict) -> Optional[List[int]]:
    return parse_power_query(RUN(["powercfg", "/query", "SCHEME_CURRENT", voce["sub"], voce["setting"]]))


def read_plan(voce: dict) -> Optional[str]:
    trovato = _GUID.search(RUN(["powercfg", "/getactivescheme"]))
    return trovato.group(0).lower() if trovato else None


def read_service(voce: dict) -> Optional[str]:
    import ottimizza_pc as op
    return op.leggi_avvio_servizio(RUN(["sc", "qc", voce["name"]]))


OTHER_READERS = {"power": read_power, "plan": read_plan, "service": read_service}


def _journal() -> Optional[Journal]:
    return getattr(_local, "journal", None)


def before_power(sub: str, setting: str) -> None:
    """Called by tools.power_settings before it changes one setting of the active plan."""
    journal = _journal()
    if journal is not None:
        ident = {"sub": sub, "setting": setting}
        _safe(lambda: journal.record_other("power", ident, read_power(ident)))


def before_plan() -> None:
    """Called before a fix switches the active power plan."""
    journal = _journal()
    if journal is not None:
        _safe(lambda: journal.record_other("plan", {}, read_plan({})))


OTHER_RESTORERS: dict = {}  # more kinds added by other modules (custom tools: "script")


def _restore_other(voce: dict) -> None:
    tipo, valore = voce["kind"], voce.get("value")
    if tipo in OTHER_RESTORERS:
        OTHER_RESTORERS[tipo](voce)
        return
    if valore is None:
        return  # nothing was there to put back
    if tipo == "power":
        for verbo, indice in (("/setacvalueindex", valore[0]), ("/setdcvalueindex", valore[1])):
            RUN(["powercfg", verbo, "SCHEME_CURRENT", voce["sub"], voce["setting"], str(int(indice))])
        RUN(["powercfg", "/setactive", "SCHEME_CURRENT"])
    elif tipo == "plan":
        if not _GUID.fullmatch(str(valore)):
            raise OSError("invalid power plan")
        RUN(["powercfg", "/setactive", str(valore)])
    elif tipo == "service":
        if valore not in ("auto", "delayed-auto", "demand", "disabled") or not re.fullmatch(r"[\w.\-]{1,80}", voce["name"]):
            raise OSError("invalid service entry")
        RUN(["sc", "config", voce["name"], "start=", valore])


# ---------- registry access ----------

def read_value(root: str, key: str, name: str):
    """(value, type) or None when the value does not exist."""
    import winreg
    try:
        with winreg.OpenKey(getattr(winreg, root), key) as handle:
            return winreg.QueryValueEx(handle, name)
    except OSError:
        return None


def encode(value, kind: int) -> Tuple[int, object]:
    """JSON-safe form: bytes become base64, everything else stays as it is."""
    if isinstance(value, (bytes, bytearray)):
        return kind, {"b64": base64.b64encode(bytes(value)).decode()}
    return kind, value


def decode(value):
    if isinstance(value, dict) and "b64" in value:
        return base64.b64decode(value["b64"])
    return value


def changed(entries: Sequence[dict]) -> List[dict]:
    """Entries whose value is different now than before the fix."""
    return [v for v in entries if v.get("existed") != v.get("after_existed")
            or (v.get("existed") and (v.get("value") != v.get("after_value") or v.get("type") != v.get("after_type")))]


def describe(voce: dict) -> str:
    if voce.get("kind") in OTHER_READERS:
        nome = {"power": lambda v: f"Power setting {v['sub']}/{v['setting']} (AC, DC)", "plan": lambda v: "Active power plan",
                "service": lambda v: f"Service {v['name']} start type",
                "script": lambda v: f"Undo script of custom tool {v.get('tool')}"}.get(voce["kind"], lambda v: voce["kind"])(voce)
        if voce["kind"] == "script":
            return nome
        return f"{nome}: {voce.get('value')!r} -> {voce.get('after_value')!r}"
    root = "HKLM" if voce["root"] == HKLM else "HKCU"
    prima = repr(voce.get("value")) if voce.get("existed") else "absent"
    dopo = repr(voce.get("after_value")) if voce.get("after_existed") else "absent"
    return f"{root}\\{voce['key']}\\{voce['name']}: {prima} -> {dopo}"


def restore(entries: Sequence[dict], writer=None, deleter=None) -> Tuple[int, List[str]]:
    """Puts every value back as it was before the fix. Returns how many were restored and the errors."""
    scrivi, elimina = writer or _write_value, deleter or _delete_value
    fatti, errori = 0, []
    for voce in entries:
        if voce.get("kind") in OTHER_READERS:
            try:
                _restore_other(voce)
                fatti += 1
            except (OSError, subprocess.SubprocessError) as errore:
                errori.append(f"{describe(voce)}: {errore}")
            continue
        if voce.get("root") not in ROOTS:
            continue
        try:
            if voce.get("existed"):
                scrivi(voce["root"], voce["key"], voce["name"], decode(voce.get("value")), int(voce.get("type", 4)))
            else:
                elimina(voce["root"], voce["key"], voce["name"])
            fatti += 1
        except OSError as errore:
            errori.append(f"{voce['key']}\\{voce['name']}: {errore}")
    return fatti, errori


def _write_value(root: str, key: str, name: str, value, kind: int) -> None:
    import winreg
    with winreg.CreateKeyEx(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, name, 0, kind, value)


def _delete_value(root: str, key: str, name: str) -> None:
    import winreg
    try:
        with winreg.OpenKey(getattr(winreg, root), key, 0, winreg.KEY_SET_VALUE) as handle:
            winreg.DeleteValue(handle, name)
    except FileNotFoundError:
        pass  # already absent: nothing to undo
