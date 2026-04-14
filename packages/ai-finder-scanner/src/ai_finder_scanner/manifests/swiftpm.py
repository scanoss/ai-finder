"""Swift Package Manager Package.swift manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML package URLs to detect
AI_PACKAGES = frozenset(
    {
        "swift-openai",
        "OpenAI",
        "SwiftOpenAI",
        "anthropic-swift",
        "google-generative-ai-swift",
        "swift-transformers",
        "CoreMLTools",
        "TensorFlow",
        "swift-numerics",
        "Replicate",
        "LangChain",
    }
)

# Regex for .package dependencies
# Matches: .package(url: "https://github.com/org/repo", from: "1.0.0")
PACKAGE_RE = re.compile(
    r'\.package\s*\(\s*url:\s*["\'](?P<url>[^"\']+)["\']\s*,\s*'
    r'(?:from:\s*["\'](?P<version>[^"\']+)["\']|'
    r'\.upToNextMajor\(from:\s*["\'](?P<version2>[^"\']+)["\']\)|'
    r'\.upToNextMinor\(from:\s*["\'](?P<version3>[^"\']+)["\']\)|'
    r'exact:\s*["\'](?P<version4>[^"\']+)["\'])',
    re.MULTILINE,
)


class SwiftPMManifestParser(BaseManifestParser):
    """Parse Package.swift for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"Package.swift"})

    def _extract_package_name(self, url: str) -> str:
        """Extract package name from GitHub URL."""
        # https://github.com/org/repo.git -> repo
        # https://github.com/org/repo -> repo
        name = url.rstrip("/").rstrip(".git").split("/")[-1]
        return name

    def _is_ai_package(self, name: str) -> bool:
        """Check if package is an AI package."""
        return name in AI_PACKAGES or any(ai_pkg.lower() in name.lower() for ai_pkg in AI_PACKAGES)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse Package.swift for AI dependencies.

        Args:
            content: Package.swift content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_packages: set[str] = set()

        for match in PACKAGE_RE.finditer(content):
            url = match.group("url")
            name = self._extract_package_name(url)
            version = (
                match.group("version")
                or match.group("version2")
                or match.group("version3")
                or match.group("version4")
                or "*"
            )

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
