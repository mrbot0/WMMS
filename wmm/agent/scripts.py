"""User scripts (.bat / .cmd): a small library stored next to the history, ready-made templates, runs on demand,
schedules in Windows Task Scheduler, and the automatic shutdown timer.

Scheduled scripts run as SYSTEM, so they are registered only when the scripts folder cannot be changed by
standard users (the protected installation), exactly like the scheduled actions."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional
from xml.sax.saxutils import escape

from . import scheduler

EXTENSIONS = (".bat", ".cmd")
MAX_BYTES = 256 * 1024
MAX_OUTPUT = 20000
RUN_TIMEOUT = 3600
TASK_PREFIX = r"WindowsMaintenanceManager\Scripts\Script-"
SCRIPT_ID = re.compile(r"^[0-9a-f]{8}$")
SAFE_TEXT = re.compile(r'^[^"\r\n%&|<>^]*$')  # parameters end up inside a batch file: no quotes, variables or operators
PROCESS_NAME = re.compile(r"^[\w .-]{1,64}\.exe$", re.IGNORECASE)
TIMER_ACTIONS = {"shutdown": "/s", "restart": "/r"}
MAX_TIMER_MINUTES = 7 * 24 * 60
BATCH_ENCODING = "oem"  # cmd.exe reads batch files in the console (OEM) code page, not UTF-8


class ScriptError(ValueError):
    """Bad input or refused operation."""


def _minutes(value, default=30) -> int:
    try:
        numero = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        raise ScriptError("Minutes must be a whole number.") from None
    if not 1 <= numero <= MAX_TIMER_MINUTES:
        raise ScriptError(f"Minutes must be between 1 and {MAX_TIMER_MINUTES} (7 days).")
    return numero


def _text(value, what: str) -> str:
    testo = str(value or "").strip()
    if not testo:
        raise ScriptError(f"{what} is required.")
    if not SAFE_TEXT.match(testo) or len(testo) > 260:
        raise ScriptError(f"{what} cannot contain quotes, %, &, |, <, >, ^ or line breaks.")
    return testo


def _process(value) -> str:
    nome = str(value or "").strip()
    if not PROCESS_NAME.match(nome):
        raise ScriptError("Enter a program name ending in .exe, for example notepad.exe.")
    return nome


def _power(verb: str, flag: str, default: int):
    def body(p):
        minuti = _minutes(p.get("minutes"), default)
        return f'shutdown {flag} /t {minuti * 60} /c "Windows Maintenance Manager: this PC {verb} in {minuti} minute(s)."'
    return body


HEADER = "@echo off\r\nrem Created by Windows Maintenance Manager: {title}\r\n"
TEMPLATES: List[dict] = [
    {"id": "shutdown_in", "title": "Shut down in N minutes", "icon": "power", "group": "Power",
     "description": "Shuts the PC down after the minutes you choose; Windows warns the signed-in user. Cancel the planned shutdown stops it.",
     "params": [{"name": "minutes", "label": "Minutes", "type": "number", "default": 30, "min": 1, "max": MAX_TIMER_MINUTES}],
     "body": _power("shuts down", "/s", 30)},
    {"id": "restart_in", "title": "Restart in N minutes", "icon": "refresh", "group": "Power",
     "description": "Restarts the PC after the minutes you choose, for example at night after updates.",
     "params": [{"name": "minutes", "label": "Minutes", "type": "number", "default": 10, "min": 1, "max": MAX_TIMER_MINUTES}],
     "body": _power("restarts", "/r", 10)},
    {"id": "shutdown_now", "title": "Shut down now", "icon": "power", "group": "Power",
     "description": "Shuts down immediately and closes the open programs (unsaved work is lost). Useful at a fixed time.", "params": [],
     "body": lambda p: "shutdown /s /f /t 0"},
    {"id": "hibernate", "title": "Hibernate", "icon": "moon", "group": "Power",
     "description": "Saves the session to disk and powers off; everything reopens as it was. Needs hibernation turned on.", "params": [],
     "body": lambda p: "shutdown /h"},
    {"id": "sleep", "title": "Sleep", "icon": "moon", "group": "Power",
     "description": "Puts the PC to sleep (hibernates instead when hibernation is on).", "params": [],
     "body": lambda p: "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"},
    {"id": "logoff", "title": "Sign out", "icon": "x", "group": "Power",
     "description": "Signs out the current user and closes their programs.", "params": [], "body": lambda p: "shutdown /l"},
    {"id": "cancel_shutdown", "title": "Cancel the planned shutdown", "icon": "x", "group": "Power",
     "description": "Cancels a shutdown or restart planned with shutdown /t.", "params": [], "body": lambda p: "shutdown /a"},
    {"id": "clean_temp", "title": "Clean temporary files", "icon": "cleanup", "group": "Maintenance",
     "description": "Deletes the files in the temporary folder of the account that runs the script (Windows\\Temp for schedules).", "params": [],
     "body": lambda p: 'del /q /f /s "%TEMP%\\*" >nul 2>&1\r\nfor /d %%d in ("%TEMP%\\*") do rd /s /q "%%d" >nul 2>&1\r\necho Temporary files cleaned.'},
    {"id": "flush_dns", "title": "Flush the DNS cache", "icon": "network", "group": "Maintenance",
     "description": "Clears cached name lookups.", "params": [], "body": lambda p: "ipconfig /flushdns"},
    {"id": "empty_recycle_bin", "title": "Empty the Recycle Bin", "icon": "trash", "group": "Maintenance",
     "description": "Permanently deletes the Recycle Bin of every drive.", "params": [],
     "body": lambda p: 'powershell -NoProfile -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"\r\necho Recycle Bin emptied.'},
    {"id": "sync_time", "title": "Synchronize the clock", "icon": "clock", "group": "Maintenance",
     "description": "Starts Windows Time and resynchronizes with the time server.", "params": [],
     "body": lambda p: "net start w32time >nul 2>&1\r\nw32tm /resync /force"},
    {"id": "backup_folder", "title": "Back up a folder", "icon": "folder", "group": "Files",
     "description": "Copies a folder to another one (disk, USB drive, network share) with robocopy; only new and changed files are copied.",
     "params": [{"name": "source", "label": "Folder to copy", "type": "text", "default": "C:\\Users\\Public\\Documents"},
                {"name": "destination", "label": "Copy to", "type": "text", "default": "D:\\Backup"}],
     "body": lambda p: (f'robocopy "{_text(p.get("source"), "The folder to copy")}" "{_text(p.get("destination"), "The destination")}" /E /R:1 /W:1 /NP /XJ\r\n'
                        "if %errorlevel% geq 8 (echo Backup finished with errors. & exit /b 1)\r\necho Backup completed.")},
    {"id": "close_program", "title": "Close a program", "icon": "x", "group": "Files",
     "description": "Ends a program by name, for example to close an app left open at night.",
     "params": [{"name": "process", "label": "Program", "type": "text", "default": "notepad.exe"}],
     "body": lambda p: f'taskkill /f /im "{_process(p.get("process"))}"'},
]
TEMPLATE_BY_ID = {t["id"]: t for t in TEMPLATES}


def render_template(template_id: str, params: dict) -> str:
    modello = TEMPLATE_BY_ID.get(template_id)
    if modello is None:
        raise ScriptError("Unknown template.")
    return HEADER.format(title=modello["title"]) + modello["body"](params or {}) + "\r\n"


def templates_public() -> List[dict]:
    return [{k: v for k, v in t.items() if k != "body"} for t in TEMPLATES]


def normalize(content) -> str:
    """CRLF line endings (cmd.exe expects them), at most MAX_BYTES, and text only."""
    if not isinstance(content, str):
        raise ScriptError("The script must be text.")
    if "\x00" in content:
        raise ScriptError("The file is not a text batch script.")
    testo = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    if len(testo.encode("utf-8")) > MAX_BYTES:
        raise ScriptError("The script is larger than 256 KB.")
    if not testo.strip():
        raise ScriptError("The script is empty.")
    return testo if testo.endswith("\r\n") else testo + "\r\n"


def task_xml(script_id: str, path: str, schedule: dict) -> str:
    inizio = f"<StartBoundary>{schedule['at']}:00</StartBoundary><Enabled>true</Enabled>"
    if schedule["kind"] == "once":
        trigger = f"<TimeTrigger>{inizio}</TimeTrigger>"
    elif schedule["kind"] == "daily":
        trigger = f"<CalendarTrigger>{inizio}<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"
    else:
        giorni = "".join(f"<{scheduler.WEEKDAYS[g]} />" for g in schedule["days"].split(",") if g)
        trigger = (f"<CalendarTrigger>{inizio}<ScheduleByWeek><DaysOfWeek>{giorni}</DaysOfWeek>"
                   f"<WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>Windows Maintenance Manager</Author><Description>Script {escape(script_id)}</Description></RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>cmd.exe</Command><Arguments>{escape(f'/d /c "{path}"')}</Arguments>
    <WorkingDirectory>{escape(os.path.dirname(path))}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*argomenti: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *argomenti], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)


class ScriptLibrary:
    def __init__(self, folder: Path, unprotected: Callable[[List[str]], List[str]] = scheduler.unprotected_paths):
        self.folder = Path(folder)
        self.index_file = self.folder / "index.json"
        self.unprotected = unprotected
        self._lock = threading.RLock()

    # ---------- storage ----------

    def _load(self) -> List[dict]:
        try:
            dati = json.loads(self.index_file.read_text(encoding="utf-8"))
            return dati if isinstance(dati, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, elenco: List[dict]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        provvisorio = self.index_file.with_suffix(".tmp")
        provvisorio.write_text(json.dumps(elenco, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(provvisorio, self.index_file)

    def path(self, voce: dict) -> Path:
        return self.folder / voce["file"]

    @staticmethod
    def _find(elenco: List[dict], script_id: str) -> dict:
        if not SCRIPT_ID.match(script_id or ""):
            raise ScriptError("Unknown script.")
        voce = next((v for v in elenco if v["id"] == script_id), None)
        if voce is None:
            raise ScriptError("Unknown script.")
        return voce

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(v, size=self.path(v).stat().st_size if self.path(v).exists() else 0) for v in self._load()]

    def get(self, script_id: str) -> dict:
        with self._lock:
            voce = self._find(self._load(), script_id)
            return dict(voce, content=self.path(voce).read_text(encoding=BATCH_ENCODING, errors="replace"))

    def create(self, name: str, content, filename: str = "", template: str = "") -> dict:
        nome = str(name or "").strip()[:80] or (Path(filename).stem if filename else "Script")
        estensione = Path(filename).suffix.lower() if filename else ".bat"
        if estensione not in EXTENSIONS:
            raise ScriptError("Only .bat and .cmd scripts can be added.")
        testo = normalize(content)
        with self._lock:
            elenco = self._load()
            adesso = datetime.now().isoformat(timespec="seconds")
            voce = {"id": secrets.token_hex(4), "name": nome, "file": "", "template": template, "created": adesso, "updated": adesso,
                    "schedule": None, "last_run": None}
            voce["file"] = voce["id"] + estensione
            self.folder.mkdir(parents=True, exist_ok=True)
            self.path(voce).write_text(testo, encoding=BATCH_ENCODING, errors="replace", newline="")
            elenco.append(voce)
            self._save(elenco)
            return voce

    def from_template(self, template_id: str, params: dict, name: str = "") -> dict:
        modello = TEMPLATE_BY_ID.get(template_id)
        if modello is None:
            raise ScriptError("Unknown template.")
        titolo = modello["title"]
        if "N minutes" in titolo:
            titolo = titolo.replace("N minutes", f"{_minutes((params or {}).get('minutes'), modello['params'][0]['default'])} minutes")
        return self.create(name or titolo, render_template(template_id, params), "script.bat", template_id)

    def update(self, script_id: str, name: str, content) -> dict:
        testo = normalize(content)
        with self._lock:
            elenco = self._load()
            voce = self._find(elenco, script_id)
            if name:
                voce["name"] = str(name).strip()[:80]
            voce["updated"] = datetime.now().isoformat(timespec="seconds")
            self.path(voce).write_text(testo, encoding=BATCH_ENCODING, errors="replace", newline="")
            self._save(elenco)
            return voce

    def delete(self, script_id: str) -> None:
        with self._lock:
            elenco = self._load()
            voce = self._find(elenco, script_id)
            if voce.get("schedule"):
                _schtasks("/Delete", "/F", "/TN", TASK_PREFIX + script_id)
            try:
                self.path(voce).unlink()
            except OSError:
                pass
            self._save([v for v in elenco if v["id"] != script_id])

    # ---------- run ----------

    def run(self, script_id: str, on_done: Optional[Callable[[dict], None]] = None) -> dict:
        """Starts the script in the background; its output is kept as last_run."""
        with self._lock:
            elenco = self._load()
            voce = self._find(elenco, script_id)
            if (voce.get("last_run") or {}).get("status") == "running":
                raise ScriptError("The script is already running.")
            voce["last_run"] = {"status": "running", "started": datetime.now().isoformat(timespec="seconds"), "output": "", "exit": None}
            self._save(elenco)
        threading.Thread(target=self._execute, args=(script_id, on_done), name=f"wmm-script-{script_id}", daemon=True).start()
        return voce["last_run"]

    def _execute(self, script_id: str, on_done) -> None:
        voce = self.get(script_id)
        inizio = time.monotonic()
        try:
            processo = subprocess.run(["cmd.exe", "/d", "/c", str(self.path(voce))], cwd=str(self.folder), stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=RUN_TIMEOUT)
            uscita, codice = processo.stdout.decode("oem", "replace"), processo.returncode
        except subprocess.TimeoutExpired:
            uscita, codice = "Stopped after one hour.", -1
        except OSError as errore:
            uscita, codice = str(errore), -1
        esito = {"status": "ok" if codice == 0 else "error", "exit": codice, "output": uscita[-MAX_OUTPUT:],
                 "started": (voce.get("last_run") or {}).get("started"), "finished": datetime.now().isoformat(timespec="seconds"),
                 "seconds": round(time.monotonic() - inizio, 1)}
        with self._lock:
            elenco = self._load()
            for v in elenco:
                if v["id"] == script_id:
                    v["last_run"] = esito
            self._save(elenco)
        if on_done:
            on_done(dict(esito, name=voce["name"]))

    # ---------- schedules ----------

    def schedule(self, script_id: str, kind: str, at: str, days: str = "") -> dict:
        with self._lock:
            elenco = self._load()
            voce = self._find(elenco, script_id)
            piano = {"kind": kind, "at": at, "days": days if kind == "weekly" else ""}
            try:
                scheduler.validate(kind, at, piano["days"])
            except ValueError as errore:
                raise ScriptError(str(errore)) from None
            if self.unprotected([str(self.folder), str(self.path(voce))]):
                raise ScriptError("Scheduled scripts run as SYSTEM, so the scripts folder must not be writable by standard users. "
                                  "Use Settings › This agent › Fix automatically (protected installation) first.")
            descrittore, file = tempfile.mkstemp(suffix=".xml", prefix="wmm-script-")
            try:
                with os.fdopen(descrittore, "w", encoding="utf-16") as uscita:
                    uscita.write(task_xml(script_id, str(self.path(voce)), piano))
                risultato = _schtasks("/Create", "/F", "/TN", TASK_PREFIX + script_id, "/XML", file)
            finally:
                os.remove(file)
            if risultato.returncode != 0:
                raise ScriptError("Task Scheduler refused the schedule: " + risultato.stdout.decode("oem", "replace").strip())
            voce["schedule"] = piano
            self._save(elenco)
            return voce

    def unschedule(self, script_id: str) -> dict:
        with self._lock:
            elenco = self._load()
            voce = self._find(elenco, script_id)
            _schtasks("/Delete", "/F", "/TN", TASK_PREFIX + script_id)
            voce["schedule"] = None
            self._save(elenco)
            return voce


class ShutdownTimer:
    """Shut down or restart in N minutes with shutdown /t: Windows keeps the countdown even if the console closes."""

    def __init__(self, state_file: Path, runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
                 clock: Callable[[], float] = time.time):
        self.state_file = Path(state_file)
        self.runner = runner or (lambda cmd: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=30))
        self.clock = clock

    def status(self) -> dict:
        try:
            stato = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"active": False}
        restante = int(stato.get("due", 0) - self.clock())
        if restante <= 0:
            return {"active": False}
        return {"active": True, "action": stato.get("action"), "due": stato.get("due"), "minutes": stato.get("minutes"), "remaining": restante}

    def start(self, minutes, action: str = "shutdown") -> dict:
        if action not in TIMER_ACTIONS:
            raise ScriptError("Choose shut down or restart.")
        minuti = _minutes(minutes)
        self.runner(["shutdown", "/a"])  # replaces a countdown already running; an error only means there was none
        parola = "shuts down" if action == "shutdown" else "restarts"
        risultato = self.runner(["shutdown", TIMER_ACTIONS[action], "/t", str(minuti * 60),
                                 "/c", f"Windows Maintenance Manager: this PC {parola} in {minuti} minute(s)."])
        if risultato.returncode != 0:
            raise ScriptError("Windows refused the timer: " + risultato.stdout.decode("oem", "replace").strip())
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"action": action, "minutes": minuti, "due": self.clock() + minuti * 60}), encoding="utf-8")
        return self.status()

    def cancel(self) -> dict:
        self.runner(["shutdown", "/a"])
        try:
            self.state_file.unlink()
        except OSError:
            pass
        return {"active": False}
