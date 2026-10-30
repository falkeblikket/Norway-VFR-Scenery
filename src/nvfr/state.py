"""Local installation database and single-writer lock (separate from catalogues)."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from .errors import SceneryError
from .paths import absolute_directory


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as out:
        json.dump(value, out, indent=2, ensure_ascii=False)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


class State:
    def __init__(self, directory: Path):
        self.directory = absolute_directory(directory)
        self.database = self.directory / "installations.sqlite3"
        self.journals = self.directory / "transactions"
        self.journals.mkdir(exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise SceneryError("This installation database needs a newer application")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS packages (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commits (id TEXT PRIMARY KEY);
                PRAGMA user_version=1;
            """)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        return contextlib.closing(db)

    def records(self) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM packages ORDER BY id")]

    def committed(self, operation: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM commits WHERE id=?", (operation,)).fetchone() is not None

    def commit(self, operation: str, records: list[dict], deleted: list[str]) -> None:
        with self.connect() as db, db:
            for key in deleted:
                db.execute("DELETE FROM packages WHERE id=?", (key,))
            for record in records:
                db.execute("INSERT OR REPLACE INTO packages VALUES (?,?)",
                           (record["id"], json.dumps(record, ensure_ascii=False)))
            db.execute("INSERT INTO commits VALUES (?)", (operation,))

    def forget_commit(self, operation: str) -> None:
        with self.connect() as db, db:
            db.execute("DELETE FROM commits WHERE id=?", (operation,))

    @contextlib.contextmanager
    def lock(self):
        with (self.directory / "manager.lock").open("a+b") as lock:
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise SceneryError("Another manager operation is running. Try again when it finishes.") from exc
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)
