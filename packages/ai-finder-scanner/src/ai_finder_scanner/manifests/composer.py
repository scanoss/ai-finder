"""PHP composer.json manifest parser."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML package names to detect
AI_PACKAGES = frozenset(
    {
        "openai-php/client",
        "anthropic/anthropic-php",
        "google/cloud-aiplatform",
        "google/generative-ai-php",
        "theodo-group/llphant",
        "kambo/langchain",
        "php-llm/llm-chain",
        "cohere-ai/cohere-php",
        "replicate/replicate-php",
        "huggingface/transformers",
        "rubix/ml",
        "php-ai/php-ml",
        "ankane/tensorflow-php",
        "ankane/onnxruntime-php",
    }
)


class ComposerManifestParser(BaseManifestParser):
    """Parse composer.json for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"composer.json"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if package is an AI package."""
        return name in AI_PACKAGES

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse composer.json for AI dependencies.

        Args:
            content: composer.json content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return

        seen_packages: set[str] = set()

        # Check require and require-dev sections
        for section in ["require", "require-dev"]:
            deps = data.get(section, {})
            if not isinstance(deps, dict):
                continue

            for name, version in deps.items():
                if self._is_ai_package(name) and name not in seen_packages:
                    seen_packages.add(name)
                    yield Finding(
                        type=FindingType.MANIFEST_DEP,
                        file_path=str(path),
                        line=1,  # JSON doesn't have meaningful line numbers
                        confidence=1.0,
                        manifest_dep=ManifestDep(
                            name=name.split("/")[-1],  # Short name after /
                            version=str(version),
                            manifest_file=str(path),
                        ),
                    )
