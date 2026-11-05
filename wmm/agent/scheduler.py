"""Schedules registered in Windows Task Scheduler, so they run with the program closed."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from .jobs import RunInProgress
from .store import Store, now

FOLDER = "\\WindowsMaintenanceManager\\"
KINDS = ("once", "daily", "weekly", "monthly", "startup", "logon")
EVENT_KINDS = ("startup", "logon")  # fire on an event, not at a time: `at` is only the date they become active
MAX_DELAY_MINUTES = 60
MAX_MONTH_DAY = 28  # every month has it, so a monthly schedule never skips a month
WEEKDAYS = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday",
            "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday"}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
BUSY_RETRIES = 60
BUSY_WAIT_SECONDS = 30


def task_name(schedule_id: int) -> str:
    return f"{FOLDER}WMM-{schedule_id}"


AT_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def validate(kind: str, at: str, days: str, delay=0) -> None:
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError(f"Unknown schedule type: {kind}")
    if not isinstance(days, str):
        raise ValueError("Days must be text such as MON,WED.")
    try:
        if not isinstance(at, str) or not AT_FORMAT.fullmatch(at):
            raise ValueError
        inizio = datetime.strptime(at, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("The start must have the format YYYY-MM-DDTHH:MM.") from None
    if kind == "weekly":
        giorni = [g for g in days.split(",") if g]
        if not giorni or any(g not in WEEKDAYS for g in giorni):
            raise ValueError("Weekly schedules need at least one day among MON, TUE, WED, THU, FRI, SAT, SUN.")
    if kind == "monthly" and inizio.day > MAX_MONTH_DAY:
        raise ValueError(f"Monthly schedules run on a day from 1 to {MAX_MONTH_DAY}, so no month is skipped.")
    if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= MAX_DELAY_MINUTES:
        raise ValueError(f"The delay must be a whole number of minutes from 0 to {MAX_DELAY_MINUTES}.")


def trigger_xml(schedule: dict) -> str:
    """The <Triggers> content for a schedule (actions and scripts share it)."""
    inizio = f"<StartBoundary>{schedule['at']}:00</StartBoundary><Enabled>true</Enabled>"
    tipo = schedule["kind"]
    if tipo in EVENT_KINDS:
        ritardo = int(schedule.get("delay") or 0)
        attesa = f"<Delay>PT{ritardo}M</Delay>" if ritardo else ""
        # No UserId in the logon trigger: it fires when any user signs in.
        return f"<BootTrigger>{inizio}{attesa}</BootTrigger>" if tipo == "startup" else f"<LogonTrigger>{inizio}{attesa}</LogonTrigger>"
    if tipo == "once":
        return f"<TimeTrigger>{inizio}</TimeTrigger>"
    if tipo == "daily":
        return f"<CalendarTrigger>{inizio}<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"
    if tipo == "monthly":
        giorno = int(schedule["at"][8:10])
        mesi = "".join(f"<{m} />" for m in MONTHS)
        return (f"<CalendarTrigger>{inizio}<ScheduleByMonth><DaysOfMonth><Day>{giorno}</Day></DaysOfMonth>"
                f"<Months>{mesi}</Months></ScheduleByMonth></CalendarTrigger>")
    giorni = "".join(f"<{WEEKDAYS[g]} />" for g in schedule["days"].split(",") if g)
    return (f"<CalendarTrigger>{inizio}<ScheduleByWeek><DaysOfWeek>{giorni}</DaysOfWeek>"
            f"<WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>")


def task_xml(schedule: dict, python: str, script: str) -> str:
    validate(schedule["kind"], schedule["at"], schedule.get("days") or "", int(schedule.get("delay") or 0))
    trigger = trigger_xml(schedule)
    abilitato = "true" if schedule.get("enabled", True) else "false"
    # -I: ignore PYTHONPATH and user site-packages in the SYSTEM process.
    argomenti = escape(f'-I "{script}" --run-schedule {schedule["id"]}')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>Windows Maintenance Manager</Author>
    <Description>Windows Maintenance Manager scheduled action {escape(schedule['action_id'])}</Description>
  </RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals>
    <Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Enabled>{abilitato}</Enabled>
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
    return subprocess.run(["schtasks", *argomenti], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, timeout=60)


def _text(dati: bytes) -> str:
    if dati[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in dati[:200]:
        return dati.decode("utf-16", "replace")
    return dati.decode(f"cp{ctypes.windll.kernel32.GetOEMCP()}", "replace")


class UnprotectedProgram(RuntimeError):
    """The code a SYSTEM task would run can be changed by standard users."""


NON_ADMIN_SIDS = {
    "S-1-1-0",        # Everyone
    "S-1-5-4",        # Interactive
    "S-1-5-11",       # Authenticated Users
    "S-1-5-32-545",   # Users
    "S-1-5-32-547",   # Power Users
}
WRITE_RIGHTS = ("FullControl", "Modify", "Write", "CreateFiles", "AppendData", "CreateDirectories",
                "ChangePermissions", "TakeOwnership")
WRITE_MASK = 0x10000000 | 0x40000000 | 0x2 | 0x4 | 0x40000 | 0x80000  # GENERIC_ALL/WRITE, write data/append, WRITE_DAC/OWNER


def writable_by_non_admins(entries: List[dict], owner_sid: str, user_sid: str) -> bool:
    """True when a standard user (or this user's unelevated processes) can change the file."""
    if owner_sid == user_sid or owner_sid in NON_ADMIN_SIDS:
        return True
    for voce in entries:
        if voce.get("type") != "Allow" or voce.get("sid") not in NON_ADMIN_SIDS | {user_sid}:
            continue
        diritti = str(voce.get("rights", ""))
        if diritti.strip().lstrip("-").isdigit():
            if int(diritti) & WRITE_MASK:
                return True
        elif any(nome in [d.strip() for d in diritti.split(",")] for nome in WRITE_RIGHTS):
            return True
    return False


SCRIPT_ACL = r"""
$user = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$sid = [Security.Principal.SecurityIdentifier]
[ordered]@{
  user = $user
  paths = @(foreach ($p in $args_paths) {
    $acl = Get-Acl -LiteralPath $p
    [ordered]@{
      path = $p
      owner = if ($acl) { $acl.GetOwner($sid).Value } else { '' }
      entries = @(if ($acl) { $acl.GetAccessRules($true, $true, $sid) | ForEach-Object {
        [ordered]@{ sid = $_.IdentityReference.Value; rights = "$($_.FileSystemRights)"; type = "$($_.AccessControlType)" } } })
    }
  })
} | ConvertTo-Json -Depth 5 -Compress
"""


def program_paths(script: str) -> List[str]:
    """The program files a SYSTEM task loads."""
    radice = os.path.dirname(os.path.abspath(script))
    obiettivi = [radice, script, os.path.join(radice, "ottimizza_pc.py"), os.path.join(radice, "dati")]
    for cartella, sottocartelle, file in os.walk(os.path.join(radice, "wmm")):
        sottocartelle[:] = [s for s in sottocartelle if s not in ("__pycache__", "web")]
        obiettivi.append(cartella)
        obiettivi += [os.path.join(cartella, f) for f in file if f.endswith(".py")]
    return [p for p in obiettivi if os.path.exists(p)]


def python_paths(python: str) -> List[str]:
    base = os.path.dirname(os.path.abspath(python))
    return [p for p in (python, base, os.path.join(base, "Lib"), os.path.join(base, "DLLs")) if os.path.exists(p)]


def protected_targets(python: str, script: str) -> List[str]:
    """Everything the SYSTEM task loads: the program, its package and the Python install."""
    return program_paths(script) + python_paths(python)


def unprotected_paths(paths: List[str]) -> List[str]:
    lista = "@(" + ",".join("'" + p.replace("'", "''") + "'" for p in paths) + ")"
    try:
        dati = json.loads(_powershell(f"$args_paths = {lista}\n" + SCRIPT_ACL) or "null")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        dati = None
    if not isinstance(dati, dict):
        return list(paths)  # fail closed: without ACLs we cannot prove the code is safe
    voci = dati.get("paths") or []
    voci = voci if isinstance(voci, list) else [voci]
    letti = {v.get("path"): v for v in voci if isinstance(v, dict)}
    risultato = []
    for percorso in paths:
        voce = letti.get(percorso)
        elenco = (voce or {}).get("entries") or []
        elenco = elenco if isinstance(elenco, list) else [elenco]
        if voce is None or not voce.get("owner") or writable_by_non_admins(elenco, voce["owner"], dati.get("user", "")):
            risultato.append(percorso)
    return risultato


def _powershell(script: str) -> str:
    codificato = base64.b64encode(("[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script).encode("utf-16-le")).decode()
    risultato = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificato],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=120)
    return risultato.stdout.decode("utf-8", "replace").strip()


def ensure_protected(python: str, script: str) -> None:
    aperti = unprotected_paths(protected_targets(python, script))
    if aperti:
        esempi = ", ".join(aperti[:4]) + (f" and {len(aperti) - 4} more" if len(aperti) > 4 else "")
        raise UnprotectedProgram(
            "Scheduled actions run as SYSTEM, so the program and Python must not be writable by standard users. "
            f"Writable paths: {esempi}. Install the suite with `python wmm.py --install` (it copies it to "
            r"C:\Program Files\WindowsMaintenanceManager), use a Python installed for all users, and start the console from there.")


def register(schedule: dict, python: str, script: str) -> None:
    xml = task_xml(schedule, python, script)
    ensure_protected(python, script)
    descrittore, percorso = tempfile.mkstemp(suffix=".xml", prefix="wmm-task-")
    try:
        with os.fdopen(descrittore, "w", encoding="utf-16") as file:
            file.write(xml)
        risultato = _schtasks("/Create", "/F", "/TN", task_name(schedule["id"]), "/XML", percorso)
    finally:
        os.remove(percorso)
    if risultato.returncode != 0:
        raise RuntimeError(_text(risultato.stdout).strip() or f"schtasks exit code {risultato.returncode}")


def unregister(schedule_id: int) -> None:
    _schtasks("/Delete", "/F", "/TN", task_name(schedule_id))


def set_enabled(schedule_id: int, enabled: bool) -> None:
    risultato = _schtasks("/Change", "/TN", task_name(schedule_id), "/ENABLE" if enabled else "/DISABLE")
    if risultato.returncode != 0:
        raise RuntimeError(_text(risultato.stdout).strip())


def sync_state(schedules: List[dict], script: str) -> Dict[int, str]:
    stati: Dict[int, str] = {}
    for schedule in schedules:
        risultato = _schtasks("/Query", "/TN", task_name(schedule["id"]), "/XML")
        if risultato.returncode != 0:
            stati[schedule["id"]] = "missing"
        elif os.path.normcase(script) not in os.path.normcase(_text(risultato.stdout)):
            stati[schedule["id"]] = "path_changed"
        else:
            stati[schedule["id"]] = "ok"
    return stati


# What Task Scheduler and wmm.py --run-schedule report as "last result", in words.
RESULT_TEXT = {
    0: ("ok", "Completed"),
    1: ("error", "Finished with errors (see History)"),
    2: ("error", "The schedule no longer exists in the console"),
    0x41300: ("ok", "Ready to run"),
    0x41301: ("running", "Running now"),
    0x41302: ("warning", "Disabled"),
    0x41303: ("skipped", "Has not run yet"),
    0x41304: ("skipped", "No more runs planned"),
    0x41306: ("error", "Stopped by Task Scheduler (time limit or user)"),
    0x8004131F: ("warning", "Skipped: the previous run was still going"),
    0x800710E0: ("warning", "Refused by Windows (conditions not met, for example on battery)"),
    0x80070002: ("error", "Python or the program was not found (moved or uninstalled)"),
    0x80070005: ("error", "Access denied"),
    0xC000013A: ("warning", "Interrupted (the PC was shutting down)"),
}

SCRIPT_TASK_STATUS = r"""
$out = @(Get-ScheduledTask -TaskPath '\WindowsMaintenanceManager\' -ErrorAction SilentlyContinue | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  [ordered]@{ name = $_.TaskName; state = "$($_.State)"; result = [int64]$i.LastTaskResult
    last = if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') } else { '' }
    next = if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { '' } } })
ConvertTo-Json -InputObject $out -Compress
"""


def result_text(code) -> Tuple[str, str]:
    """(tone, words) for a Task Scheduler last-result code."""
    try:
        code = int(code) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return ("skipped", "Unknown")
    return RESULT_TEXT.get(code, ("error", f"Failed with code 0x{code:X}"))


def task_status() -> Dict[str, dict]:
    """Every task of the WindowsMaintenanceManager folder with Task Scheduler's own view: state, last run, last result, next run.
    One PowerShell call for all of them; an empty dict when Task Scheduler cannot be read."""
    try:
        dati = json.loads(_powershell(SCRIPT_TASK_STATUS) or "[]")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return {}
    voci = dati if isinstance(dati, list) else [dati]
    stati = {}
    for v in voci:
        if not isinstance(v, dict) or not v.get("name"):
            continue
        tono, testo = result_text(v.get("result"))
        if v.get("result") == 0x41303 or not v.get("last"):
            tono, testo = "skipped", "Has not run yet"
        stati[v["name"]] = {"state": v.get("state", ""), "last": v.get("last") or None, "next": v.get("next") or None,
                            "result": v.get("result"), "result_tone": tono, "result_text": testo}
    return stati


def run_task_now(schedule_id: int) -> None:
    """Starts the Task Scheduler task at once, as SYSTEM: the real test that a schedule works."""
    risultato = _schtasks("/Run", "/TN", task_name(schedule_id))
    if risultato.returncode != 0:
        raise RuntimeError(_text(risultato.stdout).strip() or f"schtasks exit code {risultato.returncode}")


def next_run(schedule: dict, ref: datetime) -> Optional[str]:
    """Next start after `ref`, as ISO text; None when the schedule will not run again."""
    if not schedule.get("enabled"):
        return None
    try:
        inizio = datetime.strptime(schedule["at"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError):
        return None
    if schedule["kind"] == "once":
        return inizio.isoformat(timespec="minutes") if inizio > ref else None
    if schedule["kind"] in EVENT_KINDS:
        return None  # depends on when Windows starts or someone signs in
    if schedule["kind"] == "monthly":
        anno, mese = ref.year, ref.month
        for _ in range(13):
            candidato = inizio.replace(year=anno, month=mese)
            if candidato > ref and candidato >= inizio:
                return candidato.isoformat(timespec="minutes")
            anno, mese = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
        return None
    giorni = None
    if schedule["kind"] == "weekly":
        nomi = list(WEEKDAYS)
        giorni = {nomi.index(g) for g in (schedule.get("days") or "").split(",") if g in WEEKDAYS}
        if not giorni:
            return None
    base = max(ref, inizio - timedelta(minutes=1))
    for offset in range(0, 8):
        candidato = datetime.combine(base.date() + timedelta(days=offset), inizio.time())
        if candidato > ref and candidato >= inizio and (giorni is None or candidato.weekday() in giorni):
            return candidato.isoformat(timespec="minutes")
    return None


def run_schedule(schedule_id: int, store: Store, jobs) -> int:
    """Entry point of `wmm.py --run-schedule ID`. Returns the process exit code."""
    schedule = store.schedule(schedule_id)
    if schedule is None:
        return 2
    if not schedule["enabled"]:
        return 0
    from . import routines
    try:
        da_eseguire = routines.expand(schedule["action_id"])
    except KeyError:
        store.update_schedule(schedule_id, last_status="error", last_run=now())
        return 2
    # Settings › Runs (2.9): fixes run only inside the maintenance window and never high-risk ones when they are blocked;
    # read-only reports always run.
    from . import actions as _azioni, appsettings
    regole = appsettings.load(store.path.parent)
    fuori = not appsettings.in_window(regole["maint_window"])
    tenuti = [a for a in da_eseguire if _azioni.CATALOG[a].kind == "report" or not (fuori or (regole["block_high_risk"] and _azioni.CATALOG[a].risk == "high"))]
    if not tenuti:
        store.update_schedule(schedule_id, last_status="skipped", last_run=now())
        return 0
    da_eseguire = tenuti
    for tentativo in range(BUSY_RETRIES + 1):
        try:
            stato = jobs.run_sync(da_eseguire, "schedule", confirmed=schedule["confirmed"])
            break
        except RunInProgress:
            if tentativo == BUSY_RETRIES:
                store.update_schedule(schedule_id, last_status="skipped", last_run=now())
                return 1
            time.sleep(BUSY_WAIT_SECONDS)
    esiti = [r["status"] for r in stato["results"]]
    finale = "error" if "error" in esiti else ("warning" if "warning" in esiti else (esiti[0] if esiti else "error"))
    campi = {"last_status": finale, "last_run": now()}
    if schedule["kind"] == "once":
        campi["enabled"] = False
    store.update_schedule(schedule_id, **campi)
    if finale == "error":
        from . import notify
        falliti = [f"- {r['action_id']}: {r.get('note') or 'error'}" for r in stato["results"] if r["status"] == "error"]
        notify.safe_event(store.path.parent, "run_failed", f"Schedule #{schedule_id} ({schedule['action_id']}) ended with errors:\n" +
                          "\n".join(falliti[:10]) + "\n\nSee History in the console for the full log.", gruppo=str(schedule_id))
    return 1 if finale == "error" else 0
