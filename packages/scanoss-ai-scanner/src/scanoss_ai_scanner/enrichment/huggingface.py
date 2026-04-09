"""HuggingFace Hub enrichment for model metadata."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

# SPDX license ID normalization
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

# Architecture patterns
ARCH_PATTERNS = {
    "llama": ["llama", "llama2", "llama3", "codellama"],
    "mistral": ["mistral", "mixtral"],
    "qwen": ["qwen", "qwen2"],
    "phi": ["phi", "phi-2", "phi-3"],
    "gemma": ["gemma"],
    "falcon": ["falcon"],
    "gpt2": ["gpt2", "gpt-2"],
    "bert": ["bert", "distilbert", "roberta"],
    "t5": ["t5", "flan-t5"],
    "whisper": ["whisper"],
    "stable_diffusion": ["stable-diffusion", "sdxl"],
    "deepseek": ["deepseek"],
}

# Parameter count patterns
PARAM_PATTERNS = [
    (r"(\d+\.?\d*)[bB][\s\-_]?[pP]?aram", 1_000_000_000),
    (r"(\d+\.?\d*)[mM][\s\-_]?[pP]?aram", 1_000_000),
    (r"[\-_](\d+\.?\d*)[bB][\-_\.]", 1_000_000_000),
    (r"[\-_](\d+\.?\d*)[mM][\-_\.]", 1_000_000),
    (r"[\-_](\d+)[bB]$", 1_000_000_000),
]


@dataclass
class ModelCardInfo:
    """Model card information from HuggingFace."""

    model_id: str
    purl: str
    name: str
    organization: str | None = None
    architecture: str | None = None
    architecture_family: str | None = None
    parameter_count: int | None = None
    license: str | None = None
    base_model: str | None = None
    datasets: list[str] | None = None
    model_format: str | None = None
    source_url: str | None = None
    task: str | None = None


class HuggingFaceEnricher:
    """Enrich model metadata from HuggingFace Hub API."""

    API_BASE = "https://huggingface.co/api"
    TIMEOUT = 10

    def __init__(self, token: str | None = None) -> None:
        """Initialize enricher.

        Args:
            token: Optional HuggingFace API token for higher rate limits.
        """
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def lookup_model(self, model_id: str) -> ModelCardInfo | None:
        """Look up model metadata from HuggingFace.

        Args:
            model_id: Model ID in org/name format (e.g., "TinyLlama/TinyLlama-1.1B-Chat-v1.0").

        Returns:
            ModelCardInfo if found, None otherwise.
        """
        url = f"{self.API_BASE}/models/{model_id}"
        try:
            resp = self._session.get(url, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                logger.debug("Model not found: %s", model_id)
                return None
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(model_id, data)
        except requests.RequestException as e:
            logger.warning("Failed to fetch model %s: %s", model_id, e)
            return None

    def lookup_by_name(self, name: str) -> ModelCardInfo | None:
        """Search for model by name and return best match.

        Args:
            name: Model filename or partial name (e.g., "tinyllama.gguf").

        Returns:
            ModelCardInfo if found, None otherwise.
        """
        # Clean up filename
        clean_name = name.lower()
        for ext in [".gguf", ".safetensors", ".bin", ".pt", ".pth", ".onnx"]:
            if clean_name.endswith(ext):
                clean_name = clean_name[: -len(ext)]
                break

        # Remove common suffixes
        for suffix in ["-q4_k_m", "-q5_k_m", "-q8_0", "-f16", "-fp16"]:
            if suffix in clean_name:
                clean_name = clean_name.replace(suffix, "")

        # Search HuggingFace
        url = f"{self.API_BASE}/models"
        params = {"search": clean_name, "limit": 5, "sort": "downloads"}

        try:
            resp = self._session.get(url, params=params, timeout=self.TIMEOUT)
            resp.raise_for_status()
            models = resp.json()

            if not models:
                return None

            # Return first (most downloaded) match
            model_id = models[0].get("id")
            if model_id:
                return self.lookup_model(model_id)

        except requests.RequestException as e:
            logger.warning("Search failed for %s: %s", name, e)

        return None

    def _parse_response(self, model_id: str, data: dict[str, Any]) -> ModelCardInfo:
        """Parse API response into ModelCardInfo."""
        parts = model_id.split("/", 1)
        org = parts[0] if len(parts) == 2 else None
        name = parts[1] if len(parts) == 2 else model_id

        config = data.get("config", {})
        card_data = data.get("cardData", {})

        # Get architecture
        architecture = self._infer_architecture(model_id, config)
        architecture_family = self._get_architecture_family(architecture)

        # Get parameter count
        param_count = self._get_parameter_count(model_id, config, data)

        # Get license
        license_id = card_data.get("license") or config.get("license")
        if license_id:
            license_id = SPDX_CASING.get(license_id.lower(), license_id)

        # Get base model
        base_model = card_data.get("base_model")
        if isinstance(base_model, list):
            base_model = base_model[0] if base_model else None

        # Get datasets
        datasets = card_data.get("datasets")
        if datasets and not isinstance(datasets, list):
            datasets = [datasets]

        # Get format from files
        siblings = data.get("siblings", [])
        model_format = self._infer_format(siblings)

        # Get task
        pipeline_tag = data.get("pipeline_tag")

        # Build PURL
        version = data.get("sha")
        purl = f"pkg:huggingface/{model_id}"
        if version:
            purl = f"{purl}@{version[:12]}"

        return ModelCardInfo(
            model_id=model_id,
            purl=purl,
            name=name,
            organization=org,
            architecture=architecture,
            architecture_family=architecture_family,
            parameter_count=param_count,
            license=license_id,
            base_model=f"pkg:huggingface/{base_model}" if base_model else None,
            datasets=datasets,
            model_format=model_format,
            source_url=f"https://huggingface.co/{model_id}",
            task=pipeline_tag,
        )

    def _infer_architecture(self, model_id: str, config: dict[str, Any]) -> str | None:
        """Infer model architecture."""
        # Try config.model_type
        model_type = config.get("model_type", "").lower()
        if model_type:
            for arch, patterns in ARCH_PATTERNS.items():
                if any(p in model_type for p in patterns):
                    return arch

        # Try architectures list
        for arch_name in config.get("architectures", []):
            arch_lower = arch_name.lower()
            for arch, patterns in ARCH_PATTERNS.items():
                if any(p in arch_lower for p in patterns):
                    return arch

        # Try model_id
        model_id_lower = model_id.lower()
        for arch, patterns in ARCH_PATTERNS.items():
            if any(p in model_id_lower for p in patterns):
                return arch

        return model_type if model_type else None

    def _get_architecture_family(self, architecture: str | None) -> str | None:
        """Map architecture to family."""
        if not architecture:
            return None

        families = {
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
        return families.get(architecture)

    def _get_parameter_count(
        self, model_id: str, config: dict[str, Any], data: dict[str, Any]
    ) -> int | None:
        """Extract parameter count."""
        # Try safetensors metadata
        safetensors = data.get("safetensors", {})
        if safetensors:
            params = safetensors.get("total") or safetensors.get("parameters", {}).get(
                "total"
            )
            if params:
                return int(params)

        # Parse from model name
        for pattern, multiplier in PARAM_PATTERNS:
            match = re.search(pattern, model_id.lower())
            if match:
                try:
                    return int(float(match.group(1)) * multiplier)
                except ValueError:
                    continue

        # Estimate from config
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
