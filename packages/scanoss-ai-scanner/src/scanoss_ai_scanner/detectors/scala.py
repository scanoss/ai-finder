"""Scala SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML SDK packages to detect
AI_SDK_PACKAGES = frozenset(
    {
        "org.apache.spark.ml",
        "org.apache.spark.mllib",
        "ai.djl",
        "com.intel.analytics.bigdl",
        "org.tensorflow",
        "org.platanios.tensorflow",
        "ai.catboost",
        "ml.combust.mleap",
        "com.johnsnowlabs.nlp",
        "io.kjaer.compiletime",
        "org.bytedeco.pytorch",
        "com.microsoft.onnxruntime",
    }
)

# Regex for import statements
IMPORT_RE = re.compile(
    r"^(?P<statement>import\s+(?P<package>[\w.]+)(?:\._|\.\{[^}]+\})?)",
    re.MULTILINE,
)


class ScalaDetector(BaseDetector):
    """Detect SDK usage in Scala files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".scala", ".sc"})

    def _get_base_package(self, package: str) -> str:
        """Get the base package (first 3-4 parts for Scala conventions)."""
        parts = package.split(".")
        # org.apache.spark.ml -> org.apache.spark
        if len(parts) >= 3:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return parts[0]

    def _is_ai_sdk(self, package: str) -> bool:
        """Check if package is an AI SDK."""
        return any(package.startswith(sdk) for sdk in AI_SDK_PACKAGES)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in Scala file content.

        Args:
            content: Scala source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_packages: set[str] = set()

        for match in IMPORT_RE.finditer(content):
            package = match.group("package")
            base_package = self._get_base_package(package)

            if self._is_ai_sdk(package) and base_package not in seen_packages:
                seen_packages.add(base_package)
                # Extract friendly SDK name
                sdk_name = base_package.split(".")[-1]
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=sdk_name,
                        import_statement=match.group("statement").strip(),
                    ),
                )
