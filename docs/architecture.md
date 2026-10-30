# Architecture, ownership and recovery

| Module | Responsibility |
| --- | --- |
| `gui.py` | Tk/ttk catalogue, settings, ZIP preview and installed-package controls |
| `catalogue.py` + JSON Schema | Offline metadata validation, identity matching, relationships |
| `providers.py` | Local ZIP import, safe original-page opening; future approved-API protocol |
| `archive.py`, `paths.py` | Windows path validation, ZIP limits, MSFS package detection and extraction |
| `engine.py` | Plans, ownership/integrity checks, install/update/activation/uninstall |
| `state.py` | SQLite installations, atomic JSON writes and cross-process writer lock |
| `transaction.py` | Write-ahead filesystem journal coordinated with SQLite commit markers |
| `links.py` | Native Windows directory junctions and non-traversing cleanup |
| `discovery.py` | Steam/Store UserCfg discovery and explicit installation settings |

## Install/update sequence

1. Inspect all archive paths before extracting anything. Reject traversal,
   absolute/drive/UNC paths, alternate data streams, reserved Windows names,
   duplicate or case-colliding names, symlinks/special files, encryption and
   unsupported compression. Apply expanded-size, ratio and file-count limits.
2. Detect a package only when `manifest.json` and `layout.json` share a root.
   Check required manifest strings and the size/existence of layout files.
   Reject nested package roots. Wrapper/readme files outside package roots are
   not installed. A root-only ZIP gets a stable creator/title-derived folder.
3. Plan all selected packages. Match only a unique verified folder name or an
   exact normalised title+creator; otherwise require a deliberate manual match
   or leave the package local/unmatched. Check known hashes and relationships.
4. The user reviews all destinations, old/new archive versions and warnings.
   Revalidate the plan under the single-writer lock when confirmed.
5. Create private same-volume staging. Re-hash the open ZIP handle to detect
   changes after preview, then stream extraction and CRC validation. No content
   is executed. Complete **all selected payloads** before moving old packages.
6. Before each rename, atomically persist a journal entry. Move old managed
   packages to rollback storage and move staged packages into their destinations.
7. Commit new records and the operation ID together in one SQLite transaction.
   Only then remove backups and the journal. Cleanup failure leaves the committed
   result in place and is retried during recovery.

On startup, an operation without a SQLite commit marker is rolled back in reverse
order. An operation with that marker finishes cleanup. Each undone step is removed
from the journal, so recovery itself can be interrupted and resumed. If filesystem
state is ambiguous, recovery stops and preserves both locations and the journal.

## Ownership and coexistence

An installed folder has an unguessable record ID in `.nvfr-owner.json`. Before
modifying it, the engine checks its recorded path, marker, full per-file hash
inventory and absence of reparse points within the payload. Missing/extra/changed
files stop the operation. Unmanaged folders and junctions are never adopted,
deleted or overwritten. Root markers prevent two different manager databases
from claiming the same configured root.

The app does not read or edit MSFS Addons Linker configuration. It owns only the
activation paths it created. Use only one manager to activate a particular package;
external changes to an active link cause a clear conflict. Other tools can manage
different packages in the same Community folder.

## Recovery troubleshooting

1. Close MSFS and other tools modifying the affected folders.
2. Preserve `%LOCALAPPDATA%\NorwayVFR`, the journal named in the error, and the
   corresponding `.nvfr-manager` directory. **Do not delete the database** to
   dismiss a recovery warning.
3. Read `manager.log`. Restore externally moved/modified files or activation
   links to their recorded state, then restart the app to retry recovery.
4. If state remains ambiguous, back up both locations before manual investigation.
   There is deliberately no destructive “force recover” button.

The transaction protects normal failures and process interruption. It does not
replace backups or promise recovery from hardware/filesystem corruption or a
hostile process modifying the same files at exactly the same time. The supported
production filesystem is local Windows NTFS; Linux symlinks exercise the same
engine in development tests. Each activation/uninstall is one transaction;
all packages selected in a single ZIP import are committed or rolled back together.
