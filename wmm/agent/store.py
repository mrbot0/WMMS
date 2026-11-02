"""SQLite history: scans, runs and schedules. Every record carries machine_id."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL, area TEXT NOT NULL, created TEXT NOT NULL,
    score INTEGER NOT NULL, data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scans_area ON scans (machine_id, area, id);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL, action_id TEXT NOT NULL, area TEXT NOT NULL,
    origin TEXT NOT NULL, started TEXT NOT NULL, finished TEXT,
    status TEXT NOT NULL DEFAULT 'running', note TEXT NOT NULL DEFAULT '',
    bytes_freed INTEGER NOT NULL DEFAULT 0, log TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS runs_machine ON runs (machine_id, id);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL, kind TEXT NOT NULL, at TEXT NOT NULL,
    days TEXT NOT NULL DEFAULT '', confirmed INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL,
    last_status TEXT, last_run TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

SETTINGS_DEFAULTS = {"technician": "", "company": "", "report_header": "", "report_footer": "", "notes": "",
                     "restore_on_start": "1"}
SETTINGS_MAX_LENGTH = 500
NOTES_MAX_LENGTH = 4000
FLAG_SETTINGS = {"restore_on_start"}  # "1" on, "0" off

RUN_FIELDS = "id, machine_id, action_id, area, origin, started, finished, status, note, bytes_freed"
SCHEDULE_FIELDS = {"action_id", "kind", "at", "days", "confirmed", "enabled", "last_status", "last_run"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            finally:
                db.close()

    # ---------- scans ----------

    def save_scan(self, machine_id: str, area: str, score: int, data: dict) -> int:
        with self._db() as db:
            cursore = db.execute(
                "INSERT INTO scans (machine_id, area, created, score, data_json) VALUES (?, ?, ?, ?, ?)",
                (machine_id, area, now(), int(score), json.dumps(data, ensure_ascii=False)),
            )
            return int(cursore.lastrowid)

    def last_scan(self, machine_id: str, area: str) -> Optional[dict]:
        with self._db() as db:
            riga = db.execute(
                "SELECT id, area, created, score, data_json FROM scans WHERE machine_id = ? AND area = ? ORDER BY id DESC LIMIT 1",
                (machine_id, area),
            ).fetchone()
        if riga is None:
            return None
        return {"id": riga["id"], "area": riga["area"], "created": riga["created"], "score": riga["score"], "data": json.loads(riga["data_json"])}

    def trend(self, machine_id: str, area: str, limit: int = 30) -> List[dict]:
        with self._db() as db:
            righe = db.execute(
                "SELECT created, score FROM scans WHERE machine_id = ? AND area = ? ORDER BY id DESC LIMIT ?",
                (machine_id, area, limit),
            ).fetchall()
        return [dict(riga) for riga in reversed(righe)]

    # ---------- runs ----------

    def open_run(self, machine_id: str, action_id: str, origin: str) -> int:
        with self._db() as db:
            cursore = db.execute(
                "INSERT INTO runs (machine_id, action_id, area, origin, started) VALUES (?, ?, ?, ?, ?)",
                (machine_id, action_id, action_id.split(".")[0], origin, now()),
            )
            return int(cursore.lastrowid)

    def close_run(self, run_id: int, status: str, note: str, bytes_freed: int, log: str) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE runs SET finished = ?, status = ?, note = ?, bytes_freed = ?, log = ? WHERE id = ?",
                (now(), status, note, int(bytes_freed), log, run_id),
            )

    def close_stale_runs(self, note: str) -> int:
        with self._db() as db:
            cursore = db.execute("UPDATE runs SET status = 'error', note = ?, finished = ? WHERE status = 'running'", (note, now()))
            return cursore.rowcount

    def runs(self, machine_id: str, area: Optional[str] = None, limit: int = 100) -> List[dict]:
        query = f"SELECT {RUN_FIELDS} FROM runs WHERE machine_id = ?"
        parametri: list = [machine_id]
        if area:
            query += " AND area = ?"
            parametri.append(area)
        query += " ORDER BY id DESC LIMIT ?"
        parametri.append(limit)
        with self._db() as db:
            return [dict(riga) for riga in db.execute(query, parametri).fetchall()]

    def average_seconds(self, machine_id: str, action_id: str, last: int = 5) -> Optional[float]:
        """Average duration of the latest completed runs of an action (for progress estimates)."""
        with self._db() as db:
            righe = db.execute(
                "SELECT started, finished FROM runs WHERE machine_id = ? AND action_id = ? AND status IN ('ok', 'warning', 'preview') "
                "AND finished IS NOT NULL ORDER BY id DESC LIMIT ?", (machine_id, action_id, last)).fetchall()
        durate = []
        for riga in righe:
            try:
                durate.append((datetime.fromisoformat(riga["finished"]) - datetime.fromisoformat(riga["started"])).total_seconds())
            except (TypeError, ValueError):
                continue
        return round(sum(durate) / len(durate), 1) if durate else None

    def run_log(self, run_id: int) -> Optional[str]:
        with self._db() as db:
            riga = db.execute("SELECT log FROM runs WHERE id = ?", (run_id,)).fetchone()
        return None if riga is None else riga["log"]

    def last_runs_by_action(self, machine_id: str) -> Dict[str, dict]:
        with self._db() as db:
            righe = db.execute(
                f"SELECT {RUN_FIELDS} FROM runs WHERE id IN (SELECT MAX(id) FROM runs WHERE machine_id = ? GROUP BY action_id)",
                (machine_id,),
            ).fetchall()
        return {riga["action_id"]: dict(riga) for riga in righe}

    # ---------- schedules ----------

    def create_schedule(self, action_id: str, kind: str, at: str, days: str, confirmed: bool) -> int:
        with self._db() as db:
            cursore = db.execute(
                "INSERT INTO schedules (action_id, kind, at, days, confirmed, created) VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, kind, at, days, int(confirmed), now()),
            )
            return int(cursore.lastrowid)

    @staticmethod
    def _schedule(riga: sqlite3.Row) -> dict:
        dati = dict(riga)
        dati["confirmed"] = bool(dati["confirmed"])
        dati["enabled"] = bool(dati["enabled"])
        return dati

    def schedules(self) -> List[dict]:
        with self._db() as db:
            return [self._schedule(riga) for riga in db.execute("SELECT * FROM schedules ORDER BY id").fetchall()]

    def schedule(self, schedule_id: int) -> Optional[dict]:
        with self._db() as db:
            riga = db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        return None if riga is None else self._schedule(riga)

    def update_schedule(self, schedule_id: int, **fields) -> None:
        sconosciuti = set(fields) - SCHEDULE_FIELDS
        if sconosciuti:
            raise ValueError(f"Unknown schedule fields: {sorted(sconosciuti)}")
        if not fields:
            return
        valori = [int(v) if isinstance(v, bool) else v for v in fields.values()]
        assegnazioni = ", ".join(f"{nome} = ?" for nome in fields)
        with self._db() as db:
            db.execute(f"UPDATE schedules SET {assegnazioni} WHERE id = ?", (*valori, schedule_id))

    # ---------- settings ----------

    def settings(self) -> Dict[str, str]:
        with self._db() as db:
            salvati = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM settings").fetchall()}
        return {chiave: salvati.get(chiave, predefinito) for chiave, predefinito in SETTINGS_DEFAULTS.items()}

    def save_settings(self, values: Dict[str, str]) -> None:
        sconosciute = set(values) - set(SETTINGS_DEFAULTS)
        if sconosciute:
            raise ValueError(f"Unknown settings: {', '.join(sorted(sconosciute))}")
        for chiave, valore in values.items():
            massimo = NOTES_MAX_LENGTH if chiave == "notes" else SETTINGS_MAX_LENGTH
            if not isinstance(valore, str) or len(valore) > massimo:
                raise ValueError(f"{chiave} must be text of at most {massimo} characters")
            if chiave in FLAG_SETTINGS and valore not in ("0", "1"):
                raise ValueError(f"{chiave} must be \"0\" or \"1\"")
        with self._db() as db:
            db.executemany("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                           [(k, v.strip()) for k, v in values.items()])

    def delete_schedule(self, schedule_id: int) -> None:
        with self._db() as db:
            db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
