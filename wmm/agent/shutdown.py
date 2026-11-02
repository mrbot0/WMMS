"""Stop every Windows Maintenance Manager process on this PC: other consoles, scheduled runs and
the commands they started (DISM, CHKDSK...). Used by the power button of an administrator console."""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import List

from . import scheduler

# wmm.py as a separate word of the command line: "...\wmm.py", "wmm.py --preview", 'C:\x\wmm.py"'.
WMM_SCRIPT = re.compile(r'(?:^|[\s"\'\\/])wmm\.py(?:["\'\s]|$)', re.IGNORECASE)
SCRIPT_PROCESSES = (
    "@(Get-CimInstance Win32_Process -Filter \"Name like 'py%'\" | ForEach-Object { "
    "[ordered]@{ pid = [int]$_.ProcessId; command = [string]$_.CommandLine } }) | ConvertTo-Json -Compress"
)


def is_wmm(command_line: str) -> bool:
    return bool(command_line) and bool(WMM_SCRIPT.search(command_line))


def wmm_processes(own_pid: int) -> List[dict]:
    """Python processes running wmm.py, except this one."""
    try:
        dati = json.loads(scheduler._powershell(SCRIPT_PROCESSES) or "[]")
    except (ValueError, OSError, subprocess.SubprocessError):
        return []
    dati = dati if isinstance(dati, list) else [dati]
    return [p for p in dati if isinstance(p, dict) and p.get("pid") != own_pid and is_wmm(p.get("command") or "")]


def kill_tree(pid: int) -> bool:
    """Ends a process and every process it started."""
    risultato = subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=30)
    return risultato.returncode == 0


def stop_others(own_pid: int) -> List[int]:
    """Stops the other WMM processes; returns the ids that were stopped."""
    return [p["pid"] for p in wmm_processes(own_pid) if kill_tree(p["pid"])]


def stop_self() -> None:
    """Ends this process with its children (a run in progress included). Never returns."""
    try:
        kill_tree(os.getpid())
    finally:
        os._exit(0)
