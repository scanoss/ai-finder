"""npm crawler for AI package metadata."""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Known AI packages to crawl
AI_PACKAGES = [
    "openai",
    "@anthropic-ai/sdk",
    "@langchain/core",
    "@langchain/openai",
    "@langchain/anthropic",
    "langchain",
    "llamaindex",
    "@huggingface/inference",
    "@huggingface/hub",
    "ai",  # Vercel AI SDK
    "@ai-sdk/openai",
    "@ai-sdk/anthropic",
    "cohere-ai",
    "replicate",
    "@google/generative-ai",
    "@tensorflow/tfjs",
    "onnxruntime-web",
    "onnxruntime-node",
    "@pinecone-database/pinecone",
    "chromadb",
    "weaviate-ts-client",
    "@qdrant/js-client-rest",
]


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    packages_added: int = 0
    packages_updated: int = 0
    errors: list[str] = field(default_factory=list)


class NpmCrawler:
    """Crawler for npm AI packages."""

    API_BASE = "https://registry.npmjs.org"
    RATE_LIMIT_DELAY = 0.2

    def __init__(self, db_path: Path, verbose: bool = False) -> None:
        """Initialize crawler.

        Args:
            db_path: Path to KB database.
            verbose: Enable verbose output.
        """
        self.db_path = db_path
        self.verbose = verbose
        self._session = requests.Session()

    def crawl(self, packages: list[str] | None = None) -> CrawlResult:
        """Crawl npm for AI packages.

        Args:
            packages: List of packages to crawl. Defaults to AI_PACKAGES.

        Returns:
            CrawlResult with statistics.
        """
        result = CrawlResult()
        packages = packages or AI_PACKAGES

        self._log(f"Crawling {len(packages)} packages")

        for name in packages:
            try:
                if self._crawl_package(name):
                    result.packages_added += 1
                    self._log(f"Added: {name}")
                time.sleep(self.RATE_LIMIT_DELAY)
            except Exception as e:
                result.errors.append(f"{name}: {e}")

        self._log(f"Crawl complete: {result.packages_added} packages")
        return result

    def _crawl_package(self, name: str) -> bool:
        """Crawl a single package."""
        # Handle scoped packages
        encoded_name = name.replace("/", "%2F")
        url = f"{self.API_BASE}/{encoded_name}"

        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 404:
                self._log(f"Not found: {name}")
                return False
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            self._log(f"Failed {name}: {e}")
            return False

        # Get latest version
        version = data.get("dist-tags", {}).get("latest")
        versions = data.get("versions", {})
        version_info = versions.get(version, {}) if version else {}

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

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO packages (
                        purl, name, ecosystem, version, license, summary,
                        homepage, author, is_ai_package, ai_category, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'crawled')
                    ON CONFLICT(purl) DO UPDATE SET
                        version = excluded.version,
                        license = COALESCE(excluded.license, license),
                        summary = excluded.summary,
                        homepage = excluded.homepage,
                        author = excluded.author,
                        updated_at = datetime('now')
                    """,
                    (
                        purl,
                        name,
                        "npm",
                        version,
                        license_id,
                        version_info.get("description") or data.get("description"),
                        version_info.get("homepage") or data.get("homepage"),
                        author,
                        1,
                        self._categorize(name),
                    ),
                )

                conn.commit()
            return True

        except sqlite3.Error as e:
            self._log(f"DB error for {name}: {e}")
            return False

    def _normalize_license(self, license_id: str | None) -> str | None:
        """Normalize license to SPDX ID."""
        if not license_id:
            return None

        mappings = {
            "mit": "MIT",
            "isc": "ISC",
            "apache-2.0": "Apache-2.0",
            "bsd-3-clause": "BSD-3-Clause",
        }
        return mappings.get(license_id.lower(), license_id)

    def _categorize(self, name: str) -> str:
        """Categorize AI package."""
        if name in ["openai", "@anthropic-ai/sdk", "cohere-ai"]:
            return "sdk"
        if "langchain" in name or "llamaindex" in name:
            return "framework"
        if "@ai-sdk" in name or name == "ai":
            return "sdk"
        return "library"

    def _log(self, message: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[npm] {message}")
