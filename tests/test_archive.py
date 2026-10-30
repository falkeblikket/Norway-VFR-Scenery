import json
import stat
import zipfile
from dataclasses import replace

import pytest

from nvfr.archive import Limits, extract_package, inspect_zip
from nvfr.errors import UnsafeArchive


def test_nested_multi_package_and_root_zip(make_zip, tmp_path):
    packages = inspect_zip(make_zip("airport-a", "airport-b"))
    assert [p.folder for p in packages] == ["airport-a", "airport-b"]
    extract_package(packages[0], tmp_path / "stage")
    assert (tmp_path / "stage/manifest.json").is_file()
    assert (tmp_path / "stage/scenery/test.bgl").read_bytes() == b"synthetic scenery"
    assert not (tmp_path / "stage/wrapper").exists()
    root = inspect_zip(make_zip("", root_prefix=""))[0]
    assert root.folder == "test-developer-test-airport"


@pytest.mark.parametrize("name", [
    "../escape", "wrapper/../../escape", "/absolute", "C:/escape", "C:escape",
    "folder/file:stream", "folder\\..\\escape", "//server/share", "NUL.txt",
    "con", "COM1.bin", "COM¹.bin", "folder/trailing.", "folder/trailing ",
    "folder//file", "folder/./file", "bad?.bgl", "folder/.nvfr-owner.json",
])
def test_reject_unsafe_paths_anywhere_in_archive(make_zip, name):
    with pytest.raises(UnsafeArchive):
        inspect_zip(make_zip(extra={name: "bad"}))


@pytest.mark.parametrize("extra", [
    {"wrapper/test-airport/SCENERY/test.bgl": "duplicate case"},
    {"wrapper/test-airport/scenery": "file used as dir"},
    {"wrapper/test-airport/manifest.json": "duplicate"},
])
def test_reject_collisions(make_zip, extra):
    with pytest.raises(UnsafeArchive):
        inspect_zip(make_zip(extra=extra))


def test_reject_symlink_and_special_file(make_zip):
    for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR):
        path = make_zip()
        with zipfile.ZipFile(path, "a") as zf:
            item = zipfile.ZipInfo("wrapper/link")
            item.create_system = 3
            item.external_attr = (kind | 0o777) << 16
            zf.writestr(item, "../../outside")
        with pytest.raises(UnsafeArchive, match="special"):
            inspect_zip(path)


def test_layout_and_size_limits(make_zip):
    path = make_zip()
    for limits in (Limits(files=1), Limits(total_bytes=5), Limits(file_bytes=2), Limits(metadata_bytes=2)):
        with pytest.raises(UnsafeArchive):
            inspect_zip(path, limits)
    broken = make_zip(extra={"other/manifest.json": json.dumps({"title": "Other"}),
                            "other/layout.json": "{}"})
    with pytest.raises(UnsafeArchive):
        inspect_zip(broken)


def test_changed_zip_after_preview_and_bad_zip(make_zip, tmp_path):
    path = make_zip()
    package = inspect_zip(path)[0]
    with path.open("ab") as out:
        out.write(b"changed")
    with pytest.raises(UnsafeArchive, match="changed"):
        extract_package(package, tmp_path / "stage")
    broken = tmp_path / "broken.zip"
    broken.write_text("not a zip")
    with pytest.raises(UnsafeArchive):
        inspect_zip(broken)


def test_crc_failure_during_extraction(make_zip, tmp_path):
    path = make_zip()
    package = inspect_zip(path)[0]
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("other.txt", "x")
    # Re-inspect after changing the container, then corrupt compressed payload.
    package = inspect_zip(path)[0]
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo("wrapper/test-airport/scenery/test.bgl")
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    content = bytearray(path.read_bytes())
    content[offset + 2] ^= 0xFF
    path.write_bytes(content)
    from nvfr.archive import digest
    package = replace(package, sha256=digest(path))
    with pytest.raises((UnsafeArchive, zipfile.BadZipFile)):
        extract_package(package, tmp_path / "stage")


def test_nul_truncated_central_directory_name_is_rejected(make_zip):
    path = make_zip(extra={"rogue.txt": "bad"})
    content = path.read_bytes().replace(b"rogue.txt", b"rogue\x00txt")
    path.write_bytes(content)
    with pytest.raises(UnsafeArchive, match="NUL"):
        inspect_zip(path)
