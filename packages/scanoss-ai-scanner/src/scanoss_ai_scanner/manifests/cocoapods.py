"""CocoaPods Podfile manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML pod names to detect
AI_PODS = frozenset(
    {
        "OpenAI",
        "OpenAISwift",
        "GoogleGenerativeAI",
        "TensorFlowLiteSwift",
        "TensorFlowLiteObjC",
        "TensorFlowLiteC",
        "CoreMLTools",
        "MLKit",
        "GoogleMLKit",
        "Firebase/MLModelDownloader",
        "Replicate",
        "LangChain",
    }
)

# Regex for pod declarations
# Matches: pod 'Name', '~> 1.0' or pod "Name"
POD_RE = re.compile(
    r"^\s*pod\s+['\"](?P<name>[\w/-]+)['\"](?:\s*,\s*['\"](?P<version>[^'\"]+)['\"])?",
    re.MULTILINE,
)


class CocoaPodsManifestParser(BaseManifestParser):
    """Parse Podfile for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"Podfile"})

    def _is_ai_package(self, name: str) -> bool:
        """Check if pod is an AI package."""
        return name in AI_PODS or any(ai_pod.lower() in name.lower() for ai_pod in AI_PODS)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse Podfile for AI dependencies.

        Args:
            content: Podfile content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_pods: set[str] = set()

        for match in POD_RE.finditer(content):
            name = match.group("name")
            version = match.group("version") or "*"

            if self._is_ai_package(name) and name not in seen_pods:
                seen_pods.add(name)
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
