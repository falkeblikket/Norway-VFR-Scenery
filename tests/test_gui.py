import json
import os
import time
import tkinter as tk
from tkinter import ttk

import pytest

from conftest import catalogue_doc, catalogue_item
from nvfr.discovery import Settings
from nvfr.gui import Application

pytestmark = [pytest.mark.gui, pytest.mark.skipif(
    os.name != "nt" and not os.environ.get("DISPLAY"), reason="GUI needs Windows or Xvfb")]


def pump(root, predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate():
        root.update()
        if time.monotonic() > deadline:
            raise AssertionError("GUI operation timed out")
        time.sleep(0.01)
    root.update()


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


def click(root, text):
    button = next(w for w in children(root) if isinstance(w, ttk.Button) and w.cget("text") == text)
    button.invoke()


def test_gui_import_preview_install_toggle_uninstall(tmp_path, make_zip, monkeypatch):
    directory = tmp_path / "app-data"
    (directory / "catalogues").mkdir(parents=True)
    (directory / "catalogues/synthetic-tests.json").write_text(json.dumps(catalogue_doc(catalogue_item())))
    settings = Settings(str(tmp_path / "Community"), str(tmp_path / "Addons"))
    settings.save(directory / "settings.json")
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    monkeypatch.setattr("nvfr.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    monkeypatch.setattr("nvfr.gui.messagebox.askyesno", lambda *args, **kwargs: True)
    path = make_zip()
    monkeypatch.setattr("nvfr.gui.filedialog.askopenfilenames", lambda **kwargs: (str(path),))
    try:
        app = Application(root, directory)
        pump(root, lambda: not app.busy)
        app.filters["search"].set("Test Airport")
        assert "test-airport" in app.catalogue_view.get_children()
        app.catalogue_view.selection_set("test-airport")
        app.import_zips()
        pump(root, lambda: not app.busy)
        click(root, "Review installation…")
        pump(root, lambda: not app.busy)
        click(root, "Confirm and install")
        pump(root, lambda: not app.busy)
        records = app.engine.records()
        assert len(records) == 1
        app.installed_view.selection_set(records[0]["id"])
        app.toggle(False)
        pump(root, lambda: not app.busy)
        assert not app.engine.records()[0]["active"]
        app.toggle(True)
        pump(root, lambda: not app.busy)
        assert app.engine.records()[0]["active"]
        app.uninstall()
        pump(root, lambda: not app.busy)
        assert app.engine.records() == []
        assert not errors
    finally:
        root.destroy()


def test_gui_settings_and_cancel_preview_do_not_install(tmp_path, make_zip, monkeypatch):
    root = tk.Tk()
    try:
        app = Application(root, tmp_path / "state")
        pump(root, lambda: not app.busy)
        app.community_var.set(str(tmp_path / "Community2024"))
        app.method_var.set("direct")
        app.save_settings()
        assert app.settings.community.endswith("Community2024")
        from nvfr.archive import inspect_zip
        app.preview(inspect_zip(make_zip()), set())
        click(root, "Cancel")
        assert app.engine.records() == []
        assert not (tmp_path / "Community2024/test-airport").exists()
    finally:
        root.destroy()
