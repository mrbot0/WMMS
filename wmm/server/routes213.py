"""The routes of the Backup tab of Storage (wmm/agent/backups.py). api.py mixes HandlerBackups into Handler and appends
BACKUP_ROUTES; permissions.py merges RULES. Reading needs view.storage; running or deleting a backup
run.storage.safe; creating and changing one (folders and destination) run.storage.moderate; restoring into a
new folder and deleting a version run.storage.moderate; replacing files or restoring them in their place run.storage.high. Windows,
the programs and the data of this app are refused as source, destination and restore folder. Every write is audited."""
from __future__ import annotations

from typing import Any

from ..agent import accounts, backups, plus212
from .errors import ApiError

ID = r"(b[0-9a-f]{10})"


class HandlerBackups:
    # Set by Handler in api.py (declared for the type checker).
    agent: Any
    _body: Any
    _json: Any
    user: Any

    def _b(self, funzione, *a, **k):
        try:
            return funzione(*a, **k)
        except backups.BackupError as e:
            raise ApiError(e.status, str(e)) from None
        except OSError as e:
            raise ApiError(502, (e.strerror or str(e))[:300]) from None

    def backups_list(self, query):
        d = self._b(backups.summary, self.agent.data_dir)
        d["suggested"] = [str(p) for p in plus212.default_folders()]
        self._json(200, d)

    def backups_create(self, query):
        self._json(201, self._b(backups.save, self.agent.data_dir, self._body()))

    def backups_update(self, query, ident):
        self._json(200, self._b(backups.save, self.agent.data_dir, self._body(), ident))

    def backups_delete(self, query, ident):
        self._b(backups.delete, self.agent.data_dir, ident)
        self._json(200, {"deleted": ident})

    def backups_run(self, query, ident):
        anteprima = bool(self._body().get("preview")) or bool(self.agent.preview)
        self._json(202, self._b(backups.run_async, self.agent.data_dir, ident, anteprima))

    def backups_history(self, query, ident):
        self._json(200, {"history": backups.history(self.agent.data_dir, ident, 200)})

    def backups_estimate(self, query, ident):
        self._json(200, self._b(backups.estimate, self.agent.data_dir, ident))

    def backups_versions(self, query, ident):
        self._json(200, {"versions": self._b(backups.list_versions, self.agent.data_dir, ident)})

    def backups_version_delete(self, query, ident):
        nome = str(query.get("version", ""))[:40]
        self._b(backups.delete_version, self.agent.data_dir, ident, nome)
        self._json(200, {"deleted": nome})

    def backups_files(self, query, ident):
        c = self._body()
        self._json(200, self._b(backups.files, self.agent.data_dir, ident, str(c.get("version", ""))[:40], c.get("password") or None))

    def backups_restore(self, query, ident):
        c = self._body()
        scelti = c.get("files")
        if scelti is not None and (not isinstance(scelti, list) or not all(isinstance(x, str) for x in scelti) or len(scelti) > 20000):
            raise ApiError(400, "files: a list of paths of the archive.")
        dest = c.get("dest")
        if dest is not None and not isinstance(dest, str):
            raise ApiError(400, "dest: a folder, or nothing to put the files back in their place.")
        anteprima = bool(c.get("preview")) or bool(self.agent.preview)
        # Replacing files, or writing back into the saved folders, changes files that exist: high risk.
        if (c.get("overwrite") or not dest) and self.user is not None and not accounts.has(self.user, "run.storage.high"):
            raise ApiError(403, "Your role does not allow this (run.storage.high): restore into a new folder without replacing files.")
        self._json(200, self._b(backups.restore, self.agent.data_dir, ident, str(c.get("version") or "")[:40] or None, dest or None, scelti or None,
                                c.get("password") or None, bool(c.get("overwrite")), anteprima))

    def backups_verify(self, query, ident):
        c = self._body()
        self._json(200, self._b(backups.verify, self.agent.data_dir, ident, str(c.get("version") or "")[:40] or None, c.get("password") or None))


BACKUP_ROUTES = [
    ("GET", "/backups", HandlerBackups.backups_list),
    ("POST", "/backups", HandlerBackups.backups_create),
    ("PUT", "/backups/" + ID, HandlerBackups.backups_update),
    ("DELETE", "/backups/" + ID, HandlerBackups.backups_delete),
    ("POST", "/backups/" + ID + "/run", HandlerBackups.backups_run),
    ("GET", "/backups/" + ID + "/history", HandlerBackups.backups_history),
    ("GET", "/backups/" + ID + "/estimate", HandlerBackups.backups_estimate),
    ("GET", "/backups/" + ID + "/versions", HandlerBackups.backups_versions),
    ("DELETE", "/backups/" + ID + "/versions", HandlerBackups.backups_version_delete),
    ("POST", "/backups/" + ID + "/files", HandlerBackups.backups_files),
    ("POST", "/backups/" + ID + "/restore", HandlerBackups.backups_restore),
    ("POST", "/backups/" + ID + "/verify", HandlerBackups.backups_verify),
]

RULES = {
    "backups_list": "view.storage", "backups_history": "view.storage", "backups_estimate": "view.storage", "backups_versions": "view.storage",
    "backups_files": "view.storage", "backups_verify": "view.storage",
    "backups_create": ("view.storage", "run.storage.moderate"), "backups_update": ("view.storage", "run.storage.moderate"),
    "backups_delete": ("view.storage", "run.storage.safe"), "backups_run": ("view.storage", "run.storage.safe"),
    "backups_restore": ("view.storage", "run.storage.moderate"), "backups_version_delete": ("view.storage", "run.storage.moderate"),
}
