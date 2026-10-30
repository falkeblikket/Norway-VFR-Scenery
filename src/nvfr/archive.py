"""Validate ZIPs without executing content or extracting through untrusted paths."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from .errors import UnsafeArchive
from .paths import name_key, safe_folder, safe_parts, slug


@dataclass(frozen=True)
class Limits:
    files: int = 100_000
    total_bytes: int = 32 * 1024**3
    file_bytes: int = 8 * 1024**3
    ratio: int = 1000
    metadata_bytes: int = 16 * 1024**2


@dataclass(frozen=True)
class Package:
    archive: Path
    sha256: str
    root: tuple[str, ...]
    folder: str
    title: str
    creator: str
    version: str
    content_type: str
    bytes: int
    members: tuple[str, ...]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _index(zf: zipfile.ZipFile, limits: Limits) -> dict[str, zipfile.ZipInfo]:
    members = zf.infolist()
    if len(members) > limits.files:
        raise UnsafeArchive("Archive exceeds the file-count limit")
    total = 0
    result = {}
    paths: dict[str, tuple[str, bool]] = {}
    for item in members:
        if item.orig_filename != item.filename:
            raise UnsafeArchive("ZIP entry contains a truncated or NUL-containing name")
        parts = safe_parts(item.filename)
        if any(p.lower().startswith(".nvfr") for p in parts):
            raise UnsafeArchive("Archive contains a reserved manager filename")
        key = "/".join(name_key(p) for p in parts)
        if key in paths:
            raise UnsafeArchive(f"Duplicate/case-colliding ZIP entry: {item.filename}")
        mode = item.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UnsafeArchive(f"Link or special file in ZIP: {item.filename}")
        if item.flag_bits & 1:
            raise UnsafeArchive("Encrypted ZIP files are not supported")
        if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise UnsafeArchive("Only stored and deflated ZIP files are supported")
        if item.is_dir() and item.file_size:
            raise UnsafeArchive("Directory ZIP entry contains data")
        if item.file_size > limits.file_bytes:
            raise UnsafeArchive("Archive exceeds the per-file size limit")
        total += item.file_size
        if total > limits.total_bytes:
            raise UnsafeArchive("Archive exceeds the expanded-size limit")
        if item.file_size > max(item.compress_size, 1) * limits.ratio:
            raise UnsafeArchive("Suspicious ZIP compression ratio")
        paths[key] = (item.filename, item.is_dir())
        if not item.is_dir():
            result[key] = item
    # Case collisions in implicit directories also matter on Windows.
    spellings = {}
    for item in members:
        parts = safe_parts(item.filename)
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            key = name_key(prefix)
            if key in spellings and spellings[key] != prefix:
                raise UnsafeArchive(f"Inconsistent path spelling: {prefix}")
            spellings[key] = prefix
            if length < len(parts) and key in result:
                raise UnsafeArchive(f"ZIP file is also used as a directory: {prefix}")
    return result


def _json(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limits: Limits) -> dict:
    if info.file_size > limits.metadata_bytes:
        raise UnsafeArchive(f"Metadata too large: {info.filename}")
    try:
        result = json.loads(zf.read(info).decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise UnsafeArchive(f"Invalid JSON: {info.filename}") from exc
    if not isinstance(result, dict):
        raise UnsafeArchive(f"Expected JSON object: {info.filename}")
    return result


def inspect_zip(path: Path, limits: Limits = Limits()) -> list[Package]:
    path = path.absolute()
    try:
        sha256 = digest(path)
        with zipfile.ZipFile(path) as zf:
            index = _index(zf, limits)
            roots = []
            for key in index:
                if key == "manifest.json" or key.endswith("/manifest.json"):
                    prefix = key.removesuffix("manifest.json")
                    if prefix + "layout.json" in index:
                        roots.append(prefix)
            if not roots:
                raise UnsafeArchive("No package with both manifest.json and layout.json was found")
            if any(a != b and b.startswith(a) for a in roots for b in roots):
                raise UnsafeArchive("Nested MSFS package roots are ambiguous")
            packages = []
            for prefix in roots:
                manifest_info = index[prefix + "manifest.json"]
                root = safe_parts(manifest_info.filename)[:-1]
                manifest = _json(zf, manifest_info, limits)
                layout = _json(zf, index[prefix + "layout.json"], limits)
                for field in ("title", "creator", "package_version"):
                    if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                        raise UnsafeArchive(f"Missing/invalid MSFS manifest {field}: {manifest_info.filename}")
                entries = layout.get("content")
                if not isinstance(entries, list):
                    raise UnsafeArchive("layout.json must contain a content array")
                layout_names = set()
                for entry in entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                        raise UnsafeArchive("Invalid layout entry")
                    relative = "/".join(name_key(p) for p in safe_parts(entry["path"]))
                    if relative in layout_names:
                        raise UnsafeArchive(f"Duplicate layout entry: {relative}")
                    layout_names.add(relative)
                    info = index.get(prefix + relative)
                    size = entry.get("size")
                    if info is None or type(size) is not int or size != info.file_size:
                        raise UnsafeArchive(f"Missing file or wrong size in layout: {entry['path']}")
                selected = tuple(i.filename for k, i in index.items() if k.startswith(prefix))
                folder = root[-1] if root else slug(manifest["creator"] + "-" + manifest["title"])
                packages.append(Package(
                    path, sha256, root, safe_folder(folder), manifest["title"],
                    manifest["creator"], manifest["package_version"],
                    str(manifest.get("content_type", "unknown")),
                    sum(index[k].file_size for k in index if k.startswith(prefix)), selected,
                ))
            if len({name_key(p.folder) for p in packages}) != len(packages):
                raise UnsafeArchive("Multiple packages have the same destination directory name")
            return packages
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error) as exc:
        raise UnsafeArchive(f"Cannot read ZIP {path.name}: {exc}") from exc


def extract_package(package: Package, destination: Path, limits: Limits = Limits()) -> None:
    """Extract into a fresh private staging directory; revalidate the exact open ZIP."""
    destination.mkdir(exist_ok=False)
    try:
        with package.archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != package.sha256:
                raise UnsafeArchive("ZIP changed after preview. Import it again.")
            stream.seek(0)
            with zipfile.ZipFile(stream) as zf:
                index = _index(zf, limits)
                by_name = {i.filename: i for i in index.values()}
                for member in package.members:
                    parts = safe_parts(member)
                    if parts[:len(package.root)] != package.root:
                        raise UnsafeArchive("Package member escaped its root")
                    relative = parts[len(package.root):]
                    target = destination.joinpath(*relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    info = by_name[member]
                    count = 0
                    with zf.open(info) as source, target.open("xb") as out:
                        while chunk := source.read(1024 * 1024):
                            count += len(chunk)
                            if count > info.file_size:
                                raise UnsafeArchive("ZIP expanded beyond its declared size")
                            out.write(chunk)
                    if count != info.file_size:
                        raise UnsafeArchive("Truncated ZIP member")
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, zlib.error) as exc:
        raise UnsafeArchive(f"Extraction failed: {exc}") from exc
