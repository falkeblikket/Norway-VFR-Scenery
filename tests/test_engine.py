from dataclasses import replace
from pathlib import Path

import pytest

from nvfr.archive import inspect_zip
from nvfr.engine import Selection
from nvfr.errors import Conflict, SceneryError
from nvfr.links import create_link, points_to
from nvfr.transaction import Transaction


def selection(path, catalogue_id=None):
    return [Selection(p, catalogue_id) for p in inspect_zip(path)]


@pytest.mark.parametrize("method", ["direct", "linked"])
def test_full_lifecycle(engine, settings, make_zip, method):
    settings = replace(settings, method=method)
    initial = selection(make_zip())
    plan = engine.plan(initial, settings)
    assert plan.rows[0]["action"] == "install"
    assert plan.warnings
    records = engine.install(initial, settings, confirmed=True)
    record = records[0]
    payload = Path(record["path"])
    assert (payload / "manifest.json").is_file()
    assert record["catalogue_id"] == "test-airport"
    assert len(engine.records()) == 1
    if method == "linked":
        assert points_to(Path(settings.community) / "test-airport", payload)
    engine.set_active(record["id"], False)
    assert not (Path(settings.community) / "test-airport").exists()
    assert not engine.records()[0]["active"]
    updated = engine.install(selection(make_zip(version="2.0.0", payload=b"updated")), settings, confirmed=True)[0]
    assert not updated["active"]
    assert updated["id"] == record["id"]
    assert updated["version"] == "2.0.0"
    engine.set_active(record["id"], True)
    assert (Path(settings.community) / "test-airport/scenery/test.bgl").read_bytes() == b"updated"
    engine.uninstall(record["id"], confirmed=True)
    assert engine.records() == []
    assert not payload.exists()
    assert not list(engine.state.journals.glob("*.json"))


def test_confirmations_duplicate_and_changed_files(engine, settings, make_zip):
    request = selection(make_zip())
    with pytest.raises(SceneryError, match="confirm"):
        engine.install(request, settings)
    record = engine.install(request, settings, confirmed=True)[0]
    with pytest.raises(Conflict, match="Already installed"):
        engine.install(request, settings, confirmed=True)
    with pytest.raises(SceneryError, match="Confirm"):
        engine.uninstall(record["id"])
    (Path(record["path"]) / "user-file.txt").write_text("preserve me")
    with pytest.raises(Conflict, match="changed outside"):
        engine.uninstall(record["id"], confirmed=True)
    assert (Path(record["path"]) / "user-file.txt").read_text() == "preserve me"


def test_unmanaged_folder_and_external_link_are_preserved(engine, settings, make_zip, tmp_path):
    root = Path(settings.community)
    root.mkdir()
    path = root / "test-airport"
    path.mkdir()
    (path / "original.txt").write_text("keep")
    with pytest.raises(Conflict, match="not owned"):
        engine.install(selection(make_zip()), settings, confirmed=True)
    assert (path / "original.txt").read_text() == "keep"
    (path / "original.txt").unlink()
    path.rmdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / "external.txt").write_text("do not touch")
    create_link(path, other)
    with pytest.raises(Conflict):
        engine.install(selection(make_zip()), settings, confirmed=True)
    assert (other / "external.txt").read_text() == "do not touch"


def test_batch_rollback_after_one_package_was_moved(engine, settings, make_zip, monkeypatch):
    request = selection(make_zip("one", "two"), "unknown")
    original = Transaction.move
    calls = 0

    def fail(self, source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated disk failure")
        return original(self, source, target)
    monkeypatch.setattr(Transaction, "move", fail)
    with pytest.raises(OSError, match="disk failure"):
        engine.install(request, settings, confirmed=True)
    assert engine.records() == []
    assert list(Path(settings.community).iterdir()) == []
    assert not list(engine.state.journals.glob("*.json"))


def test_update_rollback_when_database_commit_fails(engine, settings, make_zip, monkeypatch):
    record = engine.install(selection(make_zip()), settings, confirmed=True)[0]
    original = (Path(record["path"]) / "scenery/test.bgl").read_bytes()

    def fail(*args, **kwargs):
        raise OSError("database failure")
    monkeypatch.setattr(engine.state, "commit", fail)
    with pytest.raises(OSError, match="database failure"):
        engine.install(selection(make_zip(version="2", payload=b"replacement")), settings, confirmed=True)
    assert engine.records()[0] == record
    assert (Path(record["path"]) / "scenery/test.bgl").read_bytes() == original


@pytest.mark.parametrize("operation", ["disable", "uninstall"])
def test_remove_and_toggle_rollback(engine, settings, make_zip, monkeypatch, operation):
    record = engine.install(selection(make_zip()), settings, confirmed=True)[0]
    def fail(*args, **kwargs):
        raise OSError("database failure")
    monkeypatch.setattr(engine.state, "commit", fail)
    with pytest.raises(OSError):
        if operation == "disable":
            engine.set_active(record["id"], False)
        else:
            engine.uninstall(record["id"], confirmed=True)
    assert engine.records()[0]["active"]
    assert Path(record["path"]).is_dir()


def test_link_creation_failure_rolls_back_payload(engine, settings, make_zip, monkeypatch):
    settings = replace(settings, method="linked")
    def fail(*args):
        raise SceneryError("junction unsupported")
    monkeypatch.setattr("nvfr.engine.create_link", fail)
    with pytest.raises(SceneryError, match="junction"):
        engine.install(selection(make_zip()), settings, confirmed=True)
    assert engine.records() == []
    assert not (Path(settings.library) / "test-airport").exists()


def test_known_dependencies_and_conflicts(engine, settings, make_zip):
    from conftest import catalogue_doc, catalogue_item
    from nvfr.catalogue import Catalogue
    airport = catalogue_item()
    library = catalogue_item("test-library", "library")
    airport["dependencies"] = ["test-library"]
    airport["conflicts"] = []
    library["dependencies"], library["conflicts"] = [], []
    engine.catalogue = Catalogue([catalogue_doc(airport, library)])
    with pytest.raises(SceneryError, match="Missing active dependencies"):
        engine.plan(selection(make_zip()), settings)
    requests = selection(make_zip()) + selection(make_zip("library"))
    records = engine.install(requests, settings, confirmed=True)
    lib = next(r for r in records if r["catalogue_id"] == "test-library")
    with pytest.raises(SceneryError, match="Missing active dependencies"):
        engine.set_active(lib["id"], False)
    airport["conflicts"] = ["test-library"]
    engine.catalogue = Catalogue([catalogue_doc(airport, library)])
    with pytest.raises(SceneryError, match="Known conflict"):
        engine.plan(selection(make_zip(version="2")), settings)


def test_checksum_mismatch(engine, settings, make_zip):
    engine.catalogue.packages["test-airport"]["sha256"] = "0" * 64
    with pytest.raises(Conflict, match="SHA-256"):
        engine.plan(selection(make_zip()), settings)


def test_external_changes_to_junction_are_preserved(engine, settings, make_zip, tmp_path):
    from nvfr.links import remove_tree
    settings = replace(settings, method="linked")
    record = engine.install(selection(make_zip()), settings, confirmed=True)[0]
    link = Path(settings.community) / "test-airport"
    remove_tree(link)
    other = tmp_path / "outside"
    other.mkdir()
    create_link(link, other)
    with pytest.raises(Conflict, match="changed externally"):
        engine.uninstall(record["id"], confirmed=True)
    assert points_to(link, other)
    assert Path(record["path"]).exists()
