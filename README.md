# Norway VFR Scenery Manager 0.1

A small Windows scenery catalogue and local ZIP installer for **Microsoft Flight
Simulator 2024**, with Norwegian and Nordic VFR scenery as its starting point.

Browse **95 ErikHanoy packages** and **258 other Norwegian freeware packages**,
open their original Flightsim.to pages, download in your own browser, and import
the ZIP files. Scenery files are not bundled or redistributed. No Flightsim.to
credentials, cookies, browser automation or automatic downloads are used.

## Run on Windows 11

1. Open [Actions](https://github.com/falkeblikket/Norway-VFR-Scenery/actions) and
   select a successful **Test and build Windows application** run for this PR.
2. Download the **NorwayVFR-0.1.0-Windows-x64** artifact (GitHub sign-in may be
   required). Extract the artifact ZIP and the contained portable application ZIP.
3. Keep the entire `NorwayVFR` folder together and run **NorwayVFR.exe**.
   No Python, development tools, administrator rights or MSFS installation is
   needed. The build is unsigned; Windows may show an unrecognised-app prompt.
   Only run a build you trust from this repository's successful workflow.
4. In **Settings**, choose your actual **Community** or **Community2024** folder.
   **Find MSFS folders** reads known Steam/Store `UserCfg.opt` locations. Custom
   or changed simulator paths can always be selected with **Browse**.
5. Select **Direct**, or **Linked** with a separate local scenery library such as
   `D:\FlightSim\Addons\Norway`. Save settings.

Use an empty test folder to try the application without MSFS. Close the simulator
before changing scenery. A simulator restart may be needed to load changes.

## Install and manage scenery

1. Filter **Catalogue** by creator, area or category. Select one or more rows and
   choose **Open original page(s)**. Creator attribution and verification details
   appear below the list.
2. Download ZIPs using the normal Flightsim.to website. Read the creator's
   instructions, including prerequisites and optional variants.
3. Choose **Import downloaded ZIPs**, select the archives, then review the
   detected package folders. Multiple packages and wrapper directories are supported.
4. Review automatic title/creator or verified folder matches. Use **Assign** for
   a deliberate manual match, or leave the package unmatched. Import works without
   a catalogue match; unavailable metadata is explicitly unknown.
5. Select only the wanted package folders. Choose **Review installation** and
   then **Confirm and install**. Updates show old/new archive versions and paths.
6. Use **Installed** to activate, deactivate or uninstall a managed package.
   Import a newly downloaded ZIP to update it. Updates retain activation state.

**Listed version** is a catalogue snapshot; **Installed version** is read from
the ZIP's MSFS manifest. The app does not claim that an imported ZIP is the newest
release. Same-ZIP imports are rejected as already installed. Every replacement
and removal needs explicit confirmation. Files modified outside the manager are
protected even after confirmation; back up and restore them before retrying.

In direct mode, disabled packages move to a managed directory **outside** Community.
In linked mode, package files remain in the scenery library and Windows directory
junctions activate them. Junction creation uses the Windows API without a shell;
Developer Mode is not required on supported local NTFS volumes.

## Catalogue maintenance

The bundled JSON catalogues and their JSON Schema are under `src/nvfr/data/`.
Use **Load catalogue JSON** to add/replace metadata without changing the program.
Local catalogues with the same catalogue ID override bundled versions. Invalid
files and duplicate package identities are rejected before replacement.

See [manifest format](docs/manifest.md), [adding scenery](docs/contributing-catalogues.md),
and [source verification](docs/catalogue-provenance.md). Freeware does **not** imply
an open licence or permission to redistribute. The shipped catalogue records do
not assert any such permission.

## Local data and recovery

Windows settings, catalogue overrides, SQLite database and rotating logs live in
`%LOCALAPPDATA%\NorwayVFR`. **Logs** displays the latest installation log.
Original ZIPs are not changed or deleted. Back up this data directory together
with the managed scenery directories; the database is the ownership record.

Private staging, rollback backups and directly disabled packages live in
`.nvfr-manager/<root-id>/` beside each configured scenery root. Do not delete this
directory: it may contain your disabled scenery. The GUI displays the actual
location of every installed package. Interrupted operations are recovered on the
next start before further changes. See [architecture and recovery](docs/architecture.md).

## Development and tests

Python 3.12+ with Tk is required for source execution. On Windows, install Python
from python.org with Tcl/Tk support. On Linux the GUI also needs a display.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m nvfr
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check src tests scripts
.venv\Scripts\python scripts\validate_catalogues.py
.venv\Scripts\python scripts\build_windows.py
```

Tests use only synthetic packages. CI runs on Linux and Windows, exercises the
GUI workflow and native Windows junctions, builds a portable Windows application,
then starts the actual packaged executable and checks its bundled catalogue.
For isolated source experiments: `python -m nvfr --data-dir C:\Temp\NVFR-TestState`.

## Scope and limitations

Read [known limitations](docs/limitations.md) before using v0.1. It is intentionally
a local ZIP manager. ZIP validation is not malware scanning, a copyright licence,
or a guarantee of simulator compatibility. The application never executes archive
code; MSFS can load add-on code when you subsequently run the simulator.

The program uses the [MIT licence](LICENSE). Original scenery remains the property
of its creators. See [third-party notices](THIRD_PARTY_NOTICES.md).
