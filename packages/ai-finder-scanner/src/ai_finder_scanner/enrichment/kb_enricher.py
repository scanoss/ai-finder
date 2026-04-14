"""KB-based enrichment for SBOM components with live API fallback."""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from .huggingface import HuggingFaceEnricher
    from .npm import NpmEnricher
    from .pypi import PyPIEnricher

logger = logging.getLogger(__name__)

# Telemetry callback type
# Uses Dict for Python 3.8 - type aliases are evaluated at runtime, not by PEP 563
TelemetryCallback = Callable[[str, dict[str, Any]], None]

# Type var for cache values
T = TypeVar("T")


def _classify_fetch_error(error: Exception) -> str:
    """Classify a fetch error for telemetry.

    Returns a category string for the error type.
    """
    error_type = type(error).__name__

    # Network/connection errors
    if "ConnectionError" in error_type or "Connection" in str(error):
        return "network_error"
    if "Timeout" in error_type or "timeout" in str(error).lower():
        return "timeout"
    if "SSLError" in error_type:
        return "ssl_error"

    # HTTP errors
    if "HTTPError" in error_type:
        # Try to extract status code
        if hasattr(error, "response") and hasattr(error.response, "status_code"):
            status = error.response.status_code
            if status == 404:
                return "not_found"
            if status == 429:
                return "rate_limited"
            if status == 401 or status == 403:
                return "auth_error"
            if status >= 500:
                return "server_error"
        return "http_error"

    # Import errors (missing dependencies)
    if "ImportError" in error_type or "ModuleNotFoundError" in error_type:
        return "missing_dependency"

    # JSON/parsing errors
    if "JSON" in error_type or "Decode" in error_type:
        return "parse_error"

    # Generic
    return "unknown"


@dataclass
class ModelEnrichment:
    """Enrichment data for a model."""

    purl: str
    name: str | None = None
    organization: str | None = None
    architecture: str | None = None
    architecture_family: str | None = None
    parameter_count: int | None = None
    license: str | None = None
    source_url: str | None = None
    task: str | None = None
    base_model_purl: str | None = None
    datasets: list[str] | None = None


@dataclass
class PackageEnrichment:
    """Enrichment data for a package."""

    purl: str
    name: str | None = None
    version: str | None = None
    license: str | None = None
    summary: str | None = None
    homepage: str | None = None
    author: str | None = None
    ai_category: str | None = None


