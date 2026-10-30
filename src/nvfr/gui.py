"""Small native Tk GUI. Slow archive/filesystem work runs off the UI thread."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .catalogue import Catalogue
from .discovery import Settings, discover_community
from .engine import Engine, Selection
from .errors import SceneryError
from .providers import BrowserSource, LocalZipSource
from .state import State

log = logging.getLogger(__name__)


def table(parent, columns, *, multiple=True):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    view = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                        selectmode="extended" if multiple else "browse")
    for key, title, width in columns:
        view.heading(key, text=title)
        view.column(key, width=width, minwidth=60, stretch=True)
    vertical = ttk.Scrollbar(frame, orient="vertical", command=view.yview)
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=view.xview)
    view.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    view.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    return view


def write_text(widget, text):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("end", text)
    widget.configure(state="disabled")


class Application:
    def __init__(self, root: tk.Tk, directory: Path):
        self.root, self.directory = root, directory
        self.state = State(directory)
        self.catalogue = Catalogue.load(directory / "catalogues")
        self.engine = Engine(self.state, self.catalogue)
        self.settings = Settings.load(directory / "settings.json")
        self.busy = False
        self.events = queue.Queue()
        self.buttons = []
        self.root.title(f"Norway VFR Scenery Manager {__version__}")
        self.root.geometry("1160x770")
        self.root.minsize(900, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=28)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        header = ttk.Frame(root, padding=(20, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Norway VFR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Discover scenery. Download from the creator. Install with confidence.").pack(anchor="w")
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=16)
        self.catalogue_tab = ttk.Frame(self.tabs, padding=12)
        self.installed_tab = ttk.Frame(self.tabs, padding=12)
        self.settings_tab = ttk.Frame(self.tabs, padding=18)
        self.logs_tab = ttk.Frame(self.tabs, padding=12)
        for frame, label in ((self.catalogue_tab, "Catalogue"), (self.installed_tab, "Installed"),
                             (self.settings_tab, "Settings"), (self.logs_tab, "Logs")):
            self.tabs.add(frame, text=label)
        self.build_catalogue()
        self.build_installed()
        self.build_settings()
        self.build_logs()
        footer = ttk.Frame(root, padding=(18, 10))
        footer.pack(fill="x")
        self.status = tk.StringVar(value="Ready — choose your Community folder in Settings")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=150)
        self.progress.pack(side="right")
        self.root.after(80, self.poll)
        self.run_task("Checking installation recovery…", self.engine.recover, lambda _: self.refresh())

    def button(self, parent, text, command, **pack):
        def guarded():
            if self.busy:
                return
            try:
                command()
            except Exception as exc:
                self.show_error(exc)
        button = ttk.Button(parent, text=text, command=guarded)
        button.pack(**({"side": "left", "padx": (0, 8)} | pack))
        self.buttons.append(button)
        return button

    def show_error(self, error):
        log.error("%s", error)
        self.status.set("Operation stopped — see the message and Logs")
        messagebox.showerror("Norway VFR", str(error), parent=self.root)

    def run_task(self, label, work, done):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        self.progress.start(12)
        for button in self.buttons:
            if button.winfo_exists():
                button.state(["disabled"])
        def execute():
            try:
                self.events.put((True, work(), done))
            except Exception as exc:
                log.exception("%s", label)
                self.events.put((False, exc, done))
        threading.Thread(target=execute, name="scenery-operation", daemon=False).start()

    def poll(self):
        try:
            ok, value, done = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.buttons = [b for b in self.buttons if b.winfo_exists()]
            for button in self.buttons:
                button.state(["!disabled"])
            self.status.set("Ready")
            if ok:
                try:
                    done(value)
                except Exception as exc:
                    self.show_error(exc)
            else:
                self.show_error(value)
                self.refresh()
        self.root.after(80, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Operation in progress", "Please wait for the current operation to finish.", parent=self.root)
        else:
            self.root.destroy()

    def build_catalogue(self):
        filters = ttk.Frame(self.catalogue_tab)
        filters.pack(fill="x", pady=(0, 10))
        self.filters = {}
        for field, label in (("search", "Search"), ("developer", "Developer"),
                             ("region", "Region"), ("category", "Category")):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 4))
            var = tk.StringVar(value="" if field == "search" else "All")
            self.filters[field] = var
            if field == "search":
                ttk.Entry(filters, textvariable=var, width=22).pack(side="left", padx=(0, 12))
            else:
                values = {p["geography"]["region"] if field == "region" else p[field]
                          for p in self.catalogue.packages.values()}
                combo = ttk.Combobox(filters, textvariable=var, values=["All", *sorted(values)], width=18, state="readonly")
                combo.pack(side="left", padx=(0, 12))
                setattr(self, field + "_combo", combo)
            var.trace_add("write", lambda *_: self.refresh_catalogue())
        toolbar = ttk.Frame(self.catalogue_tab)
        toolbar.pack(fill="x", pady=(0, 10))
        self.button(toolbar, "Open original page(s)", self.open_pages)
        self.button(toolbar, "Import downloaded ZIPs…", self.import_zips)
        self.button(toolbar, "Load catalogue JSON…", self.import_catalogue)
        self.catalogue_view = table(self.catalogue_tab, [
            ("name", "Scenery", 260), ("developer", "Developer", 130), ("category", "Category", 100),
            ("region", "Region", 130), ("version", "Listed version", 90),
            ("status", "Installed", 95), ("compatibility", "MSFS 2024", 110),
        ])
        self.catalogue_view.bind("<<TreeviewSelect>>", lambda _: self.show_catalogue_detail())
        self.catalogue_detail = ScrolledText(self.catalogue_tab, height=8, wrap="word", font=("Segoe UI", 10))
        self.catalogue_detail.pack(fill="x", pady=(10, 0))
        write_text(self.catalogue_detail, "Select scenery to see its creator, original source and verification details.\n"
                   "Downloads happen in your browser on Flightsim.to. This application does not sign in or download scenery.")

    def refresh_catalogue(self):
        if not hasattr(self, "catalogue_view"):
            return
        selected = self.catalogue_view.selection()
        self.catalogue_view.delete(*self.catalogue_view.get_children())
        installed = {}
        for record in self.engine.records():
            installed.setdefault(record["catalogue_id"], []).append(record)
        for item in sorted(self.catalogue.packages.values(), key=lambda p: p["name"].casefold()):
            if self.filters["search"].get().casefold() not in (item["name"] + " " + item["description"]).casefold():
                continue
            if any(self.filters[key].get() not in ("All", item["geography"]["region"] if key == "region" else item[key])
                   for key in ("developer", "region", "category")):
                continue
            records = installed.get(item["id"], [])
            status = "Yes / active" if any(r["active"] for r in records) else "Yes / disabled" if records else "No"
            self.catalogue_view.insert("", "end", iid=item["id"], values=(item["name"], item["developer"],
                item["category"], item["geography"]["region"], item["version"], status, item["compatibility"]["msfs2024"]))
        self.catalogue_view.selection_set([s for s in selected if self.catalogue_view.exists(s)])

    def show_catalogue_detail(self):
        selected = self.catalogue_view.selection()
        if not selected:
            return
        p = self.catalogue.packages[selected[0]]
        sources = "\n".join(f"{s['checked_at']}: {s['url']} — {s['note']}" for s in p["verification"]["sources"])
        write_text(self.catalogue_detail, f"{p['name']} — {p['developer']}\n{p['description']}\n"
            f"Original: {p['flightsim_to']['url']}\nCredit: {p['attribution']}\n"
            f"Licence: {p['license']['name']} | Redistribution: {p['license']['redistribution']}\n"
            f"Dependencies: {p['dependencies']} | Conflicts: {p['conflicts']}\n"
            f"Installation notes: {p['installation']['notes']}\n"
            f"Verification: {p['verification']['status']} | Last checked: {p['last_verified']}\n{sources}")

    def open_pages(self):
        ids = self.catalogue_view.selection()
        if not ids:
            raise SceneryError("Select one or more scenery packages first")
        if len(ids) > 1 and not messagebox.askyesno("Open pages", f"Open {len(ids)} original Flightsim.to pages in your browser?", parent=self.root):
            return
        for key in ids:
            if not BrowserSource().open_original(self.catalogue.packages[key]["flightsim_to"]["url"]):
                raise SceneryError("The browser could not open the page. Copy the link from the details panel.")

    def import_catalogue(self):
        name = filedialog.askopenfilename(parent=self.root, filetypes=[("Catalogue JSON", "*.json")])
        if not name:
            return
        if not messagebox.askyesno("Load catalogue", "Load this catalogue? A local catalogue with the same ID will be replaced. Installed scenery is not changed.", parent=self.root):
            return
        self.catalogue = self.catalogue.import_file(Path(name), self.directory / "catalogues", confirmed=True)
        self.engine.catalogue = self.catalogue
        for field in ("developer", "region", "category"):
            values = {p["geography"]["region"] if field == "region" else p[field] for p in self.catalogue.packages.values()}
            getattr(self, field + "_combo").configure(values=["All", *sorted(values)])
            self.filters[field].set("All")
        self.refresh()

    def import_zips(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Import downloaded scenery ZIPs",
                                           filetypes=[("ZIP archives", "*.zip")])
        if paths:
            selected_ids = set(self.catalogue_view.selection())
            self.run_task("Validating ZIP files…", lambda: LocalZipSource().inspect([Path(p) for p in paths]),
                          lambda packages: self.preview(packages, selected_ids))

    def preview(self, packages, selected_ids):
        window = tk.Toplevel(self.root)
        window.title("Review imported scenery")
        window.geometry("1100x600")
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", lambda: None if self.busy else window.destroy())
        ttk.Label(window, text="Select the package folders to install. Check the catalogue match before continuing.", padding=12).pack(anchor="w")
        view = table(window, [("name", "Archive title", 200), ("creator", "Archive creator", 120),
                              ("version", "ZIP version", 80), ("folder", "Package folder", 170),
                              ("match", "Catalogue match", 200), ("archive", "ZIP file", 120)])
        mappings = {}
        for n, package in enumerate(packages):
            key, reason = self.catalogue.match(package)
            mappings[n] = key or "unknown"
            view.insert("", "end", iid=str(n), values=(package.title, package.creator, package.version,
                package.folder, self.catalogue.packages[key]["name"] if key else reason, package.archive.name))
        choices = [str(n) for n in range(len(packages)) if not selected_ids or mappings[n] in selected_ids]
        view.selection_set(choices or view.get_children())
        controls = ttk.Frame(window, padding=12)
        controls.pack(fill="x")
        ttk.Label(controls, text="Assign selected rows to:").pack(side="left", padx=(0, 8))
        items = sorted(self.catalogue.packages.values(), key=lambda p: p["name"])
        labels = {f"{p['name']} — {p['developer']} [{p['id']}]": p["id"] for p in items}
        labels = {"Unmatched local package": "unknown", **labels}
        match_var = tk.StringVar(value="Unmatched local package")
        ttk.Combobox(controls, textvariable=match_var, values=list(labels), width=64, state="readonly").pack(side="left", padx=8)
        def assign():
            for value in view.selection():
                n = int(value)
                mappings[n] = labels[match_var.get()]
                view.set(value, "match", match_var.get())
        self.button(controls, "Assign", assign)
        ttk.Label(window, text="A catalogue match supplies metadata; it does not prove that a ZIP is authentic. Unknown compatibility is not a guarantee.", padding=(12, 2), wraplength=1000).pack(anchor="w")
        bottom = ttk.Frame(window, padding=12)
        bottom.pack(fill="x")
        def review():
            requests = [Selection(packages[int(n)], mappings[int(n)]) for n in view.selection()]
            settings = self.settings
            def show_plan(plan):
                lines = ["Close Microsoft Flight Simulator before changing scenery.\n"]
                for selection, row in zip(plan.selections, plan.rows):
                    old_version = row["old"]["version"] if row["old"] else "not installed"
                    lines.append(f"{row['action'].upper()}: {selection.package.title}\n"
                                 f"  {old_version} → {selection.package.version}\n  {row['target']}\n"
                                 f"  {'Active' if row['active'] else 'Remains disabled'}")
                lines += ["\nPlease review:", *plan.warnings] if plan.warnings else []
                confirm = tk.Toplevel(window)
                confirm.title("Confirm installation")
                confirm.geometry("800x560")
                confirm.transient(window)
                details = ScrolledText(confirm, wrap="word", font=("Segoe UI", 10))
                details.pack(fill="both", expand=True, padx=12, pady=12)
                write_text(details, "\n".join(lines))
                bar = ttk.Frame(confirm, padding=12)
                bar.pack(fill="x")
                def install():
                    confirm.destroy()
                    window.destroy()
                    self.run_task("Installing scenery — please wait…",
                        lambda: self.engine.install(plan.selections, settings, confirmed=True),
                        lambda records: self.finished_install(records))
                self.button(bar, "Confirm and install", install)
                self.button(bar, "Cancel", confirm.destroy)
            self.run_task("Checking installation plan…", lambda: self.engine.plan(requests, settings), show_plan)
        self.button(bottom, "Review installation…", review)
        self.button(bottom, "Cancel", window.destroy)

    def finished_install(self, records):
        self.refresh()
        self.tabs.select(self.installed_tab)
        self.status.set(f"Installed/updated {len(records)} package folder(s)")

    def build_installed(self):
        toolbar = ttk.Frame(self.installed_tab)
        toolbar.pack(fill="x", pady=(0, 10))
        self.button(toolbar, "Import / update from ZIP…", self.import_zips)
        self.button(toolbar, "Activate", lambda: self.toggle(True))
        self.button(toolbar, "Deactivate", lambda: self.toggle(False))
        self.button(toolbar, "Uninstall…", self.uninstall)
        self.button(toolbar, "Refresh", self.refresh)
        self.installed_view = table(self.installed_tab, [("name", "Installed package", 220), ("creator", "Creator", 130),
            ("version", "Installed version", 110), ("active", "Active", 65), ("method", "Method", 70), ("path", "Location", 350)], multiple=False)
        self.installed_view.bind("<<TreeviewSelect>>", lambda _: self.installed_details())
        self.installed_detail = ScrolledText(self.installed_tab, height=5, wrap="word", font=("Segoe UI", 10))
        self.installed_detail.pack(fill="x", pady=(10, 0))
        write_text(self.installed_detail, "Only installations owned by this manager are listed. Existing scenery and Addons Linker links are never adopted or replaced.")

    def selected_installation(self):
        ids = self.installed_view.selection()
        if not ids:
            raise SceneryError("Select an installed package first")
        return next(r for r in self.engine.records() if r["id"] == ids[0])

    def installed_details(self):
        if not self.installed_view.selection():
            return
        r = self.selected_installation()
        item = self.catalogue.packages.get(r["catalogue_id"])
        source = item["flightsim_to"]["url"] if item else r.get("source_url", "unknown")
        write_text(self.installed_detail, f"{r['title']} — {r['creator']}\nOriginal: {source}\n"
                   f"Community: {r['community']}\nArchive SHA-256: {r['sha256']}\n"
                   "Close the simulator before activating, deactivating, updating or uninstalling.")

    def toggle(self, active):
        record = self.selected_installation()
        self.run_task("Changing activation…", lambda: self.engine.set_active(record["id"], active), lambda _: self.refresh())

    def uninstall(self):
        record = self.selected_installation()
        if messagebox.askyesno("Uninstall scenery", f"Permanently remove {record['title']} {record['version']}?\n\n{record['path']}\n\nKeep your downloaded ZIP if you may want to reinstall it. Close MSFS first.", parent=self.root):
            self.run_task("Uninstalling scenery…", lambda: self.engine.uninstall(record["id"], confirmed=True), lambda _: self.refresh())

    def build_settings(self):
        self.community_var = tk.StringVar(value=self.settings.community)
        self.library_var = tk.StringVar(value=self.settings.library)
        self.method_var = tk.StringVar(value=self.settings.method)
        ttk.Label(self.settings_tab, text="Installation folders", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 15))
        for title, var in (("MSFS Community / Community2024 folder", self.community_var), ("Separate scenery library (linked mode)", self.library_var)):
            ttk.Label(self.settings_tab, text=title).pack(anchor="w")
            row = ttk.Frame(self.settings_tab)
            row.pack(fill="x", pady=(4, 15))
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=(0, 8))
            def browse(variable=var):
                folder = filedialog.askdirectory(parent=self.root, mustexist=False)
                if folder:
                    variable.set(folder)
            self.button(row, "Browse…", browse)
        row = ttk.Frame(self.settings_tab)
        row.pack(fill="x", pady=8)
        self.button(row, "Find MSFS folders", self.detect)
        ttk.Label(self.settings_tab, text="Default installation method").pack(anchor="w", pady=(18, 8))
        ttk.Radiobutton(self.settings_tab, text="Direct — place packages in Community; move disabled packages out of it", variable=self.method_var, value="direct").pack(anchor="w", pady=4)
        ttk.Radiobutton(self.settings_tab, text="Linked — store packages in the scenery library and activate with directory junctions", variable=self.method_var, value="linked").pack(anchor="w", pady=4)
        ttk.Label(self.settings_tab, text="Settings apply to new installations. Existing installations retain their recorded locations.\n"
                  "Choose the correct folder yourself if detection is unavailable. MSFS does not need to be installed.\n"
                  "Use a local NTFS drive for junctions. Other Addons Linker installations remain independent.", wraplength=850).pack(anchor="w", pady=20)
        save = ttk.Frame(self.settings_tab)
        save.pack(fill="x")
        self.button(save, "Save settings", self.save_settings)
        ttk.Label(self.settings_tab, text=f"Application data and logs: {self.directory}", wraplength=850).pack(anchor="w", pady=25)

    def save_settings(self):
        settings = Settings(self.community_var.get().strip(), self.library_var.get().strip(), self.method_var.get())
        settings.save(self.directory / "settings.json")
        self.settings = settings
        self.status.set("Settings saved")

    def detect(self):
        candidates = discover_community()
        if not candidates:
            messagebox.showinfo("No folders found", "Browse to your Community or Community2024 folder manually. You can also use an empty test folder.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Choose a detected folder")
        choice = tk.StringVar(value=str(candidates[0]))
        for path in candidates:
            ttk.Radiobutton(window, text=str(path), variable=choice, value=str(path)).pack(anchor="w", padx=14, pady=8)
        def choose():
            self.community_var.set(choice.get())
            window.destroy()
        self.button(window, "Use selected folder", choose, pady=14, padx=14)

    def build_logs(self):
        row = ttk.Frame(self.logs_tab)
        row.pack(fill="x", pady=(0, 8))
        self.button(row, "Refresh log", self.refresh_logs)
        self.logs = ScrolledText(self.logs_tab, wrap="word", font=("Consolas", 10))
        self.logs.pack(fill="both", expand=True)

    def refresh_logs(self):
        path = self.directory / "manager.log"
        text = path.read_text("utf-8", errors="replace")[-120_000:] if path.exists() else "No log entries yet."
        write_text(self.logs, text)

    def refresh(self):
        self.refresh_catalogue()
        selected = self.installed_view.selection()
        self.installed_view.delete(*self.installed_view.get_children())
        for record in self.engine.records():
            self.installed_view.insert("", "end", iid=record["id"], values=(record["title"], record["creator"],
                record["version"], "Yes" if record["active"] else "No", record["method"], record["path"]))
        self.installed_view.selection_set([s for s in selected if self.installed_view.exists(s)])
        self.refresh_logs()
