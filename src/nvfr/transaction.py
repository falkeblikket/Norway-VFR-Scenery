"""Write-ahead filesystem journal coordinated with a SQLite commit marker.

Every destructive step is an atomic rename to private, same-volume storage.
A crash before the database commit rolls back; a crash after it finishes cleanup.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from .errors import RecoveryError, SceneryError
from .links import remove_tree
from .paths import exists
from .state import State, atomic_json

log = logging.getLogger(__name__)


class Transaction:
    def __init__(self, state: State):
        self.state = state
        self.id = uuid.uuid4().hex
        self.path = state.journals / (self.id + ".json")
        self.data = {"id": self.id, "moves": [], "workspaces": []}
        self.save()

    def save(self):
        atomic_json(self.path, self.data)

    def workspace(self, parent: Path) -> Path:
        directory = parent / self.id
        if str(directory) not in self.data["workspaces"]:
            if exists(directory):
                raise SceneryError("Private transaction directory already exists")
            self.data["workspaces"].append(str(directory))
            self.save()
            directory.mkdir(parents=True)
        return directory

    def move(self, source: Path, target: Path) -> None:
        if not exists(source) or exists(target):
            raise SceneryError(f"Cannot safely move {source} to {target}; filesystem changed")
        self.data["moves"].append({"source": str(source), "target": str(target)})
        self.save()
        # os.rename refuses an existing target on Windows. The preflight is also
        # repeated here; supported production platform is Windows.
        os.rename(source, target)
        log.info("Moved %s -> %s", source, target)

    def rollback(self):
        while self.data["moves"]:
            step = self.data["moves"][-1]
            source, target = Path(step["source"]), Path(step["target"])
            if exists(source) and not exists(target):
                pass  # Journalled but not executed, or already reversed.
            elif not exists(source) and exists(target):
                os.rename(target, source)
                log.info("Rolled back %s -> %s", target, source)
            else:
                raise RecoveryError(f"Recovery needs attention; preserve both paths: {source}, {target}")
            self.data["moves"].pop()
            self.save()
        self.cleanup()

    def cleanup(self):
        for directory in self.data["workspaces"]:
            remove_tree(Path(directory))
        self.path.unlink(missing_ok=True)
        self.state.forget_commit(self.id)

    def commit(self, records: list[dict], deleted: list[str] | None = None):
        self.state.commit(self.id, records, deleted or [])
        # From this point the operation is committed. A cleanup error must never
        # trigger rollback of files which SQLite now records as installed.
        try:
            self.cleanup()
        except Exception:
            log.exception("Committed successfully; cleanup will resume next time")

    @classmethod
    def recover(cls, state: State):
        import json

        for path in sorted(state.journals.glob("*.json")):
            try:
                tx = cls.__new__(cls)
                tx.state, tx.path = state, path
                tx.data = json.loads(path.read_text(encoding="utf-8"))
                tx.id = tx.data["id"]
                if state.committed(tx.id):
                    tx.cleanup()
                else:
                    tx.rollback()
            except Exception as exc:
                raise RecoveryError(f"Automatic recovery could not finish. Keep {path}. Details: {exc}") from exc
