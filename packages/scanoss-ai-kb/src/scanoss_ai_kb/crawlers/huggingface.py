"""HuggingFace Hub crawler for model metadata."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)

# SPDX license normalization
SPDX_CASING = {
    "mit": "MIT",
    "apache-2.0": "Apache-2.0",
    "gpl-3.0": "GPL-3.0-only",
    "bsd-3-clause": "BSD-3-Clause",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "cc0-1.0": "CC0-1.0",
    "openrail": "OpenRAIL",
    "llama2": "Llama-2",
    "llama3": "Llama-3",
    "llama3.1": "Llama-3.1",
    "gemma": "Gemma",
}

ARCH_PATTERNS = {
    "llama": ["llama", "codellama"],
    "mistral": ["mistral", "mixtral"],
    "qwen": ["qwen"],
    "phi": ["phi"],
    "gemma": ["gemma"],
    "falcon": ["falcon"],
    "gpt2": ["gpt2", "gpt-2"],
    "bert": ["bert", "roberta"],
    "t5": ["t5", "flan-t5"],
    "whisper": ["whisper"],
    "stable_diffusion": ["stable-diffusion", "sdxl"],
    "deepseek": ["deepseek"],
}

ARCH_FAMILIES = {
    "llama": "transformer",
    "mistral": "transformer",
    "qwen": "transformer",
    "phi": "transformer",
    "gemma": "transformer",
    "falcon": "transformer",
    "gpt2": "transformer",
    "bert": "transformer",
    "t5": "transformer",
    "whisper": "transformer",
    "stable_diffusion": "diffusion",
    "deepseek": "transformer",
}

PARAM_PATTERNS = [
    (r"(\d+\.?\d*)[bB][\s\-_]?[pP]?aram", 1_000_000_000),
    (r"(\d+\.?\d*)[mM][\s\-_]?[pP]?aram", 1_000_000),
    (r"[\-_](\d+\.?\d*)[bB][\-_\.]", 1_000_000_000),
    (r"[\-_](\d+)[bB]$", 1_000_000_000),
]


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    models_added: int = 0
    models_updated: int = 0
    errors: list[str] = field(default_factory=list)


class HuggingFaceCrawler:
    """Crawler for HuggingFace Hub models.

    Fetches model metadata and stores in KB database.
    """

    API_BASE = "https://huggingface.co/api"
    RATE_LIMIT_DELAY = 0.5

    def __init__(
        self,
        db_path: Path,
        verbose: bool = False,
        token: str | None = None,
    ) -> None:
        """Initialize crawler.

        Args:
            db_path: Path to KB database.
            verbose: Enable verbose output.
            token: Optional HuggingFace API token.
        """
        self.db_path = db_path
        self.verbose = verbose
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def crawl(
        self,
        limit: int | None = None,
        sort: str = "downloads",
        min_downloads: int = 1000,
    ) -> CrawlResult:
        """Crawl HuggingFace Hub for popular models.

        Args:
            limit: Maximum models to crawl.
            sort: Sort order (downloads, likes).
            min_downloads: Minimum downloads to include.

        Returns:
            CrawlResult with statistics.
        """
        result = CrawlResult()
        count = 0

        self._log(f"Starting crawl (limit={limit}, sort={sort})")

        for model_info in self._list_models(sort=sort, limit=limit):
            try:
                if model_info.get("downloads", 0) < min_downloads:
                    continue

                model_id = model_info["id"]
                detail = self._get_model_detail(model_id)
                if not detail:
                    continue

                if self._upsert_model(model_id, model_info, detail):
                    result.models_added += 1
                    self._log(f"Added: {model_id}")

                count += 1
                if limit and count >= limit:
                    break

                time.sleep(self.RATE_LIMIT_DELAY)

            except Exception as e:
                result.errors.append(f"Error: {model_info.get('id', 'unknown')}: {e}")

        self._log(f"Crawl complete: {result.models_added} models")
        return result

    def crawl_model(self, model_id: str) -> bool:
        """Crawl a specific model by ID.

        Args:
            model_id: HuggingFace model ID (org/name).

        Returns:
            True if successful.
        """
        detail = self._get_model_detail(model_id)
        if not detail:
            return False

        return self._upsert_model(model_id, {}, detail)

    def _list_models(
        self, sort: str = "downloads", limit: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """List models from HuggingFace API."""
        url = f"{self.API_BASE}/models"
        params = {"sort": sort, "direction": "-1", "limit": min(limit or 100, 100)}

        yielded = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                models = resp.json()

                if not models:
                    break

                for model in models:
                    yield model
                    yielded += 1
                    if limit and yielded >= limit:
                        return

                # Pagination
                if "Link" not in resp.headers:
                    break
                link = resp.headers["Link"]
                if 'rel="next"' not in link:
                    break
                match = re.search(r'<([^>]+)>;\s*rel="next"', link)
                if not match:
                    break
                url = match.group(1)
                params = {}

                time.sleep(self.RATE_LIMIT_DELAY)

            except requests.RequestException as e:
                self._log(f"API error: {e}")
                break

    def _get_model_detail(self, model_id: str) -> dict[str, Any] | None:
        """Get detailed model information."""
        url = f"{self.API_BASE}/models/{model_id}"
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            self._log(f"Failed to get {model_id}: {e}")
            return None

    def _upsert_model(
        self, model_id: str, list_info: dict[str, Any], detail: dict[str, Any]
    ) -> bool:
        """Insert or update model in KB."""
        parts = model_id.split("/", 1)
        org = parts[0] if len(parts) == 2 else None
        name = parts[1] if len(parts) == 2 else model_id

        config = detail.get("config", {})
        card_data = detail.get("cardData", {})

        # Architecture
        architecture = self._infer_architecture(model_id, config)
        architecture_family = ARCH_FAMILIES.get(architecture) if architecture else None

        # Parameters
        param_count = self._get_parameter_count(model_id, config, detail)

        # License
        license_id = card_data.get("license") or config.get("license")
        if license_id:
            license_id = SPDX_CASING.get(license_id.lower(), license_id)

        # Base model
        base_model = card_data.get("base_model")
        if isinstance(base_model, list):
            base_model = base_model[0] if base_model else None
        base_model_purl = f"pkg:huggingface/{base_model}" if base_model else None

        # Datasets
        datasets = card_data.get("datasets")
        if datasets and not isinstance(datasets, list):
            datasets = [datasets]
        datasets_json = json.dumps(datasets) if datasets else None

        # Format
        siblings = detail.get("siblings", [])
        model_format = self._infer_format(siblings)

        # Task
        task = detail.get("pipeline_tag")

        # Version
        version = detail.get("sha")

        # PURL
        purl = f"pkg:huggingface/{model_id}"
        if version:
            purl = f"{purl}@{version[:12]}"

        source_url = f"https://huggingface.co/{model_id}"

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO models (
                        purl, name, organization, version, format, architecture,
                        architecture_family, parameter_count, license, source_url,
                        task, base_model_purl, datasets
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(purl) DO UPDATE SET
                        name = excluded.name,
                        organization = excluded.organization,
                        version = COALESCE(excluded.version, version),
                        format = COALESCE(excluded.format, format),
                        architecture = COALESCE(excluded.architecture, architecture),
                        architecture_family = COALESCE(excluded.architecture_family, architecture_family),
                        parameter_count = COALESCE(excluded.parameter_count, parameter_count),
                        license = COALESCE(excluded.license, license),
                        source_url = excluded.source_url,
                        task = COALESCE(excluded.task, task),
                        base_model_purl = COALESCE(excluded.base_model_purl, base_model_purl),
                        datasets = COALESCE(excluded.datasets, datasets),
                        updated_at = datetime('now')
                    """,
                    (
                        purl,
                        name,
                        org,
                        version,
                        model_format,
                        architecture,
                        architecture_family,
                        param_count,
                        license_id,
                        source_url,
                        task,
                        base_model_purl,
                        datasets_json,
                    ),
                )

                conn.commit()
            return True

        except sqlite3.Error as e:
            self._log(f"DB error for {model_id}: {e}")
            return False

    def _infer_architecture(self, model_id: str, config: dict[str, Any]) -> str | None:
        """Infer model architecture."""
        model_type = config.get("model_type", "").lower()
        if model_type:
            for arch, patterns in ARCH_PATTERNS.items():
                if any(p in model_type for p in patterns):
                    return arch

        for arch_name in config.get("architectures", []):
            arch_lower = arch_name.lower()
            for arch, patterns in ARCH_PATTERNS.items():
                if any(p in arch_lower for p in patterns):
                    return arch

        model_id_lower = model_id.lower()
        for arch, patterns in ARCH_PATTERNS.items():
            if any(p in model_id_lower for p in patterns):
                return arch

        return model_type if model_type else None

    def _get_parameter_count(
        self, model_id: str, config: dict[str, Any], detail: dict[str, Any]
    ) -> int | None:
        """Extract parameter count."""
        safetensors = detail.get("safetensors", {})
        if safetensors:
            params = safetensors.get("total") or safetensors.get("parameters", {}).get(
                "total"
            )
            if params:
                return int(params)

        for pattern, multiplier in PARAM_PATTERNS:
            match = re.search(pattern, model_id.lower())
            if match:
                try:
                    return int(float(match.group(1)) * multiplier)
                except ValueError:
                    continue

        hidden_size = config.get("hidden_size")
        num_layers = config.get("num_hidden_layers")
        if hidden_size and num_layers:
            return int(12 * hidden_size * hidden_size * num_layers)

        return None

    def _infer_format(self, siblings: list[dict[str, Any]]) -> str | None:
        """Infer model format from files."""
        filenames = [s.get("rfilename", "") for s in siblings]

        if any(f.endswith(".gguf") for f in filenames):
            return "gguf"
        if any(f.endswith(".safetensors") for f in filenames):
            return "safetensors"
        if any(f.endswith(".onnx") for f in filenames):
            return "onnx"
        if any(f.endswith(".pt") or f.endswith(".pth") for f in filenames):
            return "pytorch"

        return None

    def _log(self, message: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[HuggingFace] {message}")