class KBEnricher:
    """Enrich SBOM components from local KB cache with live API fallback."""

    def __init__(
        self,
        db_path: Path | None = None,
        enable_live_fallback: bool = True,
        telemetry_callback: TelemetryCallback | None = None,
    ) -> None:
        """Initialize enricher.

        Args:
            db_path: Path to KB database (optional).
            enable_live_fallback: If True, fetch from APIs when not in KB.
            telemetry_callback: Optional callback for telemetry signals.
        """
        self.db_path = db_path
        self.enable_live_fallback = enable_live_fallback
        self._telemetry = telemetry_callback
        self._conn: sqlite3.Connection | None = None
        self._hf_enricher: HuggingFaceEnricher | None = None
        self._pypi_enricher: PyPIEnricher | None = None
        self._npm_enricher: NpmEnricher | None = None

        # In-memory LRU cache for session (avoid duplicate API calls, bounded size)
        self._cache_max_size = 1000
        self._model_cache: dict[str, ModelEnrichment | None] = {}
        self._package_cache: dict[str, PackageEnrichment | None] = {}

    def _cache_set(self, cache: dict[str, T | None], key: str, value: T | None) -> None:
        """Set cache value with LRU eviction if needed."""
        if len(cache) >= self._cache_max_size:
            # Remove oldest entry (first key in dict - Python 3.7+ preserves order)
            oldest_key = next(iter(cache))
            del cache[oldest_key]
        cache[key] = value

    def __enter__(self) -> KBEnricher:
        """Open database connection."""
        if self.db_path and self.db_path.exists():
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, *args) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _track(self, event: str, data: dict) -> None:
        """Record telemetry signal."""
        if self._telemetry:
            with contextlib.suppress(Exception):
                self._telemetry(event, data)

    def lookup_model(self, name: str) -> ModelEnrichment | None:
        """Look up model by name or partial match.

        Args:
            name: Model filename (e.g., "tinyllama.gguf").

        Returns:
            ModelEnrichment if found, None otherwise.
        """
        # Check session cache first
        if name in self._model_cache:
            self._track("enrichment.cache_hit", {"type": "model"})
            return self._model_cache[name]

        # Clean filename for search
        clean_name = name.lower()
        for ext in [".gguf", ".safetensors", ".bin", ".pt", ".pth", ".onnx"]:
            if clean_name.endswith(ext):
                clean_name = clean_name[: -len(ext)]
                break

        # Remove quantization suffixes
        for suffix in ["-q4_k_m", "-q5_k_m", "-q8_0", "-f16", "-fp16", "_q4_k_m"]:
            clean_name = clean_name.replace(suffix, "")

        # Try KB first
        if self._conn:
            try:
                cursor = self._conn.execute(
                    """
                    SELECT purl, name, organization, architecture, architecture_family,
                           parameter_count, license, source_url, task, base_model_purl, datasets
                    FROM models
                    WHERE LOWER(name) LIKE ? OR LOWER(purl) LIKE ?
                    ORDER BY parameter_count DESC NULLS LAST
                    LIMIT 1
                    """,
                    (f"%{clean_name}%", f"%{clean_name}%"),
                )
                row = cursor.fetchone()
                if row:
                    datasets = None
                    if row["datasets"]:
                        with contextlib.suppress(json.JSONDecodeError):
                            datasets = json.loads(row["datasets"])

                    self._track("enrichment.kb_hit", {"type": "model", "name": clean_name})
                    kb_result = ModelEnrichment(
                        purl=row["purl"],
                        name=row["name"],
                        organization=row["organization"],
                        architecture=row["architecture"],
                        architecture_family=row["architecture_family"],
                        parameter_count=row["parameter_count"],
                        license=row["license"],
                        source_url=row["source_url"],
                        task=row["task"],
                        base_model_purl=row["base_model_purl"],
                        datasets=datasets,
                    )
                    self._cache_set(self._model_cache, name, kb_result)
                    return kb_result
            except sqlite3.Error as e:
                logger.debug("Model KB lookup failed: %s", e)

        # Fallback to live HuggingFace API
        if self.enable_live_fallback:
            live_result = self._fetch_model_live(clean_name)
            self._cache_set(
                self._model_cache, name, live_result
            )  # Cache even None to avoid repeated lookups
            return live_result

        self._cache_set(self._model_cache, name, None)
        return None

    def _fetch_model_live(self, name: str) -> ModelEnrichment | None:
        """Fetch model from HuggingFace API."""
        try:
            from .huggingface import HuggingFaceEnricher

            if self._hf_enricher is None:
                self._hf_enricher = HuggingFaceEnricher()

            result = self._hf_enricher.lookup_by_name(name)
            if result:
                self._track("enrichment.live_fetch", {"type": "model", "source": "huggingface"})
                return ModelEnrichment(
                    purl=result.purl,
                    name=result.name,
                    organization=result.organization,
                    architecture=result.architecture,
                    architecture_family=result.architecture_family,
                    parameter_count=result.parameter_count,
                    license=result.license,
                    source_url=result.source_url,
                    task=result.task,
                    base_model_purl=result.base_model,
                    datasets=result.datasets,
                )
            else:
                # Model not found in HuggingFace
                self._track(
                    "enrichment.model_not_found", {"source": "huggingface", "name": name[:50]}
                )
        except Exception as e:
            error_category = _classify_fetch_error(e)
            self._track(
                "enrichment.live_fetch_failed",
                {
                    "type": "model",
                    "source": "huggingface",
                    "error_category": error_category,
                },
            )
            logger.debug("HuggingFace live fetch failed: %s", e)

        return None

    def lookup_package(self, name: str, ecosystem: str) -> PackageEnrichment | None:
        """Look up package by name and ecosystem.

        Args:
            name: Package name (e.g., "openai").
            ecosystem: Package ecosystem (pypi, npm, etc.).

        Returns:
            PackageEnrichment if found, None otherwise.
        """
        # Check session cache first
        cache_key = f"{ecosystem}:{name}"
        if cache_key in self._package_cache:
            self._track("enrichment.cache_hit", {"type": "package"})
            return self._package_cache[cache_key]

        # Try KB first
        if self._conn:
            try:
                cursor = self._conn.execute(
                    """
                    SELECT purl, name, version, license, summary, homepage, author, ai_category
                    FROM packages
                    WHERE LOWER(name) = LOWER(?) AND ecosystem = ?
                    LIMIT 1
                    """,
                    (name, ecosystem),
                )
                row = cursor.fetchone()
                if row:
                    self._track("enrichment.kb_hit", {"type": "package", "ecosystem": ecosystem})
                    kb_pkg = PackageEnrichment(
                        purl=row["purl"],
                        name=row["name"],
                        version=row["version"],
                        license=row["license"],
                        summary=row["summary"],
                        homepage=row["homepage"],
                        author=row["author"],
                        ai_category=row["ai_category"],
                    )
                    self._cache_set(self._package_cache, cache_key, kb_pkg)
                    return kb_pkg
            except sqlite3.Error as e:
                logger.debug("Package KB lookup failed: %s", e)

        # Fallback to live API
        if self.enable_live_fallback:
            live_pkg = self._fetch_package_live(name, ecosystem)
            self._cache_set(self._package_cache, cache_key, live_pkg)  # Cache even None
            return live_pkg

        self._cache_set(self._package_cache, cache_key, None)
        return None

    def _fetch_package_live(self, name: str, ecosystem: str) -> PackageEnrichment | None:
        """Fetch package from PyPI/npm API."""
        try:
            if ecosystem == "pypi":
                from .pypi import PyPIEnricher

                if self._pypi_enricher is None:
                    self._pypi_enricher = PyPIEnricher()

                pypi_info = self._pypi_enricher.lookup_package(name)
                if pypi_info:
                    self._track("enrichment.live_fetch", {"type": "package", "source": "pypi"})
                    return PackageEnrichment(
                        purl=pypi_info.purl,
                        name=pypi_info.name,
                        version=pypi_info.version,
                        license=pypi_info.license,
                        summary=pypi_info.summary,
                        homepage=pypi_info.homepage,
                        author=pypi_info.author,
                    )
                else:
                    self._track(
                        "enrichment.package_not_found", {"source": "pypi", "name": name[:50]}
                    )

            elif ecosystem == "npm":
                from .npm import NpmEnricher

                if self._npm_enricher is None:
                    self._npm_enricher = NpmEnricher()

                npm_info = self._npm_enricher.lookup_package(name)
                if npm_info:
                    self._track("enrichment.live_fetch", {"type": "package", "source": "npm"})
                    return PackageEnrichment(
                        purl=npm_info.purl,
                        name=npm_info.name,
                        version=npm_info.version,
                        license=npm_info.license,
                        summary=npm_info.description,
                        homepage=npm_info.homepage,
                        author=npm_info.author,
                    )
                else:
                    self._track(
                        "enrichment.package_not_found", {"source": "npm", "name": name[:50]}
                    )

            else:
                # Unsupported ecosystem - track it
                self._track("enrichment.unsupported_ecosystem", {"ecosystem": ecosystem})

        except Exception as e:
            error_category = _classify_fetch_error(e)
            self._track(
                "enrichment.live_fetch_failed",
                {
                    "type": "package",
                    "source": ecosystem,
                    "error_category": error_category,
                },
            )
            logger.debug("Live package fetch failed for %s/%s: %s", ecosystem, name, e)

        return None

    def lookup_sdk(self, sdk_name: str) -> PackageEnrichment | None:
        """Look up SDK by name, inferring ecosystem.

        Args:
            sdk_name: SDK name or import path.

        Returns:
            PackageEnrichment if found, None otherwise.
        """
        # Infer ecosystem from name pattern
        if sdk_name.startswith("github.com/"):
            # Go module - extract package name
            parts = sdk_name.split("/")
            name = parts[-1] if len(parts) > 2 else sdk_name
            return self.lookup_package(name, "golang")
        elif sdk_name.startswith("@"):
            # npm scoped package
            return self.lookup_package(sdk_name, "npm")
        else:
            # Try pypi first, then npm
            result = self.lookup_package(sdk_name, "pypi")
            if not result:
                result = self.lookup_package(sdk_name, "npm")
            return result
