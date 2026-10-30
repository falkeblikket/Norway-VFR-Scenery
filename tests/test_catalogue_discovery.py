import copy
import json

import pytest

from conftest import catalogue_doc, catalogue_item
from nvfr.archive import inspect_zip
from nvfr.catalogue import Catalogue, validate
from nvfr.discovery import Settings, discover_community
from nvfr.errors import SceneryError
from nvfr.providers import BrowserSource


def test_catalogue_schema_unknowns_duplicate_and_bad_version():
    doc = catalogue_doc(catalogue_item())
    validate(doc)
    for field, value in [("schema_version", "2"), ("updated_at", "2026-99-99")]:
        invalid = copy.deepcopy(doc)
        invalid[field] = value
        with pytest.raises(SceneryError):
            validate(invalid)
    doc["packages"].append(copy.deepcopy(doc["packages"][0]))
    with pytest.raises(SceneryError):
        validate(doc)


def test_id_url_disagreement_and_windows_folder_name():
    item = catalogue_item()
    item["flightsim_to"]["id"] = 456
    with pytest.raises(SceneryError, match="disagree"):
        validate(catalogue_doc(item))
    item["flightsim_to"]["id"] = 123
    item["installation"]["folder_names"] = ["../escape"]
    with pytest.raises(SceneryError):
        validate(catalogue_doc(item))


def test_exact_and_ambiguous_matching(make_zip):
    package = inspect_zip(make_zip())[0]
    a = catalogue_item()
    catalogue = Catalogue([catalogue_doc(a)])
    assert catalogue.match(package) == ("test-airport", "title and creator")
    b = catalogue_item("duplicate-title")
    assert Catalogue([catalogue_doc(a, b)]).match(package)[0] is None


def test_independent_catalogue_import(engine, tmp_path):
    source = tmp_path / "catalogue.json"
    doc = catalogue_doc(catalogue_item())
    doc["packages"][0]["version"] = "2.1"
    source.write_text(json.dumps(doc))
    with pytest.raises(SceneryError, match="Confirm"):
        engine.catalogue.import_file(source, tmp_path / "catalogues")
    updated = engine.catalogue.import_file(source, tmp_path / "catalogues", confirmed=True)
    assert updated.packages["test-airport"]["version"] == "2.1"
    assert engine.records() == []


@pytest.mark.parametrize("platform", ["steam", "store"])
def test_discovery_custom_packages_path_and_both_community_names(tmp_path, platform):
    roaming, local = tmp_path / "roaming", tmp_path / "local"
    packages = tmp_path / "custom-packages"
    (packages / "Community").mkdir(parents=True)
    (packages / "Community2024").mkdir()
    config = (roaming / "Microsoft Flight Simulator 2024/UserCfg.opt" if platform == "steam" else
              local / "Packages/Microsoft.Limitless_8wekyb3d8bbwe/LocalCache/UserCfg.opt")
    config.parent.mkdir(parents=True)
    config.write_text(f'Version 1\nInstalledPackagesPath "{packages}"\n')
    assert discover_community({"APPDATA": str(roaming), "LOCALAPPDATA": str(local)}) == [
        packages / "Community", packages / "Community2024"]
    assert discover_community({}) == []


def test_settings_reject_overlapping_locations(tmp_path):
    with pytest.raises(SceneryError, match="separate"):
        Settings(str(tmp_path / "Community"), str(tmp_path / "Community/addons"), "linked").roots()


def test_browser_source_allowlist(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, new: opened.append(url) or True)
    source = BrowserSource()
    for url in ["file:///etc/passwd", "https://flightsim.to.evil/file/1/x", "https://evil.com/file/x", "https://user@flightsim.to/file/1/x"]:
        with pytest.raises(SceneryError):
            source.open_original(url)
    assert opened == []
    assert source.open_original("https://flightsim.to/file/123/example")
    assert len(opened) == 1
