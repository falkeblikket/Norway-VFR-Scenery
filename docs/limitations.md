# Known limitations in v0.1

- No automatic download, login, cookie access, browser automation or online
  version checks. The `ApprovedApiSource` protocol has no implementation until
  Flightsim.to approves an integration. Existing providers need no credentials.
- No scenery assets are shipped. Listed versions are source snapshots; all
  compatibility is reported/unknown until documented independent testing.
- ZIP only (stored/deflate); no RAR/7z, split archives, encrypted ZIPs, installers
  or scripts. Limits: 100,000 entries, 32 GiB expanded total, 8 GiB per file,
  compression ratio 1000:1, and 16 MiB per metadata JSON. Large legitimate files
  beyond these limits need a reviewed future change, not a bypass button.
- Only package roots with valid manifest/layout files are installable. Downloads
  requiring changes outside Community, special configuration steps, optional
  replacement files or manual merging are not automatically supported.
- No arbitrary existing-file replacement or unmanaged-installation adoption.
  Manually modified managed packages are blocked until restored. Renamed package
  folders need explicit removal/reinstallation rather than an inferred migration.
- No automatic catalogue match based on ZIP filenames or fuzzy title similarity.
  Creator strings in an MSFS manifest may differ from listing usernames: inspect
  and assign deliberately in the preview. Checksums are unknown in the initial
  catalogues, so matching is not authenticity verification.
- Unknown dependencies/conflicts are warnings, not proof of compatibility.
  Known dependency requirements only count active packages recorded by this app
  in the same Community. Dependencies installed by another tool need separate
  consideration; external filesystem scanning is not implemented.
- Direct and linked modes cannot be switched in place for an existing package.
  Settings changes apply to new installations. Keep your ZIP and uninstall/reinstall
  if moving a package to a different root or method.
- Junction activation is intended for local Windows NTFS drives. UNC/network
  library targets are rejected in linked mode. If link creation is unsupported,
  the whole install rolls back; choose direct mode. Linked ancestors in configured
  paths are rejected, so select the real destination folder.
- Addons Linker config is untouched. Do not use two tools to control the same
  activation link, and do not point it at the manager's private `.nvfr-manager`
  staging/disabled directories.
- Steam/Store detection is heuristic and depends on known `UserCfg.opt` locations;
  manual folder selection is always available. Nothing changes simulator configs.
- No map, profiles, dependency auto-install, directory watcher, multiversion
  catalogue channels, telemetry or background network requests.
- Portable builds are unsigned. CI runs on GitHub's Windows runner (Windows Server),
  which does not replace a manual Windows 11 + MSFS flight test. Actual scenery,
  unusual security software, network filesystems and long-path configurations
  need user testing. A long/path/permission failure should roll back safely.
- SQLite and private staging state are essential ownership/recovery information.
  Do not delete them while scenery is installed. There is no database-loss
  adoption/reconstruction tool in this release.
