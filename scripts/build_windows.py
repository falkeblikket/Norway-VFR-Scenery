"""Build on Windows; no cross-compilation or downloaded scenery content."""
from importlib import metadata
from pathlib import Path
import os
import shutil
import subprocess
import sys


def main():
    if os.name != "nt":
        raise SystemExit("Build this application on Windows (or use the GitHub Actions artifact).")
    root = Path(__file__).resolve().parents[1]
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "NorwayVFR", "--paths", str(root / "src"), "--collect-data", "nvfr",
        "--collect-data", "jsonschema_specifications", str(root / "scripts/launch.py"),
    ], cwd=root, check=True)
    destination = root / "dist/NorwayVFR"
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / name, destination / name)
    shutil.copytree(root / "docs", destination / "docs", dirs_exist_ok=True)
    licenses = destination / "third-party-licenses"
    licenses.mkdir(exist_ok=True)
    for name in ("jsonschema", "jsonschema-specifications", "referencing", "rpds-py", "attrs", "pyinstaller"):
        dist = metadata.distribution(name)
        for file in dist.files or []:
            if any(part.lower().startswith(("license", "copying")) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, licenses / (name + "-" + source.name))
    for name in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / name
        if source.exists():
            shutil.copy2(source, licenses / ("Python-" + name))
    for source in (Path(sys.base_prefix) / "tcl").rglob("license*"):
        if source.is_file():
            shutil.copy2(source, licenses / ("TclTk-" + source.parent.name + "-" + source.name))
    print(f"Portable application: {destination / 'NorwayVFR.exe'}")


if __name__ == "__main__":
    main()
