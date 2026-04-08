"""JavaScript/TypeScript SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML SDK package names to detect
AI_SDK_PACKAGES = frozenset(
    {
        "openai",
        "@anthropic-ai/sdk",
        "langchain",
        "@langchain/core",
        "@langchain/openai",
        "ai",  # Vercel AI SDK
        "@vercel/ai",
        "cohere-ai",
        "replicate",
        "@huggingface/inference",
        "together-ai",
        "groq-sdk",
        "@mistralai/mistralai",
        "ollama-js",
        "@google/generative-ai",
        "@xenova/transformers",
    }
)

# Regex for ES6 import statements
ES_IMPORT_RE = re.compile(
    r'^(?P<statement>import\s+.+?\s+from\s+["\'](?P<package>[@\w/-]+)["\'])\s*;?',
    re.MULTILINE,
)

# Regex for CommonJS require statements
REQUIRE_RE = re.compile(
    r'^(?P<statement>(?:const|let|var)\s+\w+\s*=\s*require\(["\'](?P<package>[@\w/-]+)["\']\))\s*;?',
    re.MULTILINE,
)


class JavaScriptDetector(BaseDetector):
    """Detect SDK usage in JavaScript/TypeScript files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

    def _get_base_package(self, package: str) -> str:
        """Get the base package name.

        For scoped packages like @org/pkg/sub, returns @org/pkg.
        For regular packages like pkg/sub, returns pkg.
        For langchain/*, returns langchain.
        """
        if package.startswith("@"):
            # Scoped package: @org/pkg or @org/pkg/subpath
            parts = package.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return package
        else:
            # Regular package: pkg or pkg/subpath
            return package.split("/")[0]

    def _is_ai_sdk(self, package: str) -> bool:
        """Check if package is an AI SDK."""
        base = self._get_base_package(package)
        return base in AI_SDK_PACKAGES or package in AI_SDK_PACKAGES

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in JavaScript/TypeScript file content.

        Args:
            content: JS/TS source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_packages: set[str] = set()

        # Check ES6 imports
        for match in ES_IMPORT_RE.finditer(content):
            package = match.group("package")
            base_package = self._get_base_package(package)

            if self._is_ai_sdk(package) and base_package not in seen_packages:
                seen_packages.add(base_package)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_package,
                        import_statement=match.group("statement").strip(),
                    ),
                )

        # Check CommonJS require
        for match in REQUIRE_RE.finditer(content):
            package = match.group("package")
            base_package = self._get_base_package(package)

            if self._is_ai_sdk(package) and base_package not in seen_packages:
                seen_packages.add(base_package)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_package,
                        import_statement=match.group("statement").strip(),
                    ),
                )
