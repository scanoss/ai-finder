"""Swift SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# Fallback AI/ML SDK modules (used when no KB matcher provided)
AI_SDK_MODULES_FALLBACK = frozenset(
    {
        "CoreML",
        "CreateML",
        "NaturalLanguage",
        "Vision",
        "SoundAnalysis",
        "Speech",
        "OpenAI",
        "Anthropic",
        "GoogleGenerativeAI",
        "LangChain",
        "Replicate",
        "MLKit",
        "TensorFlowLite",
        "TensorFlowLiteSwift",
        "ONNX",
        "SwiftOpenAI",
    }
)

# Regex for import statements
IMPORT_RE = re.compile(
    r"^(?P<statement>import\s+(?:struct\s+|class\s+|enum\s+|protocol\s+|func\s+)?(?P<module>[\w.]+))",
    re.MULTILINE,
)


class SwiftDetector(BaseDetector):
    """Detect SDK usage in Swift files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".swift"})

    def _get_base_module(self, module: str) -> str:
        """Get the base module name (first part before dot)."""
        return module.split(".")[0]

    def _is_ai_sdk_fallback(self, module: str) -> bool:
        """Check if module is an AI SDK using fallback patterns."""
        base = self._get_base_module(module)
        return base in AI_SDK_MODULES_FALLBACK or module in AI_SDK_MODULES_FALLBACK

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect SDK usage in Swift file content.

        Args:
            content: Swift source code.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup.

        Yields:
            Finding for each SDK usage detected.
        """
        seen_modules: set[str] = set()

        for match in IMPORT_RE.finditer(content):
            module = match.group("module")
            base_module = self._get_base_module(module)

            if base_module in seen_modules:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(module)
                if sdk_match:
                    seen_modules.add(base_module)
                    yield Finding(
                        type=FindingType.SDK_USAGE,
                        file_path=str(path),
                        line=self._find_line_number(content, match.start()),
                        confidence=sdk_match.confidence,
                        sdk_usage=SDKUsage(
                            sdk=sdk_match.id,
                            import_statement=match.group("statement").strip(),
                        ),
                    )
            elif self._is_ai_sdk_fallback(module):
                seen_modules.add(base_module)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_module.lower(),
                        import_statement=match.group("statement").strip(),
                    ),
                )
