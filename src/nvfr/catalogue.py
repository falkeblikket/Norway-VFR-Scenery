"""Versioned, independently replaceable catalogues. Unknown is never inferred away."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .archive import Package
from .errors import SceneryError
from .paths import name_key, safe_folder
from .state import atomic_json


def validate(data: dict) -> None:
    schema = json.loads(files("nvfr").joinpath("data/catalogue.schema.json").read_text("utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data),
                    key=lambda error: str(error.path))
    if errors:
        first = errors[0]
        raise SceneryError(f"Invalid catalogue at {'/'.join(map(str, first.path))}: {first.message}")
    seen = set()
    for item in data["packages"]:
        if item["id"] in seen:
            raise SceneryError(f"Duplicate catalogue package ID: {item['id']}")
        seen.add(item["id"])
        source = item["flightsim_to"]
        page_id = int(source["url"].split("/")[4])
        if source["id"] != "unknown" and source["id"] != page_id:
            raise SceneryError(f"Flightsim.to ID and URL disagree: {item['id']}")
        folders = item["installation"]["folder_names"]
        if folders != "unknown":
            for folder in folders:
                safe_folder(folder)
        for field in ("dependencies", "conflicts"):
            if item[field] != "unknown" and item["id"] in item[field]:
                raise SceneryError(f"Package cannot list itself in {field}")


def read_catalogue(path: Path) -> dict:
    try:
        if path.stat().st_size > 16 * 1024**2:
            raise SceneryError("Catalogue is larger than 16 MiB")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        validate(data)
        return data
    except (OSError, ValueError) as exc:
        raise SceneryError(f"Cannot load catalogue {path}: {exc}") from exc


class Catalogue:
    def __init__(self, documents: list[dict]):
        self.documents = documents
        self.packages = {}
        ids = set()
        for data in documents:
            validate(data)
            if data["catalogue_id"] in ids:
                raise SceneryError(f"Duplicate catalogue ID: {data['catalogue_id']}")
            ids.add(data["catalogue_id"])
            for item in data["packages"]:
                if item["id"] in self.packages:
                    raise SceneryError(f"Package appears in multiple catalogues: {item['id']}")
                self.packages[item["id"]] = item

    @classmethod
    def load(cls, user_directory: Path):
        documents = {}
        for resource in files("nvfr").joinpath("data/catalogues").iterdir():
            if resource.name.endswith(".json"):
                data = json.loads(resource.read_text("utf-8"))
                validate(data)
                documents[data["catalogue_id"]] = data
        if user_directory.exists():
            user_ids = set()
            for path in sorted(user_directory.glob("*.json")):
                data = read_catalogue(path)
                if data["catalogue_id"] in user_ids:
                    raise SceneryError("Two local files declare the same catalogue ID")
                user_ids.add(data["catalogue_id"])
                documents[data["catalogue_id"]] = data
        return cls(list(documents.values()))

    def import_file(self, source: Path, directory: Path, *, confirmed: bool = False):
        if not confirmed:
            raise SceneryError("Confirm catalogue import before replacing local metadata")
        data = read_catalogue(source)
        combined = [d for d in self.documents if d["catalogue_id"] != data["catalogue_id"]]
        updated = Catalogue(combined + [data])  # Validate all IDs before the write.
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(directory / (data["catalogue_id"] + ".json"), data)
        return updated

    def match(self, package: Package) -> tuple[str | None, str]:
        exact = []
        def norm(text):
            return re.sub(r"\s+", " ", text.strip()).casefold()
        for item in self.packages.values():
            folders = item["installation"]["folder_names"]
            if folders != "unknown" and name_key(package.folder) in {name_key(f) for f in folders}:
                exact.append((item["id"], "catalogue directory name"))
            elif norm(package.title) == norm(item["name"]) and norm(package.creator) == norm(item["developer"]):
                exact.append((item["id"], "title and creator"))
        if len(exact) == 1:
            return exact[0]
        return None, "ambiguous match" if exact else "not matched; local package"

    def check_relationships(self, active_ids: set[str]) -> list[str]:
        warnings = []
        for key in sorted(active_ids):
            item = self.packages.get(key)
            if not item:
                warnings.append(f"No catalogue dependency/conflict information for {key}")
                continue
            deps, conflicts = item["dependencies"], item["conflicts"]
            if deps == "unknown" or conflicts == "unknown":
                warnings.append(f"Dependencies/conflicts have not been verified for {item['name']}")
            if deps != "unknown":
                missing = set(deps) - active_ids
                if missing:
                    raise SceneryError(f"Missing active dependencies for {item['name']}: {', '.join(sorted(missing))}")
            if conflicts != "unknown":
                found = set(conflicts) & active_ids
                if found:
                    raise SceneryError(f"Known conflict involving {item['name']}: {', '.join(sorted(found))}")
        return warnings
