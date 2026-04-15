"""PyPI crawler for AI package metadata."""

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
    "anthropic",
    "langchain",
    "langchain-core",
    "langchain-openai",
    "langchain-anthropic",
    "llama-index",
    "llama-index-core",
    "transformers",
    "huggingface-hub",
    "torch",
    "tensorflow",
    "keras",
    "google-generativeai",
    "vertexai",
    "cohere",
    "replicate",
    "together",
    "groq",
    "mistralai",
    "ollama",
    "chromadb",
    "pinecone-client",
    "weaviate-client",
    "qdrant-client",
    "sentence-transformers",
    "accelerate",
    "datasets",
    "safetensors",
    "onnx",
    "onnxruntime",
]


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    packages_added: int = 0
    packages_updated: int = 0
    errors: list[str] = field(default_factory=list)


class PyPICrawler:
    """Crawler for PyPI AI packages."""

    API_BASE = "https://pypi.org/pypi"
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
        """Crawl PyPI for AI packages.

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
        url = f"{self.API_BASE}/{name}/json"

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

        info = data.get("info", {})
        version = info.get("version")
        purl = f"pkg:pypi/{name}"
        if version:
            purl = f"{purl}@{version}"

        # Get license
        license_id = None
        for classifier in info.get("classifiers", []):
            if classifier.startswith("License :: OSI Approved ::"):
                license_name = classifier.split("::")[-1].strip()
                license_id = self._map_license(license_name)
                break
        if not license_id:
            license_id = self._map_license(info.get("license"))

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
                        "pypi",
                        version,
                        license_id,
                        info.get("summary"),
                        info.get("home_page") or info.get("project_url"),
                        info.get("author"),
                        1,
                        self._categorize(name),
                    ),
                )

                conn.commit()
            return True

        except sqlite3.Error as e:
            self._log(f"DB error for {name}: {e}")
            return False

    def _map_license(self, text: str | None) -> str | None:
        """Map license text to SPDX ID."""
        if not text:
            return None

        mappings = {
            "mit license": "MIT",
            "mit": "MIT",
            "apache software license": "Apache-2.0",
            "apache 2.0": "Apache-2.0",
            "bsd license": "BSD-3-Clause",
            "isc license": "ISC",
        }
        return mappings.get(text.lower().strip(), text)

    def _categorize(self, name: str) -> str:
        """Categorize AI package."""
        if name in ["openai", "anthropic", "cohere", "groq", "mistralai"]:
            return "sdk"
        if name in ["langchain", "llama-index", "langchain-core"]:
            return "framework"
        if name in ["torch", "tensorflow", "keras"]:
            return "library"
        return "library"

    def _log(self, message: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[PyPI] {message}")
