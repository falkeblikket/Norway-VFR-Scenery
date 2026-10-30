"""Download-source boundary. v0.1 makes no HTTP requests and handles no credentials."""

from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
import re
import webbrowser

from .archive import Package, inspect_zip
from .errors import SceneryError


class LocalZipSource:
    def inspect(self, paths: list[Path]) -> list[Package]:
        return [package for path in dict.fromkeys(paths) for package in inspect_zip(path)]


class BrowserSource:
    def open_original(self, url: str) -> bool:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "flightsim.to"
                or not re.fullmatch(r"/(?:file|addon)/[0-9]+/[^/]+", parsed.path)
                or parsed.query or parsed.fragment):
            raise SceneryError("Expected an original HTTPS Flightsim.to file page")
        return webbrowser.open(url, new=2)


class ApprovedApiSource(Protocol):
    """Future contract only. Implement after written provider approval.

    Authentication must use the provider's approved system-browser flow and OS
    credential storage. Downloaded files still go through inspect_zip + staging.
    No implementation or unofficial API endpoints are included in this release.
    """

    def authenticate(self) -> None: ...
    def available_version(self, provider_id: str) -> str: ...
    def download(self, provider_id: str, destination: Path) -> Path: ...
    def sign_out(self) -> None: ...
