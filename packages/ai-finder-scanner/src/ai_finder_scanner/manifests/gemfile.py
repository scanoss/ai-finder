"""Ruby Gemfile manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML gem names to detect
AI_GEMS = frozenset(
    {
        "ruby-openai",
        "anthropic",
        "langchainrb",
        "langchain",
        "cohere-ruby",
        "replicate-ruby",
        "ollama-ai",
        "google-cloud-ai_platform",
        "google-apis-generativelanguage_v1beta",
        "tensorflow",
        "torch-rb",
        "onnxruntime",
        "hugging-face",
        "pinecone",
        "weaviate",
        "qdrant-ruby",
        "milvus",
    }
)

# Regex for Gemfile gem declarations
# Matches: gem 'name', '~> 1.0' or gem "name"
GEMFILE_RE = re.compile(
    r"^gem\s+['\"](?P<name>[\w-]+)['\"](?:,\s*['\"](?P<version>[^'\"]+)['\"])?",
    re.MULTILINE,
)


class GemfileManifestParser(BaseManifestParser):
    """Parse Gemfile for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"Gemfile"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if gem is an AI package."""
        return name in AI_GEMS

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse Gemfile for AI dependencies.

        Args:
            content: Gemfile content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_gems: set[str] = set()

        for match in GEMFILE_RE.finditer(content):
            name = match.group("name")
            version = match.group("version") or "*"

            if self._is_ai_package(name) and name not in seen_gems:
                seen_gems.add(name)
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
