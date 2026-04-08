"""Java/Kotlin SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# Fallback AI/ML SDK package patterns (used when no KB matcher provided)
AI_SDK_PACKAGES_FALLBACK = frozenset(
    {
        "com.theokanning.openai",
        "com.aallam.openai",
        "dev.langchain4j",
        "ai.djl",
        "org.tensorflow",
        "org.deeplearning4j",
        "com.google.cloud.aiplatform",
        "ai.onnxruntime",
    }
)

# Regex for Java/Kotlin import statements
IMPORT_RE = re.compile(
    r"^import\s+(?:static\s+)?(?P<package>[\w.]+)(?:\.\*)?;?",
    re.MULTILINE,
)


class JavaDetector(BaseDetector):
    """Detect SDK usage in Java/Kotlin files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".java", ".kt", ".kts"})

    def _get_base_package(self, package: str) -> str:
        """Get the base package (first 2-3 parts) for matching."""
        parts = package.split(".")
        # Return first 2-3 parts for matching
        if len(parts) >= 3:
            return ".".join(parts[:3])
        return package

    def _is_ai_sdk_fallback(self, package: str) -> bool:
        """Check if package is an AI SDK using fallback patterns."""
        base = self._get_base_package(package)
        return any(base.startswith(sdk) for sdk in AI_SDK_PACKAGES_FALLBACK)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(
        self, content: str, path: Path, matcher: Any | None = None
    ) -> Iterator[Finding]:
        """Detect SDK usage in Java/Kotlin file content.

        Args:
            content: Java/Kotlin source code.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup.

        Yields:
            Finding for each SDK usage detected.
        """
        seen_packages: set[str] = set()

        for match in IMPORT_RE.finditer(content):
            package = match.group("package")
            base_package = self._get_base_package(package)

            if base_package in seen_packages:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(package)
                if sdk_match:
                    seen_packages.add(base_package)
                    yield Finding(
                        type=FindingType.SDK_USAGE,
                        file_path=str(path),
                        line=self._find_line_number(content, match.start()),
                        confidence=sdk_match.confidence,
                        sdk_usage=SDKUsage(
                            sdk=sdk_match.id,
                            import_statement=match.group(0).strip(),
                        ),
                    )
            elif self._is_ai_sdk_fallback(package):
                seen_packages.add(base_package)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_package,
                        import_statement=match.group(0).strip(),
                    ),
                )
