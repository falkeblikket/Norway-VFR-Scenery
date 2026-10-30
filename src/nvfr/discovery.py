"""Conservative Community discovery. The user always chooses the actual folder."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import SceneryError
from .paths import absolute_directory
from .state import atomic_json


def app_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "NorwayVFR"
    return Path.home() / ".local/share/norway-vfr"


def discover_community(environment: dict | None = None) -> list[Path]:
    env = os.environ if environment is None else environment
    configs = []
    if env.get("APPDATA"):
        roaming = Path(env["APPDATA"])
        configs += [roaming / title / "UserCfg.opt" for title in (
            "Microsoft Flight Simulator 2024", "Microsoft Flight Simulator")]
    if env.get("LOCALAPPDATA"):
        local = Path(env["LOCALAPPDATA"])
        configs += [local / "Packages" / title / "LocalCache/UserCfg.opt" for title in (
            "Microsoft.Limitless_8wekyb3d8bbwe", "Microsoft.FlightSimulator_8wekyb3d8bbwe")]
    candidates = []
    for config in configs:
        if not config.is_file():
            continue
        try:
            raw = config.read_bytes()
            text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
            match = re.search(r'^\s*InstalledPackagesPath\s+"([^"\r\n]+)"', text, re.MULTILINE)
            if match:
                root = Path(os.path.expandvars(match[1]))
                for name in ("Community", "Community2024"):
                    path = root / name
                    if path.is_dir() and path not in candidates:
                        candidates.append(path)
        except (OSError, UnicodeError):
            continue
    return candidates


@dataclass(frozen=True)
class Settings:
    community: str = ""
    library: str = ""
    method: str = "direct"

    def roots(self) -> tuple[Path, Path]:
        if not self.community:
            raise SceneryError("Choose a Community or Community2024 folder in Settings")
        if self.method not in ("direct", "linked"):
            raise SceneryError("Installation method must be direct or linked")
        community = absolute_directory(Path(self.community))
        if self.method == "direct":
            return community, community
        if not self.library:
            raise SceneryError("Choose a local scenery library for linked installation")
        library = absolute_directory(Path(self.library))
        if library == community or library in community.parents or community in library.parents:
            raise SceneryError("Community and scenery library must be separate, non-nested directories")
        return community, library

    def save(self, path: Path):
        self.roots()
        atomic_json(path, asdict(self))

    @classmethod
    def load(cls, path: Path):
        import json
        if not path.exists():
            return cls()
        try:
            return cls(**json.loads(path.read_text("utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise SceneryError(f"Cannot read settings: {exc}") from exc
