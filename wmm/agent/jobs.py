"""Runs catalog actions one job at a time, with live log and history records."""
from __future__ import annotations

import msvcrt
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional, Tuple

import wmm  # noqa: F401
import ottimizza_pc as op
from ottimizza_pc import Esito, SequenzaFermata, Stato

from . import actions, undo, verify
from .core import STATUS, JobContext, translate
from .store import Store

op.REGISTRO_PRIMA_DI_SCRIVERE = undo.before_write  # ottimizza_pc's own registry writes join the undo journal

MAX_LOG_LINES = 2000
LIST_LOG_LINES = 6
KEEP_JOBS = 25


class TaskRegistry:
    """Operations that are not catalog actions (scans), so the Activity page can show them."""

    def __init__(self, keep: int = 30):
        self._lock = threading.Lock()
        self._tasks: Dict[str, dict] = {}
        self._keep = keep

    def start(self, kind: str, title: str, total: int) -> str:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._tasks[task_id] = {"id": task_id, "kind": kind, "title": title, "total": total, "done": 0, "current": "",
                                    "active": True, "status": "running", "started": time.time(), "finished": None}
            for vecchio in sorted(self._tasks, key=lambda k: self._tasks[k]["started"])[:-self._keep]:
                if not self._tasks[vecchio]["active"]:
                    del self._tasks[vecchio]
        return task_id

    def step(self, task_id: str, label: str) -> None:
        with self._lock:
            voce = self._tasks.get(task_id)
            if voce:
                voce["done"] = min(voce["total"], voce["done"] + 1)
                voce["current"] = label

    def finish(self, task_id: str, status: str) -> None:
        with self._lock:
            voce = self._tasks.get(task_id)
            if voce:
                voce.update(active=False, status=status, finished=time.time(), current="",
                            done=voce["total"] if status == "ok" else voce["done"])

    def list(self) -> List[dict]:
        with self._lock:
            return sorted((dict(v) for v in self._tasks.values()), key=lambda v: v["started"], reverse=True)


class RunInProgress(Exception):
    """Another job is changing the system."""


class ConfirmationRequired(Exception):
    """A non-safe action was requested without explicit confirmation."""


def free_bytes() -> int:
    try:
        return shutil.disk_usage("C:\\").free
    except OSError:
        return 0


# "45.2%", "45 %": DISM, SFC, CHKDSK, defrag, Defender and winget all print progress like this.
PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")
MAX_ESTIMATE = 0.95


class Job:
    def __init__(self, action_ids: List[str], origin: str, minutes: Optional[List[float]] = None,
                 clock: Callable[[], float] = time.time):
        self.id = uuid.uuid4().hex
        self.action_ids = action_ids
        self.origin = origin
        self.minutes = minutes or [1.0] * len(action_ids)
        self.clock = clock
        self.active = True
        self.current: Optional[str] = None
        self.log: List[str] = []
        self.results: List[dict] = []
        self.started = time.time()
        self.finished: Optional[float] = None
        self.step_percent: Optional[float] = None
        self.step_started = clock()

    def begin_step(self) -> None:
        self.step_percent = None
        self.step_started = self.clock()

    def write(self, riga: str) -> None:
        self.log.append(riga)
        if len(self.log) > MAX_LOG_LINES:
            del self.log[: len(self.log) - MAX_LOG_LINES]
        for valore in reversed(PERCENT.findall(riga)):
            numero = float(valore.replace(",", "."))
            if 0 <= numero <= 100:
                self.step_percent = numero
                break

    def progress(self) -> Tuple[float, Optional[float], bool]:
        """Overall percent, percent of the current step, and whether it is an estimate."""
        fatte, totale = len(self.results), max(1, len(self.action_ids))
        if not self.active or fatte >= totale:
            return (100.0 if fatte >= totale else round(100 * fatte / totale, 1)), None, False
        if self.step_percent is not None:
            frazione, stimata = self.step_percent / 100, False
        else:
            durata = max(1.0, self.minutes[min(fatte, len(self.minutes) - 1)] * 60)
            frazione, stimata = min(MAX_ESTIMATE, (self.clock() - self.step_started) / durata), True
        return round(100 * (fatte + frazione) / totale, 1), self.step_percent, stimata

    def as_dict(self, log_lines: Optional[int] = None) -> dict:
        percento, passo, stimata = self.progress()
        return {
            "id": self.id, "origin": self.origin, "active": self.active, "current": self.current,
            "done": len(self.results), "total": len(self.action_ids), "titles": list(self.action_ids),
            "started": self.started, "finished": self.finished,
            "percent": percento, "step_percent": passo, "estimated": stimata,
            "log": list(self.log if log_lines is None else self.log[-log_lines:]), "results": list(self.results),
        }


