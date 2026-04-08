"""C# SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML SDK namespaces to detect
AI_SDK_NAMESPACES = frozenset(
    {
        "OpenAI",
        "Anthropic",
        "Azure.AI",
        "Azure.AI.OpenAI",
        "Microsoft.ML",
        "Microsoft.SemanticKernel",
        "Google.Ai.Generativelanguage",
        "Google.Cloud.AIPlatform",
        "HuggingFace",
        "LangChain",
        "Replicate",
        "Cohere",
        "TensorFlow",
        "ONNX",
    }
)

# Regex for using statements
USING_RE = re.compile(
    r"^(?P<statement>using\s+(?:static\s+)?(?P<namespace>[\w.]+))\s*;",
    re.MULTILINE,
)


class CSharpDetector(BaseDetector):
    """Detect SDK usage in C# files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".cs"})

    def _get_base_namespace(self, namespace: str) -> str:
        """Get the base namespace (first two parts for Azure/Microsoft, else first)."""
        parts = namespace.split(".")
        # Azure.AI.*, Microsoft.* -> keep first two parts
        if parts[0] in {"Azure", "Microsoft", "Google"} and len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return parts[0]

    def _is_ai_sdk(self, namespace: str) -> bool:
        """Check if namespace is an AI SDK."""
        base = self._get_base_namespace(namespace)
        return base in AI_SDK_NAMESPACES or namespace in AI_SDK_NAMESPACES

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in C# file content.

        Args:
            content: C# source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_namespaces: set[str] = set()

        for match in USING_RE.finditer(content):
            namespace = match.group("namespace")
            base_namespace = self._get_base_namespace(namespace)

            if self._is_ai_sdk(namespace) and base_namespace not in seen_namespaces:
                seen_namespaces.add(base_namespace)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_namespace.lower().replace(".", "-"),
                        import_statement=match.group("statement").strip(),
                    ),
                )
