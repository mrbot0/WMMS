"""The agent in the background (2.10): a Windows Task Scheduler task that starts the agent as SYSTEM at boot, without
a window and without a signed-in user, restarts it every minute if it stops (up to 999 times), and never ends it for
running too long. It works like a Windows service without extra packages. The background agent runs the central
server client, the alert escalation and the watchers; the console in the browser connects to it as usual."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK = r"\Windows Maintenance Manager\Background agent"


def task_xml(python: str, script: str, port: int) -> str:
    argomenti = escape(f'-I "{script}" --background --port {int(port)}')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>Windows Maintenance Manager</Author>
    <Description>Runs the Windows Maintenance Manager agent in the background, as SYSTEM, from boot.</Description>
  </RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Hidden>true</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>{argomenti}</Arguments>
      <WorkingDirectory>{escape(os.path.dirname(script))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*argomenti: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *argomenti], capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def status() -> dict:
    r = _schtasks("/Query", "/TN", TASK, "/FO", "LIST", "/V")
    if r.returncode != 0:
        return {"installed": False, "running": False, "last_result": None}
    campi = {}
    for riga in r.stdout.splitlines():
        if ":" in riga:
            k, v = riga.split(":", 1)
            campi[k.strip().lower()] = v.strip()
    stato = next((v for k, v in campi.items() if k in ("status", "stato")), "")
    return {"installed": True, "running": stato.lower() in ("running", "in esecuzione"), "status": stato,
            "last_result": next((v for k, v in campi.items() if "last result" in k or "ultimo risultato" in k), None)}


def install(python: str, script: str, port: int) -> dict:
    """Needs administrator rights and the protected installation (Program Files), like the schedules."""
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(task_xml(python, script, port))
        percorso = f.name
    try:
        r = _schtasks("/Create", "/TN", TASK, "/XML", percorso, "/F")
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout).strip()[-300:] or "Task Scheduler refused the task")
        _schtasks("/Run", "/TN", TASK)
    finally:
        Path(percorso).unlink(missing_ok=True)
    return status()


def uninstall() -> dict:
    _schtasks("/End", "/TN", TASK)
    r = _schtasks("/Delete", "/TN", TASK, "/F")
    if r.returncode != 0 and "cannot find" not in (r.stderr or "").lower() and "impossibile trovare" not in (r.stderr or "").lower():
        raise OSError((r.stderr or r.stdout).strip()[-300:])
    return status()
