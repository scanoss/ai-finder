"""Rust Cargo.toml manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML crate names to detect
AI_CRATES = frozenset(
    {
        "openai",
        "async-openai",
        "anthropic",
        "llm",
        "llm-chain",
        "langchain-rust",
        "candle",
        "candle-core",
        "candle-nn",
        "candle-transformers",
        "tch",
        "torch-sys",
        "ort",
        "onnxruntime",
        "tract",
        "tract-onnx",
        "burn",
        "burn-core",
        "burn-tensor",
        "safetensors",
        "tokenizers",
        "huggingface-hub",
        "mistralrs",
        "ollama-rs",
        "replicate",
    }
)

# Regex for Cargo.toml dependencies
# Matches: name = "version" or name = { version = "x" }
CARGO_DEP_RE = re.compile(
    r'^(?P<name>[\w-]+)\s*=\s*(?:"(?P<version1>[^"]+)"|{[^}]*version\s*=\s*"(?P<version2>[^"]+)"[^}]*})',
    re.MULTILINE,
)


class CargoManifestParser(BaseManifestParser):
    """Parse Cargo.toml for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"Cargo.toml"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if crate is an AI package."""
        return name in AI_CRATES

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse Cargo.toml for AI dependencies.

        Args:
            content: Cargo.toml content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_packages: set[str] = set()

        for match in CARGO_DEP_RE.finditer(content):
            name = match.group("name")
            version = match.group("version1") or match.group("version2") or "*"

            if self._is_ai_package(name) and name not in seen_packages:
                seen_packages.add(name)
                yield Finding(
                    type=FindingType.MANIFEST_DEP,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    manifest_dep=ManifestDep(
                        name=name,
                        version=version,
                        manifest_file=str(path),
                    ),
                )
