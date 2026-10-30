import json
import zipfile

import pytest

from nvfr.catalogue import Catalogue
from nvfr.discovery import Settings
from nvfr.engine import Engine
from nvfr.state import State


def catalogue_item(identifier="test-airport", name="Test Airport", developer="Test Developer"):
    return {
        "id": identifier, "name": name, "developer": developer,
        "description": "Synthetic test scenery; not a real download", "category": "airport",
        "flightsim_to": {"id": 123, "url": "https://flightsim.to/file/123/synthetic-test"},
        "version": "unknown", "last_verified": "unknown",
        "compatibility": {"msfs2020": "unknown", "msfs2024": "unknown"},
        "geography": {"country": "Norway", "region": "unknown", "coordinates": "unknown"},
        "dependencies": "unknown", "conflicts": "unknown",
        "license": {"name": "unknown", "url": "unknown", "redistribution": "unknown"},
        "attribution": developer, "installation": {"folder_names": "unknown", "notes": "unknown"},
        "sha256": "unknown", "verification": {"status": "unverified", "sources": []},
    }


def catalogue_doc(*items):
    return {"schema_version": "1.0", "catalogue_id": "synthetic-tests", "title": "Tests",
            "updated_at": "2026-10-30", "packages": list(items)}


@pytest.fixture
def make_zip(tmp_path):
    count = 0

    def make(*folders, version="1.0.0", payload=b"synthetic scenery", extra=None, root_prefix="wrapper"):
        nonlocal count
        count += 1
        path = tmp_path / f"import-{count}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder in folders or ("test-airport",):
                root = "/".join(p for p in (root_prefix, folder) if p)
                root = root + "/" if root else ""
                zf.writestr(root + "manifest.json", json.dumps({
                    "title": "Test Airport" if folder in ("test-airport", "") else folder,
                    "creator": "Test Developer", "package_version": version, "content_type": "SCENERY",
                }))
                zf.writestr(root + "layout.json", json.dumps({"content": [
                    {"path": "scenery/test.bgl", "size": len(payload), "date": 0}]}))
                zf.writestr(root + "scenery/test.bgl", payload)
            for name, value in (extra or {}).items():
                zf.writestr(name, value)
        return path
    return make


@pytest.fixture
def engine(tmp_path):
    return Engine(State(tmp_path / "state"), Catalogue([catalogue_doc(catalogue_item())]))


@pytest.fixture
def settings(tmp_path):
    return Settings(str(tmp_path / "Community"), str(tmp_path / "Addons"), "direct")
