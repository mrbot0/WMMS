"""Versioned database migrations (2.11). Every database of the app (wmm.db, accounts.db, central.db) keeps its schema
version in PRAGMA user_version; the steps of a database are a list, step n brings version n-1 to n. Before a database
written by an older version is changed, a copy goes to dati\\db-backups (the last 5 per database are kept), and the
steps run in one transaction: if one fails nothing is changed and the copy stays. A database written by a newer version
of the app is left as it is."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

Step = Callable[[sqlite3.Connection], None]
KEEP = 5
BACKUP_DIR = "db-backups"
TARGETS: Dict[str, int] = {}  # database name -> the version this build writes (filled by the modules that own them)


def columns(db: sqlite3.Connection, tabella: str) -> set:
    return {r[1] for r in db.execute(f"PRAGMA table_info({tabella})")}


def add_column(tabella: str, nome: str, tipo: str) -> Step:
    """A step that adds a column (skipped when a build before 2.11 already added it)."""
    def passo(db: sqlite3.Connection) -> None:
        if nome not in columns(db, tabella):
            db.execute(f"ALTER TABLE {tabella} ADD COLUMN {nome} {tipo}")
    passo.__doc__ = f"{tabella}.{nome}"
    return passo


def version(path: Path) -> Optional[int]:
    p = Path(path)
    if not p.exists():
        return None
    db = sqlite3.connect(p, timeout=10)
    try:
        return int(db.execute("PRAGMA user_version").fetchone()[0])
    finally:
        db.close()


def backup(db: sqlite3.Connection, path: Path, nome: str, versione: int) -> Path:
    cartella = Path(path).parent / BACKUP_DIR
    cartella.mkdir(parents=True, exist_ok=True)
    destinazione = cartella / f"{nome}-v{versione}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
    copia = sqlite3.connect(destinazione)
    try:
        db.backup(copia)  # consistent also with the write-ahead log
    finally:
        copia.close()
    vecchie = sorted(cartella.glob(f"{nome}-v*.db"), key=lambda p: p.stat().st_mtime)
    for p in vecchie[:-KEEP]:
        try:
            p.unlink()
        except OSError:
            pass
    return destinazione


def upgrade(path: Path, nome: str, schema: str, steps: Sequence[Step]) -> dict:
    """Creates or upgrades a database: the current schema (CREATE ... IF NOT EXISTS), then the missing steps."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    obiettivo = len(steps)
    TARGETS[nome] = obiettivo
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        versione = int(db.execute("PRAGMA user_version").fetchone()[0])
        if versione > obiettivo:
            return {"name": nome, "version": versione, "target": obiettivo, "newer": True, "backup": None, "applied": []}
        tabelle = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        copia = backup(db, path, nome, versione) if versione < obiettivo and tabelle else None
        fatti: List[str] = []
        db.execute("BEGIN IMMEDIATE")
        try:
            for istruzione in _statements(schema):
                db.execute(istruzione)
            for n in range(versione, obiettivo):
                steps[n](db)
                fatti.append(steps[n].__doc__ or f"step {n + 1}")
            db.execute(f"PRAGMA user_version = {obiettivo}")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return {"name": nome, "version": obiettivo, "target": obiettivo, "newer": False, "backup": str(copia) if copia else None, "applied": fatti}
    finally:
        db.close()


def _statements(schema: str) -> List[str]:
    """The statements of a schema script, to run them inside the transaction (executescript would commit first)."""
    fuori, parziale = [], ""
    for riga in schema.splitlines(keepends=True):
        parziale += riga
        if sqlite3.complete_statement(parziale):
            if parziale.strip():
                fuori.append(parziale.strip())
            parziale = ""
    if parziale.strip():
        fuori.append(parziale.strip())
    return fuori


def status(data_dir: Path) -> List[dict]:
    """Version of every database in the data folder and its backups, for Settings › Data."""
    cartella = Path(data_dir)
    copie = sorted((cartella / BACKUP_DIR).glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True) if (cartella / BACKUP_DIR).exists() else []
    fuori = []
    for nome in ("wmm.db", "accounts.db", "central.db"):
        v = version(cartella / nome)
        if v is None:
            continue
        chiave = nome.split(".")[0]
        fuori.append({"name": nome, "version": v, "target": TARGETS.get(chiave), "backups": [p.name for p in copie if p.name.startswith(chiave + "-")][:KEEP]})
    return fuori
