"""NuGet .csproj manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML package names to detect
AI_PACKAGES = frozenset(
    {
        "OpenAI",
        "Anthropic",
        "Azure.AI.OpenAI",
        "Microsoft.SemanticKernel",
        "Microsoft.ML",
        "Microsoft.ML.OnnxRuntime",
        "TensorFlow.NET",
        "Keras.NET",
        "LangChain",
        "Pinecone",
        "Weaviate.Client",
        "Qdrant.Client",
        "Milvus.Client",
    }
)

# Regex for PackageReference in .csproj
PACKAGE_REF_RE = re.compile(
    r'<PackageReference\s+Include=["\'](?P<name>[^"\']+)["\']\s+'
    r'Version=["\'](?P<version>[^"\']+)["\']',
    re.IGNORECASE,
)

# Alternative format with nested Version element
PACKAGE_REF_ALT_RE = re.compile(
    r'<PackageReference\s+Include=["\'](?P<name>[^"\']+)["\']>\s*'
    r"<Version>(?P<version>[^<]+)</Version>",
    re.IGNORECASE | re.DOTALL,
)


class NuGetManifestParser(BaseManifestParser):
    """Parse .csproj for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        # Note: .csproj files have variable names, discovery handles *.csproj
        return frozenset({"packages.config"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if package is an AI package."""
        return name in AI_PACKAGES or any(name.startswith(p) for p in AI_PACKAGES)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse .csproj for AI dependencies.

        Args:
            content: .csproj XML content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_packages: set[str] = set()

        # Check both formats
        for pattern in [PACKAGE_REF_RE, PACKAGE_REF_ALT_RE]:
            for match in pattern.finditer(content):
                name = match.group("name")
                version = match.group("version")

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
