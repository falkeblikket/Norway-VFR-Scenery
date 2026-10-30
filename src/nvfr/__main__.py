from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from .discovery import app_directory


def main():
    parser = argparse.ArgumentParser(description="Norway VFR Scenery Manager")
    parser.add_argument("--data-dir", type=Path, default=None, help="Isolated settings/database directory")
    parser.add_argument("--smoke-test", action="store_true", help="Construct the GUI, load catalogue and exit")
    args = parser.parse_args()
    directory = args.data_dir or app_directory()
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "manager.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        import tkinter as tk
        from .gui import Application
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        root = tk.Tk()
        application = Application(root, directory)
        if args.smoke_test:
            from .state import atomic_json
            def finish_smoke():
                if application.busy:
                    root.after(100, finish_smoke)
                    return
                atomic_json(directory / "smoke-test.json", {
                    "ok": application.status.get() == "Ready",
                    "catalogue_packages": len(application.catalogue.packages),
                })
                root.destroy()
            root.after(300, finish_smoke)
        root.mainloop()
    except Exception as exc:
        logging.exception("Application could not start")
        if "root" in locals():
            from tkinter import messagebox
            messagebox.showerror("Norway VFR could not start", f"{exc}\n\nLog: {directory / 'manager.log'}")
        else:
            print(f"Norway VFR could not start: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