class ProcessLock:
    """Lock shared by the GUI agent and scheduled runs, which are separate processes."""

    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        handle = open(self.path, "a+b")
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._file.close()
            self._file = None


class JobManager:
    def __init__(self, store: Store, machine_id: str, preview: bool = False):
        self.store = store
        self.machine_id = machine_id
        self.preview = preview
        self._busy = threading.Lock()
        self._process_lock = ProcessLock(store.path.with_suffix(".lock"))
        self._jobs: Dict[str, Job] = {}
        self.current_id: Optional[str] = None

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def _acquire(self) -> None:
        if not self._busy.acquire(blocking=False):
            raise RunInProgress("A run is already in progress.")
        if not self._process_lock.acquire():
            self._busy.release()
            raise RunInProgress("A scheduled run is already in progress.")

    def _release(self) -> None:
        try:
            self._process_lock.release()
        except OSError:
            pass  # closing the handle drops the lock anyway; never keep the GUI blocked
        finally:
            self._busy.release()

    def recover_interrupted(self) -> int:
        """Marks runs left 'running' by a killed process. Skipped while another process runs."""
        try:
            self._acquire()
        except RunInProgress:
            return 0
        try:
            return self.store.close_stale_runs("Interrupted: the agent stopped before the action finished.")
        finally:
            self._release()

    def _prepare(self, action_ids: List[str], origin: str, confirmed: bool) -> Job:
        if not action_ids:
            raise KeyError("no actions")
        for action_id in action_ids:
            if action_id not in actions.CATALOG:
                raise KeyError(action_id)
        if not confirmed and any(actions.CATALOG[a].risk != "safe" for a in action_ids):
            raise ConfirmationRequired("Confirmation is required for actions that are not safe.")
        self._acquire()
        job = Job(list(action_ids), origin, [self._expected_minutes(a) for a in action_ids])
        self._jobs[job.id] = job
        self.current_id = job.id
        return job

    def _expected_minutes(self, action_id: str) -> float:
        """How long this action took here before, else the catalog estimate."""
        try:
            secondi = self.store.average_seconds(self.machine_id, action_id)
        except sqlite3.Error:
            secondi = None
        return max(0.1, secondi / 60) if secondi else actions.CATALOG[action_id].minutes

    def start(self, action_ids: List[str], origin: str, confirmed: bool) -> str:
        job = self._prepare(action_ids, origin, confirmed)
        threading.Thread(target=self._execute, args=(job,), name=f"wmm-job-{job.id[:8]}", daemon=True).start()
        return job.id

    def run_sync(self, action_ids: List[str], origin: str, confirmed: bool) -> dict:
        job = self._prepare(action_ids, origin, confirmed)
        self._execute(job)
        return job.as_dict()

    def status(self, job_id: str) -> dict:
        return self._jobs[job_id].as_dict()

    def list(self) -> List[dict]:
        """Recent jobs of this agent, newest first, with only the tail of each log."""
        recenti = sorted(self._jobs.values(), key=lambda j: j.started, reverse=True)
        for vecchio in recenti[KEEP_JOBS:]:
            if not vecchio.active:
                self._jobs.pop(vecchio.id, None)
        return [j.as_dict(LIST_LOG_LINES) for j in recenti[:KEEP_JOBS]]

    def _execute(self, job: Job) -> None:
        try:
            ctx = JobContext(job.write, self.preview)
            fermata = ""
            if any(actions.CATALOG[a].risk != "safe" for a in job.action_ids):
                job.current = "restore_point"
                job.write("== Creating a restore point ==")
                try:
                    esito = op.punto_ripristino(ctx)
                    job.write(f"Restore point: {STATUS[esito.stato]} {translate(esito.nota)}".rstrip())
                except SequenzaFermata as motivo:
                    fermata = f"Stopped: {translate(str(motivo))}"
                    job.write(fermata)
                except Exception as errore:  # a broken restore point must never let changes through
                    fermata = f"Stopped: restore point failed ({errore})"
                    job.write(fermata)
            for action_id in job.action_ids:
                try:
                    self._run_action(job, ctx, actions.CATALOG[action_id], fermata)
                except Exception as errore:  # bookkeeping failures must not drop the next actions
                    job.write(f"Unexpected error: {errore!r}")
                    job.results.append({"action_id": action_id, "status": "error", "note": str(errore), "seconds": 0.0, "bytes_freed": 0})
        finally:
            job.current = None
            job.finished = time.time()
            job.active = False
            self._release()

    @staticmethod
    def probe(action_id: str) -> verify.Probe:
        """The before check of a fix (a hook, so tests replace the PowerShell reads)."""
        return verify.Probe(action_id)

    @staticmethod
    def _after_fix(job: Job, controllo, giornale, esito: Esito) -> Tuple[list, Optional[dict]]:
        """What the fix changed in the registry (kept for the undo) and its before/after verdict."""
        modifiche: list = []
        if giornale is not None and giornale.entries:
            try:
                modifiche = undo.changed(giornale.with_current())
            except Exception as errore:  # the fix already ran: a failed read only loses the undo
                job.write(f"Registry values could not be read again ({errore})")
            for voce in modifiche[:10]:
                job.write("  " + undo.describe(voce))
            if modifiche:
                job.write(f"{len(modifiche)} registry values changed: History can put back exactly these (Undo).")
        verifica = None
        if controllo is not None and esito.stato in (Stato.OK, Stato.AVVISO):
            try:
                verifica = controllo.finish(modifiche, len(giornale.entries) if giornale else 0)
            except Exception as errore:
                job.write(f"The after check failed ({errore})")
            if verifica:
                job.write(verify.summary(verifica))
        return modifiche, verifica

    def undo_run(self, run_id: int) -> dict:
        """Puts back the registry values one run changed, nothing else. One change at a time, like any job."""
        dati = self.store.run_undo(run_id)
        if dati is None:
            raise KeyError(run_id)
        if dati["undone"]:
            raise ValueError(f"Already undone on {dati['undone']}.")
        if not dati["entries"]:
            raise ValueError("This run changed no registry value that can be put back.")
        if self.preview:
            return {"restored": 0, "errors": [], "preview": True, "entries": len(dati["entries"])}
        self._acquire()
        try:
            fatti, errori = undo.restore(dati["entries"])
            if fatti:
                self.store.mark_undone(run_id)
        finally:
            self._release()
        return {"restored": fatti, "errors": errori, "entries": len(dati["entries"])}

    def _run_action(self, job: Job, ctx: JobContext, action: actions.Action, fermata: str) -> None:
        job.current = action.id
        job.begin_step()
        try:
            run_id = self.store.open_run(self.machine_id, action.id, job.origin)
        except sqlite3.Error as errore:
            # Without a history record the action must not touch the system.
            nota = f"Not run: history database unavailable ({errore})"
            job.write(f"== {action.title} ==")
            job.write(nota)
            job.results.append({"action_id": action.id, "status": "error", "note": nota, "seconds": 0.0, "bytes_freed": 0})
            return
        inizio_log = len(job.log)
        job.write(f"== {action.title} ==")
        partenza = time.monotonic()
        prima = free_bytes()
        controllo, giornale = None, None
        if fermata:
            esito = Esito(Stato.SALTATO, fermata)
        else:
            if action.kind == "fix" and not self.preview:
                # Read the state the fix should change, and the registry values it declares, before it runs.
                try:
                    controllo = self.probe(action.id)
                except Exception as errore:  # a broken check never stops the fix
                    job.write(f"The before check failed ({errore})")
                giornale = undo.begin()
                undo.declare(action.id, giornale)
            try:
                esito = action.run(ctx)
            except SequenzaFermata as motivo:
                esito = Esito(Stato.ERRORE, str(motivo))
            except subprocess.TimeoutExpired:
                esito = Esito(Stato.ERRORE, "timed out")
            except Exception as errore:  # one failing action must not stop the others
                esito = Esito(Stato.ERRORE, f"{type(errore).__name__}: {errore}")
            finally:
                if giornale is not None:
                    undo.end()
        liberati = max(0, free_bytes() - prima) if esito.stato is Stato.OK else 0
        esito.nota = translate(esito.nota)
        stato = STATUS[esito.stato]
        job.write(f"Result: {stato} {esito.nota}".rstrip())
        modifiche, verifica = self._after_fix(job, controllo, giornale, esito)
        risultato = {"action_id": action.id, "status": stato, "note": esito.nota,
                     "seconds": round(time.monotonic() - partenza, 1), "bytes_freed": liberati, "run_id": run_id,
                     "verify": verifica, "undo_count": len(modifiche)}
        job.results.append(risultato)
        try:
            self.store.close_run(run_id, stato, esito.nota, liberati, "\n".join(job.log[inizio_log:]), verifica, modifiche)
        except sqlite3.Error as errore:
            job.write(f"Warning: the result could not be saved to history ({errore})")
