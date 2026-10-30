"""Windows-safe names and filesystem boundaries, including reparse points."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath

from .errors import SceneryError, UnsafeArchive

RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in "123456789¹²³"
}


def safe_parts(name: str) -> tuple[str, ...]:
    """Reject names whose meaning can change during extraction on Windows."""
    if not isinstance(name, str) or not name or "\x00" in name:
        raise UnsafeArchive("Empty or NUL-containing path")
    normal = name.replace("\\", "/")
    if normal.startswith("/") or "//" in normal:
        raise UnsafeArchive(f"Absolute or ambiguous path: {name!r}")
    parts = normal.rstrip("/").split("/")
    for part in parts:
        if (not part or part in (".", "..") or part[-1] in " ."
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or part.split(".")[0].upper() in RESERVED
                or len(part) > 240):
            raise UnsafeArchive(f"Unsafe Windows path: {name!r}")
    if len(normal) > 1800:
        raise UnsafeArchive("Archive path is too long")
    return tuple(parts)


def name_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def safe_folder(value: str) -> str:
    if len(safe_parts(value)) != 1 or value.endswith(("/", "\\")):
        raise UnsafeArchive(f"Expected one directory name: {value}")
    if value.lower().startswith(".nvfr"):
        raise UnsafeArchive("The .nvfr prefix is reserved for the manager")
    return value


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return safe_folder(re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120] or "scenery")


def exists(path: Path) -> bool:
    return os.path.lexists(path)


def is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, FileNotFoundError):
        return False


def plain_tree(path: Path) -> None:
    """Never traverse an unexpected junction, symlink or special file."""
    if not exists(path):
        raise SceneryError(f"Missing managed directory: {path}")
    if is_link(path) or not path.is_dir():
        raise SceneryError(f"Managed directory was replaced or is a link: {path}")
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(base) / name
            if is_link(item) or not (item.is_dir() or item.is_file()):
                raise SceneryError(f"Unexpected link or special file in managed package: {item}")


def absolute_directory(path: Path, *, create: bool = True) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    # Reject linked ancestors too: changes must stay within the displayed location.
    for parent in reversed((path, *path.parents)):
        if exists(parent) and (is_link(parent) or not parent.is_dir()):
            raise SceneryError(f"Choose a real directory, not a link: {parent}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def child(parent: Path, name: str) -> Path:
    return parent / safe_folder(name)


def archive_relative(parts: tuple[str, ...]) -> str:
    return str(PurePosixPath(*parts))
