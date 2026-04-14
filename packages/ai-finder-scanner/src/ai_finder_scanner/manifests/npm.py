"""NPM manifest parser (package.json)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

logger = logging.getLogger(__name__)

# AI/ML package names to detect (including scoped packages)
AI_PACKAGES = frozenset(
    {
        "openai",
        "@anthropic-ai/sdk",
        "langchain",
        "@langchain/core",
        "@langchain/openai",
        "@langchain/anthropic",
        "@langchain/community",
        "ai",  # Vercel AI SDK
        "@vercel/ai",
        "@huggingface/inference",
        "@huggingface/hub",
        "cohere-ai",
        "replicate",
        "together-ai",
        "groq-sdk",
        "@mistralai/mistralai",
        "ollama",
        "@google/generative-ai",
        "@xenova/transformers",
        "llamaindex",
        "chromadb",
        "@pinecone-database/pinecone",
        "weaviate-ts-client",
        "@qdrant/js-client-rest",
        "onnxruntime-node",
        "onnxruntime-web",
        "@tensorflow/tfjs",
        "@tensorflow/tfjs-node",
    }
)


class NpmManifestParser(BaseManifestParser):
    """Parse NPM manifest files for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"package.json"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if package is an AI package."""
        # Check exact match or langchain scoped package
        return name in AI_PACKAGES or name.startswith("@langchain/")

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse package.json for AI dependencies.

        Args:
            content: package.json content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency found.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in %s: %s", path, e)
            return

        # Check both dependencies and devDependencies
        for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
            deps = data.get(dep_key, {})
            if not isinstance(deps, dict):
                continue

            for name, version in deps.items():
                if self._is_ai_package(name):
                    yield Finding(
                        type=FindingType.MANIFEST_DEP,
                        file_path=str(path),
                        confidence=1.0,
                        manifest_dep=ManifestDep(
                            name=name,
                            version=str(version),
                            manifest_file=str(path),
                        ),
                    )
