"""PyPI enrichment for Python package metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class PyPIPackageInfo:
    """Package information from PyPI."""

    name: str
    purl: str
    version: str | None = None
    license: str | None = None
    summary: str | None = None
    homepage: str | None = None
    author: str | None = None


class PyPIEnricher:
    """Enrich package metadata from PyPI API."""

    API_BASE = "https://pypi.org/pypi"
    TIMEOUT = 10

    def __init__(self) -> None:
        """Initialize enricher."""
        self._session = requests.Session()

    def lookup_package(self, name: str, version: str | None = None) -> PyPIPackageInfo | None:
        """Look up package metadata from PyPI.

        Args:
            name: Package name (e.g., "openai").
            version: Optional specific version.

        Returns:
            PyPIPackageInfo if found, None otherwise.
        """
        url = f"{self.API_BASE}/{name}/json"
        if version:
            url = f"{self.API_BASE}/{name}/{version}/json"

        try:
            resp = self._session.get(url, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                logger.debug("Package not found: %s", name)
                return None
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(name, data)
        except requests.RequestException as e:
            logger.warning("Failed to fetch package %s: %s", name, e)
            return None

    def _parse_response(self, name: str, data: dict) -> PyPIPackageInfo:
        """Parse PyPI API response."""
        info = data.get("info", {})

        version = info.get("version")
        purl = f"pkg:pypi/{name}"
        if version:
            purl = f"{purl}@{version}"

        # Get license - try classifier first, then license field
        license_id = None
        classifiers = info.get("classifiers", [])
        for classifier in classifiers:
            if classifier.startswith("License :: OSI Approved ::"):
                # Extract license name
                license_name = classifier.split("::")[-1].strip()
                # Map to SPDX
                license_id = self._map_to_spdx(license_name)
                break

        if not license_id:
            license_id = info.get("license")
            if license_id:
                license_id = self._map_to_spdx(license_id)

        # Get author - try multiple fields
        author = self._extract_author(info)

        return PyPIPackageInfo(
            name=name,
            purl=purl,
            version=version,
            license=license_id,
            summary=info.get("summary"),
            homepage=info.get("home_page") or info.get("project_url"),
            author=author,
        )

    def _extract_author(self, info: dict) -> str | None:
        """Extract author name from PyPI info.

        Tries multiple fields since modern packages (PEP 621) often use
        author_email in format "Name <email>" instead of separate author field.
        """
        # Try author field first
        if info.get("author"):
            return info["author"]

        # Try to extract from author_email ("Name <email>" format)
        author_email = info.get("author_email")
        if author_email:
            name = self._parse_name_from_email(author_email)
            if name:
                return name

        # Try maintainer fields as fallback
        if info.get("maintainer"):
            return info["maintainer"]

        maintainer_email = info.get("maintainer_email")
        if maintainer_email:
            name = self._parse_name_from_email(maintainer_email)
            if name:
                return name

        return None

    def _parse_name_from_email(self, email_field: str) -> str | None:
        """Parse name from 'Name <email>' format."""
        if not email_field:
            return None

        # Handle "Name <email>" format
        if "<" in email_field and ">" in email_field:
            name = email_field.split("<")[0].strip()
            if name:
                return name

        return None

    def _map_to_spdx(self, license_text: str) -> str | None:
        """Map license text to SPDX identifier."""
        if not license_text:
            return None

        text_lower = license_text.lower().strip()

        # Common mappings
        mappings = {
            "mit license": "MIT",
            "mit": "MIT",
            "apache software license": "Apache-2.0",
            "apache 2.0": "Apache-2.0",
            "apache-2.0": "Apache-2.0",
            "bsd license": "BSD-3-Clause",
            "bsd-3-clause": "BSD-3-Clause",
            "bsd 3-clause": "BSD-3-Clause",
            "gnu general public license v3": "GPL-3.0-only",
            "gpl-3.0": "GPL-3.0-only",
            "isc license": "ISC",
            "isc": "ISC",
            "mozilla public license 2.0": "MPL-2.0",
        }

        return mappings.get(text_lower, license_text)
