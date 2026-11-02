"""Live processes and services (stdlib only).

Processes come from the Process performance counters (CPU, private memory, threads, handles, I/O per
PID) plus the image path from the Windows API; services from Win32_Service. Ending a process or
stopping a service refuses the parts Windows cannot live without."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import subprocess
import threading
import time
from ctypes import wintypes
from typing import Callable, Dict, List, Optional

import wmm  # noqa: F401
import ottimizza_pc as op

from .live import MB, _INSTANCE, _Pdh

COUNTERS = {
    "cpu": r"\Process(*)\% Processor Time",
    "memory": r"\Process(*)\Working Set - Private",
    "pid": r"\Process(*)\ID Process",
    "threads": r"\Process(*)\Thread Count",
    "handles": r"\Process(*)\Handle Count",
    "io": r"\Process(*)\IO Data Bytes/sec",
    "elapsed": r"\Process(*)\Elapsed Time",
}
# Ending these crashes or locks Windows.
CRITICAL_PROCESSES = frozenset({"system", "idle", "registry", "smss", "csrss", "wininit", "winlogon", "services", "lsass", "lsaiso",
                                "memory compression", "secure system", "fontdrvhost", "dwm", "svchost", "conhost", "sihost"})
# Stopping these breaks networking, security, logging or the session.
CRITICAL_SERVICES = frozenset(s.lower() for s in op.SERVIZI_PROTETTI) | frozenset({
    "rpcss", "rpceptmapper", "dcomlaunch", "lsm", "samss", "winmgmt", "plugplay", "power", "brokerinfrastructure", "coremessagingregistrar",
    "gpsvc", "profsvc", "schedule", "systemeventsbroker", "dhcp", "dnscache", "nsi", "mpssvc", "bfe", "cryptsvc", "windefend", "eventlog",
    "audiosrv", "audioendpointbuilder", "appinfo", "staterepository", "usermanager", "tokenbroker", "wlansvc"})
SERVICE_NAME = re.compile(r"^[\w.\-@$]{1,128}$")
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SERVICES_SCRIPT = ("Get-CimInstance Win32_Service | Select-Object Name, DisplayName, State, StartMode, ProcessId, PathName, Description | "
                   "ConvertTo-Json -Compress")


DETAILS_SCRIPT = r"""
$owner = @{}
try { Get-Process -IncludeUserName -ErrorAction Stop | ForEach-Object { $owner[$_.Id] = @($_.UserName, $_.Company, $_.Description, $_.ProductVersion, "$($_.PriorityClass)") } }
catch { Get-Process | ForEach-Object { $owner[$_.Id] = @('', $_.Company, $_.Description, $_.ProductVersion, "$($_.PriorityClass)") } }
@(Get-CimInstance Win32_Process | ForEach-Object {
  $o = $owner[[int]$_.ProcessId]
  [ordered]@{ pid = [int]$_.ProcessId; ppid = [int]$_.ParentProcessId; session = [int]$_.SessionId; command = $_.CommandLine
    started = if ($_.CreationDate) { $_.CreationDate.ToString('o') } else { $null }
    user = if ($o) { $o[0] } else { '' }; company = if ($o) { $o[1] } else { '' }; description = if ($o) { $o[2] } else { '' }
    version = if ($o) { $o[3] } else { '' }; priority = if ($o) { $o[4] } else { '' } }
}) | ConvertTo-Json -Compress
"""
PRIORITIES = {"idle": "Idle", "below_normal": "BelowNormal", "normal": "Normal", "above_normal": "AboveNormal", "high": "High"}
CREATE_NEW_CONSOLE = 0x00000010


class ControlError(ValueError):
    """The request is refused (protected, unknown or stale target)."""


def image_path(pid: int) -> str:
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        dimensione = wintypes.DWORD(len(buffer))
        if k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(dimensione)):
            return buffer.value
        return ""
    finally:
        k32.CloseHandle(handle)


def merge(samples: Dict[str, Dict[str, float]], cpus: int, paths: Callable[[int], str], services: Dict[int, List[str]]) -> List[dict]:
    """Joins the counter arrays (same instance names) into one row per process."""
    righe = []
    for istanza, pid in samples.get("pid", {}).items():
        pid = int(pid)
        nome = _INSTANCE.sub("", istanza)
        if istanza == "_Total" or (pid == 0 and nome.lower() == "idle"):
            continue
        percorso = paths(pid)
        righe.append({
            "pid": pid, "name": os.path.basename(percorso) if percorso else nome + ("" if pid in (0, 4) else ".exe"),
            "cpu": round(max(0.0, samples.get("cpu", {}).get(istanza, 0.0)) / max(1, cpus), 1),
            "memory_mb": round(samples.get("memory", {}).get(istanza, 0.0) / MB, 1),
            "threads": int(samples.get("threads", {}).get(istanza, 0)),
            "handles": int(samples.get("handles", {}).get(istanza, 0)),
            "io_bps": int(samples.get("io", {}).get(istanza, 0)),
            "uptime_s": int(samples.get("elapsed", {}).get(istanza, 0)),
            "path": percorso,
            "services": services.get(pid, []),
            "critical": nome.lower() in CRITICAL_PROCESSES,
        })
    return sorted(righe, key=lambda r: (-r["cpu"], -r["memory_mb"]))


class ProcessMonitor:
    def __init__(self, services_loader: Optional[Callable[[], List[dict]]] = None,
                 details_loader: Optional[Callable[[], Dict[int, dict]]] = None):
        self._details: Dict[int, dict] = {}
        self._details_time = 0.0
        self._details_loading = False
        self._details_loader = details_loader or load_details
        self._lock = threading.Lock()
        self._pdh: Optional[_Pdh] = None
        self._counters: Dict[str, object] = {}
        self._paths: Dict[int, str] = {}
        self._services: List[dict] = []
        self._services_time = 0.0
        self._services_loader = services_loader or load_services
        self.cpus = os.cpu_count() or 1

    def _path(self, pid: int) -> str:
        if pid not in self._paths:
            try:
                self._paths[pid] = image_path(pid)
            except OSError:
                self._paths[pid] = ""
        return self._paths[pid]

    def services(self, fresh: bool = False) -> List[dict]:
        with self._lock:
            if fresh or time.monotonic() - self._services_time > 5:
                self._services = self._services_loader()
                self._services_time = time.monotonic()
            return list(self._services)

    def details(self, fresh: bool = False) -> Dict[int, dict]:
        """Owner, parent, command line, company, priority: about two seconds to read, so they are refreshed
        in the background every 10 s and only the first request waits for them."""
        with self._lock:
            scaduti = fresh or time.monotonic() - self._details_time > 10
            primo = not self._details
            if scaduti and not self._details_loading:
                self._details_loading = True
                self._details_time = time.monotonic()
                filo = threading.Thread(target=self._load_details, name="wmm-process-details", daemon=True)
                filo.start()
            else:
                filo = None
        if primo and filo is not None:
            filo.join(timeout=15)
        return self._details

    def _load_details(self) -> None:
        try:
            dettagli = self._details_loader()
        except (OSError, ValueError, subprocess.SubprocessError):
            dettagli = None  # counters still work without the details
        with self._lock:
            if dettagli is not None:
                self._details = dettagli
            self._details_loading = False

    def processes(self, full: bool = False) -> dict:
        servizi: Dict[int, List[str]] = {}
        for s in self.services():
            if s.get("pid"):
                servizi.setdefault(int(s["pid"]), []).append(s["name"])
        dettagli = self.details() if full else {}
        with self._lock:
            if self._pdh is None:
                self._pdh = _Pdh()
                self._counters = {k: self._pdh.add(v) for k, v in COUNTERS.items()}
                self._pdh.collect()  # rate counters need two samples
                time.sleep(0.4)
            self._pdh.collect()
            campioni = {k: self._pdh.array(c) for k, c in self._counters.items()}
            righe = merge(campioni, self.cpus, self._path, servizi)
            for riga in righe:
                extra = dettagli.get(riga["pid"])
                if extra:
                    riga.update({k: extra.get(k) for k in ("ppid", "session", "command", "started", "user", "company", "description",
                                                          "version", "priority")})
            vivi = {r["pid"] for r in righe}
            self._paths = {pid: p for pid, p in self._paths.items() if pid in vivi}  # PIDs are reused: forget the dead ones
        return {"processes": righe, "cpus": self.cpus, "time": time.time(),
                "totals": {"count": len(righe), "threads": sum(r["threads"] for r in righe), "handles": sum(r["handles"] for r in righe),
                           "memory_mb": round(sum(r["memory_mb"] for r in righe), 1)}}


def _powershell(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    codificato = base64.b64encode(("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';" + script)
                                  .encode("utf-16-le")).decode()
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificato],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=timeout)


def load_services() -> List[dict]:
    risultato = _powershell(SERVICES_SCRIPT)
    try:
        dati = json.loads(risultato.stdout.decode("utf-8", "replace") or "[]")
    except ValueError:
        return []
    dati = dati if isinstance(dati, list) else [dati]
    return [{"name": s.get("Name") or "", "display": s.get("DisplayName") or "", "state": s.get("State") or "",
             "start": (s.get("StartMode") or "").lower(), "pid": s.get("ProcessId") or 0, "path": s.get("PathName") or "",
             "description": s.get("Description") or "", "critical": (s.get("Name") or "").lower() in CRITICAL_SERVICES}
            for s in dati if isinstance(s, dict)]


def load_details() -> Dict[int, dict]:
    risultato = _powershell(DETAILS_SCRIPT)
    dati = json.loads(risultato.stdout.decode("utf-8", "replace") or "[]")
    dati = dati if isinstance(dati, list) else [dati]
    return {int(d["pid"]): d for d in dati if isinstance(d, dict) and "pid" in d}


def set_priority(pid: int, priority: str) -> str:
    if priority not in PRIORITIES:
        raise ControlError("Unknown priority.")
    risultato = _powershell(f"$ErrorActionPreference='Stop'; $p = Get-Process -Id {int(pid)}; $p.PriorityClass = '{PRIORITIES[priority]}'; "
                            "\"$($p.ProcessName): $($p.PriorityClass)\"", timeout=30)
    if risultato.returncode != 0:
        errore = risultato.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OSError(errore[0] if errore else f"exit code {risultato.returncode}")
    return risultato.stdout.decode("utf-8", "replace").strip()


def resolve_program(program: str) -> str:
    """An existing executable: a full path, or a name found on PATH (notepad, cmd, regedit…)."""
    import shutil
    testo = (program or "").strip().strip('"')
    if not testo or len(testo) > 260 or any(c in testo for c in '<>|"\r\n'):
        raise ControlError("Enter a program name or the full path of an executable.")
    percorso = testo if os.path.isabs(testo) else shutil.which(testo)
    if not percorso or not os.path.isfile(percorso):
        raise ControlError(f"Program not found: {testo}")
    if os.path.splitext(percorso)[1].lower() not in (".exe", ".com", ".bat", ".cmd", ".msc", ".cpl"):
        raise ControlError("Only programs (.exe, .com, .bat, .cmd, .msc, .cpl) can be started.")
    return percorso


def start_process(program: str, arguments: str, folder: str, elevated: bool) -> dict:
    """Starts a program in its own window. Not elevated: runas /trustlevel drops the administrator rights."""
    percorso = resolve_program(program)
    if len(arguments or "") > 2000 or any(c in (arguments or "") for c in "\r\n\x00"):
        raise ControlError("The arguments are too long or contain line breaks.")
    cartella = (folder or "").strip() or os.path.dirname(percorso)
    if not os.path.isdir(cartella):
        raise ControlError("The working folder does not exist.")
    riga = subprocess.list2cmdline([percorso]) + (" " + arguments if arguments else "")
    if os.path.splitext(percorso)[1].lower() in (".msc", ".cpl"):
        riga = subprocess.list2cmdline(["mmc.exe" if percorso.lower().endswith(".msc") else "control.exe", percorso]) + (" " + arguments if arguments else "")
    if elevated:
        processo = subprocess.Popen(riga, cwd=cartella, creationflags=CREATE_NEW_CONSOLE, stdin=subprocess.DEVNULL)
        return {"pid": processo.pid, "command": riga, "elevated": True}
    subprocess.Popen(["runas", "/trustlevel:0x20000", riga], cwd=cartella, creationflags=CREATE_NEW_CONSOLE, stdin=subprocess.DEVNULL)
    return {"pid": None, "command": riga, "elevated": False}


def check_end_process(rows: List[dict], pid: int, name: str, own_pids: List[int]) -> dict:
    """The row to end, refused when it is critical, the agent itself, or no longer the same process."""
    riga = next((r for r in rows if r["pid"] == pid), None)
    if riga is None:
        raise ControlError("The process has already ended.")
    if riga["name"].lower() != (name or "").lower():
        raise ControlError("The process ID now belongs to another program. Refresh the list.")
    if riga["critical"] or pid in own_pids or pid in (0, 4):
        raise ControlError(f"{riga['name']} is essential to Windows or to this console and cannot be ended.")
    return riga


def end_process(pid: int, tree: bool) -> str:
    comando = ["taskkill", "/PID", str(int(pid)), "/F"] + (["/T"] if tree else [])
    risultato = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=30)
    testo = risultato.stdout.decode("oem", "replace").strip()
    if risultato.returncode != 0:
        raise OSError(testo or f"taskkill exit code {risultato.returncode}")
    return testo


def check_service(services: List[dict], name: str, operation: str) -> dict:
    if operation not in ("start", "stop", "restart"):
        raise ControlError("Unknown operation.")
    if not SERVICE_NAME.match(name or ""):
        raise ControlError("Invalid service name.")
    servizio = next((s for s in services if s["name"].lower() == name.lower()), None)
    if servizio is None:
        raise ControlError("Service not found.")
    if operation != "start" and servizio["critical"]:
        raise ControlError(f"{servizio['display'] or servizio['name']} is essential to Windows and cannot be stopped from here.")
    if operation == "start" and servizio["start"] == "disabled":
        raise ControlError("The service is disabled: change its start type first.")
    return servizio


def control_service(name: str, operation: str) -> str:
    verbo = {"start": "Start-Service", "stop": "Stop-Service -Force", "restart": "Restart-Service -Force"}[operation]
    risultato = _powershell(f"$ErrorActionPreference='Stop'; {verbo} -Name '{name}'; (Get-Service -Name '{name}').Status", timeout=90)
    uscita = risultato.stdout.decode("utf-8", "replace").strip()
    if risultato.returncode != 0:
        errore = risultato.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OSError((errore[0] if errore else "") or uscita or f"exit code {risultato.returncode}")
    return uscita
