"""Start the console when the technician signs in to Windows.

A Task Scheduler task for the signed-in user with the highest rights: the console starts as
administrator without a UAC prompt. That is only safe when standard users cannot change the
program or Python, so the task needs the same protected installation as the schedules."""
from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
from xml.sax.saxutils import escape

from . import scheduler

TASK = scheduler.FOLDER + "WMM-Autostart"
DELAY = "PT30S"  # let the desktop and the network come up first


def current_user_sid() -> str:
    risultato = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, timeout=30)
    righe = list(csv.reader(io.StringIO(scheduler._text(risultato.stdout).strip())))
    sid = righe[0][-1] if righe and righe[0] else ""
    if not sid.startswith("S-1-"):
        raise RuntimeError("The account of the signed-in user could not be read.")
    return sid


def windowless(python: str) -> str:
    """pythonw.exe from the same folder: the console starts at sign-in without any window."""
    candidato = os.path.join(os.path.dirname(python), "pythonw.exe")
    return candidato if os.path.isfile(candidato) else python


def task_xml(sid: str, python: str, script: str, port: int) -> str:
    # --hidden: no console window (output in dati\wmm-console.log); the console opens in the default browser.
    python = windowless(python)
    argomenti = escape(f'-I "{script}" --hidden --port {int(port)}')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>Windows Maintenance Manager</Author>
    <Description>Starts the Windows Maintenance Manager console when this user signs in.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{escape(sid)}</UserId><Delay>{DELAY}</Delay></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{escape(sid)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
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


def is_enabled() -> bool:
    return scheduler._schtasks("/Query", "/TN", TASK).returncode == 0


def enable(python: str, script: str, port: int) -> None:
    scheduler.ensure_protected(python, script)
    xml = task_xml(current_user_sid(), python, script, port)
    descrittore, percorso = tempfile.mkstemp(suffix=".xml", prefix="wmm-autostart-")
    try:
        with os.fdopen(descrittore, "w", encoding="utf-16") as file:
            file.write(xml)
        risultato = scheduler._schtasks("/Create", "/F", "/TN", TASK, "/XML", percorso)
    finally:
        os.remove(percorso)
    if risultato.returncode != 0:
        raise RuntimeError(scheduler._text(risultato.stdout).strip() or f"schtasks exit code {risultato.returncode}")


def disable() -> None:
    if is_enabled():
        risultato = scheduler._schtasks("/Delete", "/F", "/TN", TASK)
        if risultato.returncode != 0:
            raise RuntimeError(scheduler._text(risultato.stdout).strip() or f"schtasks exit code {risultato.returncode}")
