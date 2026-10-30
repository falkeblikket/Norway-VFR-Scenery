"""Filesystem operations independent of the GUI and any download provider."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .archive import Package, digest, extract_package
from .catalogue import Catalogue
from .discovery import Settings
from .errors import Conflict, SceneryError
from .links import create_link, points_to
from .paths import absolute_directory, child, exists, name_key, plain_tree, safe_folder
from .state import State, atomic_json
from .transaction import Transaction

log = logging.getLogger(__name__)
OWNER = ".nvfr-owner.json"


@dataclass(frozen=True)
class Selection:
    package: Package
    catalogue_id: str | None = None


@dataclass
class Plan:
    selections: list[Selection]
    rows: list[dict]
    warnings: list[str]


def _path_key(path: Path | str) -> str:
    return name_key(os.path.abspath(path))


def inventory(path: Path) -> dict[str, str]:
    plain_tree(path)
    return {str(p.relative_to(path)).replace("\\", "/"): digest(p)
            for p in sorted(path.rglob("*")) if p.is_file() and p != path / OWNER}


class Engine:
    def __init__(self, state: State, catalogue: Catalogue):
        self.state = state
        self.catalogue = catalogue

    def recover(self):
        with self.state.lock():
            Transaction.recover(self.state)

    def records(self):
        return self.state.records()

    def _control(self, root: Path) -> Path:
        key = hashlib.sha256(_path_key(root).encode()).hexdigest()[:16]
        directory = absolute_directory(root.parent / ".nvfr-manager" / key)
        owner = directory / "root.json"
        identity = {"root": _path_key(root), "state": _path_key(self.state.directory)}
        if owner.exists():
            if json.loads(owner.read_text("utf-8")) != identity:
                raise SceneryError(f"Directory is managed by a different installation database: {root}")
        else:
            # Exclusive create also serialises the first claim across manager instances.
            with owner.open("x", encoding="utf-8") as out:
                json.dump(identity, out)
        return directory

    def _disabled(self, community: Path) -> Path:
        return absolute_directory(self._control(community) / "disabled")

    def _root_checks(self, community: Path, library: Path):
        for root in {community, library}:
            if root == root.parent:
                raise SceneryError("Choose a scenery folder, not the root of a drive")
            if self.state.directory == root or root in self.state.directory.parents or self.state.directory in root.parents:
                raise SceneryError("Application data and scenery must use separate directories")
            if any(part.lower() == ".nvfr-manager" for part in root.parts):
                raise SceneryError("The manager's private storage cannot be an installation folder")
            self._control(root)

    @staticmethod
    def _slot(record):
        return _path_key(record["community"]), name_key(record["folder"])

    def _record(self, identifier: str) -> dict:
        for record in self.records():
            if record["id"] == identifier:
                return record
        raise SceneryError("Installation no longer exists; refresh the list")

    def _verify(self, record: dict) -> Path:
        community = absolute_directory(Path(record["community"]))
        library = absolute_directory(Path(record["library"]))
        self._root_checks(community, library)
        folder = safe_folder(record["folder"])
        if record["method"] == "linked":
            expected = child(library, folder)
        else:
            expected = child(community if record["active"] else self._disabled(community), folder)
        path = Path(record["path"])
        if path != expected:
            raise SceneryError("Installation database path does not match its managed location")
        plain_tree(path)
        try:
            marker = json.loads((path / OWNER).read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise Conflict(f"Ownership marker missing or damaged: {path}") from exc
        if marker != {"format": 1, "id": record["id"]}:
            raise Conflict(f"Ownership marker changed: {path}")
        if inventory(path) != record["inventory"]:
            raise Conflict(f"Files changed outside the manager: {path}. Back up and restore them before changing this installation.")
        if record["method"] == "linked" and record["active"]:
            activation = child(community, folder)
            if not points_to(activation, path):
                raise Conflict(f"Activation link was removed or changed externally: {activation}. Restore it before continuing.")
        return path

    @staticmethod
    def _occupied(path: Path) -> bool:
        return exists(path) or any(name_key(item.name) == name_key(path.name) for item in path.parent.iterdir())

    def plan(self, selections: list[Selection], settings: Settings) -> Plan:
        community, library = settings.roots()
        self._root_checks(community, library)
        if not selections:
            raise SceneryError("Select at least one imported package")
        records = self.records()
        slots = {self._slot(r): r for r in records}
        planned, resolved, warnings, seen = [], [], [], set()
        for selection in selections:
            package = selection.package
            folder = safe_folder(package.folder)
            slot = _path_key(community), name_key(folder)
            if slot in seen:
                raise Conflict(f"Two selected packages use the same directory: {folder}")
            seen.add(slot)
            key = selection.catalogue_id
            if key is None:
                key = self.catalogue.match(package)[0]
            if key == "unknown":
                key = None
            item = self.catalogue.packages.get(key) if key else None
            if key and not item:
                raise SceneryError(f"Unknown catalogue ID: {key}")
            if item:
                checksum = item["sha256"]
                if checksum != "unknown" and checksum != package.sha256:
                    raise Conflict(f"SHA-256 does not match the catalogue: {item['name']}")
                if item["compatibility"]["msfs2024"] != "confirmed":
                    warnings.append(f"{item['name']}: MSFS 2024 compatibility is {item['compatibility']['msfs2024']}")
                if item["license"]["name"] == "unknown":
                    warnings.append(f"{item['name']}: licence is unknown; check the original page")
            else:
                warnings.append(f"{package.title}: unmatched local package; compatibility, dependencies and conflicts are unknown")
            old = slots.get(slot)
            if old:
                self._verify(old)
                if old["method"] != settings.method or _path_key(old["library"]) != _path_key(library):
                    raise Conflict("Update using the original installation method and directories, or uninstall first")
                if old["catalogue_id"] != key:
                    raise Conflict(f"Catalogue identity differs from installed package: {folder}")
                if old["sha256"] == package.sha256:
                    raise Conflict(f"Already installed from this ZIP: {package.title} {package.version}")
                target, active = Path(old["path"]), old["active"]
                action = "update"
            else:
                target, active, action = child(library, folder), True, "install"
                for location in {target, child(community, folder), child(self._disabled(community), folder)}:
                    if self._occupied(location):
                        raise Conflict(f"Existing scenery or link is not owned by this manager: {location}. Nothing will be overwritten.")
                if key and any(r["catalogue_id"] == key and _path_key(r["community"]) == _path_key(community)
                               and r["sha256"] != package.sha256 for r in records):
                    raise Conflict(f"{item['name']} is already installed under another folder name. Resolve the old installation first.")
            row = {"old": old, "action": action, "target": str(target), "active": active,
                   "catalogue_id": key, "community": str(community), "library": str(library)}
            planned.append(row)
            resolved.append(Selection(package, key or "unknown"))
        active_ids = {r["catalogue_id"] for r in records if r["active"] and r["catalogue_id"]
                      and _path_key(r["community"]) == _path_key(community) and self._slot(r) not in seen}
        active_ids |= {r["catalogue_id"] for r in planned if r["active"] and r["catalogue_id"]}
        warnings += self.catalogue.check_relationships(active_ids)
        # New payload and old backups coexist until commit. Backups are renames.
        by_drive: dict[int, tuple[Path, int]] = {}
        for selection, row in zip(resolved, planned):
            root = Path(row["target"]).parent
            device = root.stat().st_dev
            previous = by_drive.get(device, (root, 0))
            by_drive[device] = (root, previous[1] + selection.package.bytes)
        for root, size in by_drive.values():
            if shutil.disk_usage(root).free < size + 64 * 1024**2:
                raise SceneryError(f"Not enough free staging space on {root}")
        return Plan(resolved, planned, sorted(set(warnings)))

    @contextlib.contextmanager
    def _transaction(self):
        tx = Transaction(self.state)
        try:
            yield tx
        except BaseException:
            log.exception("Operation failed; attempting rollback")
            if not self.state.committed(tx.id):
                tx.rollback()
            raise

    def install(self, selections: list[Selection], settings: Settings, *, confirmed: bool = False) -> list[dict]:
        if not confirmed:
            raise SceneryError("Review and confirm the installation plan first")
        with self.state.lock():
            Transaction.recover(self.state)
            plan = self.plan(selections, settings)  # Recheck under the lock after preview.
            with self._transaction() as tx:
                staged = []
                for number, (selection, row) in enumerate(zip(plan.selections, plan.rows)):
                    old, package = row["old"], selection.package
                    root = Path(row["library"])
                    work = tx.workspace(self._control(root))
                    stage = work / f"new-{number}"
                    extract_package(package, stage)
                    identifier = old["id"] if old else uuid.uuid4().hex
                    atomic_json(stage / OWNER, {"format": 1, "id": identifier})
                    record = {
                        "id": identifier, "catalogue_id": row["catalogue_id"], "folder": package.folder,
                        "title": package.title, "creator": package.creator, "version": package.version,
                        "sha256": package.sha256, "path": row["target"], "community": row["community"],
                        "library": row["library"], "method": settings.method, "active": row["active"],
                        "installed_at": datetime.now(timezone.utc).isoformat(), "inventory": inventory(stage),
                    }
                    item = self.catalogue.packages.get(record["catalogue_id"])
                    record["source_url"] = item["flightsim_to"]["url"] if item else "unknown"
                    staged.append((stage, row, record))
                # All selected ZIPs, CRCs and payloads must validate before any old package is moved.
                for number, (stage, row, record) in enumerate(staged):
                    target = Path(row["target"])
                    if row["old"]:
                        self._verify(row["old"])
                        tx.move(target, stage.parent / f"backup-{number}")
                    tx.move(stage, target)
                    if settings.method == "linked" and row["active"] and not row["old"]:
                        community = Path(row["community"])
                        link_work = tx.workspace(self._control(community))
                        temporary_link = link_work / f"link-{number}"
                        create_link(temporary_link, target)
                        tx.move(temporary_link, child(community, record["folder"]))
                result = [r for _, _, r in staged]
                tx.commit(result)
                log.info("Committed batch of %d package(s)", len(result))
                return result

    def _relationship_change(self, record: dict, active: bool):
        records = self.records()
        ids = {r["catalogue_id"] for r in records if r["id"] != record["id"] and r["active"]
               and r["catalogue_id"] and _path_key(r["community"]) == _path_key(record["community"])}
        if active and record["catalogue_id"]:
            ids.add(record["catalogue_id"])
        self.catalogue.check_relationships(ids)

    def set_active(self, identifier: str, active: bool):
        with self.state.lock():
            Transaction.recover(self.state)
            record = self._record(identifier)
            path = self._verify(record)
            if record["active"] == active:
                return
            self._relationship_change(record, active)
            community = Path(record["community"])
            activation = child(community, record["folder"])
            with self._transaction() as tx:
                work = tx.workspace(self._control(community))
                if record["method"] == "linked":
                    if active:
                        if self._occupied(activation):
                            raise Conflict(f"Community path already exists: {activation}")
                        temporary_link = work / "activation"
                        create_link(temporary_link, path)
                        tx.move(temporary_link, activation)
                    else:
                        tx.move(activation, work / "activation")
                else:
                    target = activation if active else child(self._disabled(community), record["folder"])
                    if self._occupied(target):
                        raise Conflict(f"Activation destination already exists: {target}")
                    tx.move(path, target)
                    record["path"] = str(target)
                record["active"] = active
                tx.commit([record])

    def uninstall(self, identifier: str, *, confirmed: bool = False):
        if not confirmed:
            raise SceneryError("Confirm permanent removal of the selected managed package")
        with self.state.lock():
            Transaction.recover(self.state)
            record = self._record(identifier)
            path = self._verify(record)
            self._relationship_change(record, False)
            with self._transaction() as tx:
                work = tx.workspace(self._control(Path(record["library"])))
                if record["method"] == "linked" and record["active"]:
                    community = Path(record["community"])
                    link_work = tx.workspace(self._control(community))
                    tx.move(child(community, record["folder"]), link_work / "activation")
                tx.move(path, work / "removed")
                tx.commit([], [record["id"]])
                log.info("Uninstalled %s", record["title"])
