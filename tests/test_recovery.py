
import pytest

from nvfr.errors import RecoveryError, SceneryError
from nvfr.links import create_link, remove_tree
from nvfr.state import atomic_json
from nvfr.transaction import Transaction


def test_recovery_rolls_back_an_interrupted_update(engine, tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    installed = root / "airport"
    installed.mkdir()
    (installed / "old.txt").write_text("old")
    tx = Transaction(engine.state)
    work = tx.workspace(root / "transactions")
    fresh = work / "fresh"
    fresh.mkdir()
    (fresh / "new.txt").write_text("new")
    tx.move(installed, work / "backup")
    tx.move(fresh, installed)
    # Simulate process death: no rollback/commit called.
    engine.recover()
    assert (installed / "old.txt").read_text() == "old"
    assert not (installed / "new.txt").exists()
    engine.recover()  # Idempotent.


def test_recovery_after_committed_database_finishes_cleanup(engine, tmp_path):
    tx = Transaction(engine.state)
    work = tx.workspace(tmp_path / "transactions")
    payload = work / "payload"
    payload.mkdir()
    (payload / "new.txt").write_text("new")
    target = tmp_path / "installed"
    tx.move(payload, target)
    engine.state.commit(tx.id, [], [])
    engine.recover()
    assert (target / "new.txt").read_text() == "new"
    assert not work.exists()


def test_recovery_of_journalled_but_not_executed_move(engine, tmp_path):
    tx = Transaction(engine.state)
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    tx.data["moves"].append({"source": str(source), "target": str(target)})
    tx.save()
    engine.recover()
    assert source.is_dir()
    assert not target.exists()


def test_restart_during_rollback_is_safe(engine, tmp_path, monkeypatch):
    import nvfr.transaction as module
    tx = Transaction(engine.state)
    work = tx.workspace(tmp_path / "work")
    old, fresh = tmp_path / "installed", work / "new"
    old.mkdir()
    (old / "old.txt").write_text("keep")
    fresh.mkdir()
    tx.move(old, work / "backup")
    tx.move(fresh, old)
    real_save = module.atomic_json
    failed = False

    def interrupt(path, data):
        nonlocal failed
        if not failed and len(data["moves"]) == 1:
            failed = True
            raise OSError("power loss after first undo")
        real_save(path, data)
    monkeypatch.setattr(module, "atomic_json", interrupt)
    with pytest.raises(OSError):
        tx.rollback()
    monkeypatch.setattr(module, "atomic_json", real_save)
    engine.recover()
    assert (old / "old.txt").read_text() == "keep"


def test_ambiguous_recovery_preserves_both_paths(engine, tmp_path):
    tx = Transaction(engine.state)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    tx.move(a, b)
    a.mkdir()  # External change after crash.
    with pytest.raises(RecoveryError, match="attention"):
        engine.recover()
    assert a.is_dir() and b.is_dir() and tx.path.exists()


def test_cleanup_never_follows_link(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    work = tmp_path / "work"
    work.mkdir()
    create_link(work / "link", outside)
    remove_tree(work)
    assert (outside / "keep.txt").read_text() == "keep"


def test_single_writer_lock(engine):
    with engine.state.lock():
        with pytest.raises(SceneryError, match="Another manager"):
            with engine.state.lock():
                pass


def test_atomic_json_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    import nvfr.state as module
    path = tmp_path / "state.json"
    atomic_json(path, {"old": True})
    def fail(*args):
        raise OSError("disk error")
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_json(path, {"new": True})
    assert '"old"' in path.read_text()
