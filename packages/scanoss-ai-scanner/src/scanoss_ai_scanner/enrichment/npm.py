"""npm registry enrichment for JavaScript package metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class NpmPackageInfo:
    """Package information from npm."""

    name: str
    purl: str
    version: str | None = None
    license: str | None = None
    description: str | None = None
    homepage: str | None = None
    author: str | None = None


class NpmEnricher:
    """Enrich package metadata from npm registry API."""

    API_BASE = "https://registry.npmjs.org"
    TIMEOUT = 10

    def __init__(self) -> None:
        """Initialize enricher."""
        self._session = requests.Session()

    def lookup_package(self, name: str, version: str | None = None) -> NpmPackageInfo | None:
        """Look up package metadata from npm.

        Args:
            name: Package name (e.g., "openai", "@anthropic-ai/sdk").
            version: Optional specific version.

        Returns:
            NpmPackageInfo if found, None otherwise.
        """
        # Handle scoped packages
        encoded_name = name.replace("/", "%2F")
        url = f"{self.API_BASE}/{encoded_name}"

        try:
            resp = self._session.get(url, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                logger.debug("Package not found: %s", name)
                return None
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(name, data, version)
        except requests.RequestException as e:
            logger.warning("Failed to fetch package %s: %s", name, e)
            return None

    def _parse_response(
        self, name: str, data: dict, version: str | None = None
    ) -> NpmPackageInfo:
        """Parse npm API response."""
        # Get latest version if not specified
        if not version:
            version = data.get("dist-tags", {}).get("latest")

        # Get version-specific info
        versions = data.get("versions", {})
        version_info = versions.get(version, {}) if version else {}

        # Build PURL
        purl = f"pkg:npm/{name}"
        if version:
            purl = f"{purl}@{version}"

        # Get license
        license_id = version_info.get("license") or data.get("license")
        if isinstance(license_id, dict):
            license_id = license_id.get("type")
        license_id = self._normalize_license(license_id)

        # Get author
        author = version_info.get("author") or data.get("author")
        if isinstance(author, dict):
            author = author.get("name")

        return NpmPackageInfo(
            name=name,
            purl=purl,
            version=version,
            license=license_id,
            description=version_info.get("description") or data.get("description"),
            homepage=version_info.get("homepage") or data.get("homepage"),
            author=author,
        )

    def _normalize_license(self, license_id: str | None) -> str | None:
        """Normalize license to SPDX identifier."""
        if not license_id:
            return None

        # npm usually uses SPDX identifiers directly
        # Just normalize casing for common ones
        mappings = {
            "mit": "MIT",
            "isc": "ISC",
            "apache-2.0": "Apache-2.0",
            "bsd-3-clause": "BSD-3-Clause",
            "gpl-3.0": "GPL-3.0-only",
        }

        return mappings.get(license_id.lower(), license_id)
