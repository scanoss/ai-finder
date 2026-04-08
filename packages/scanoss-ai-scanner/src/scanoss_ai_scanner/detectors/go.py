"""Go SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML SDK import paths to detect
AI_SDK_IMPORTS = frozenset(
    {
        "github.com/sashabaranov/go-openai",
        "github.com/anthropics/anthropic-sdk-go",
        "github.com/cohere-ai/cohere-go",
        "github.com/replicate/replicate-go",
        "github.com/tmc/langchaingo",
    }
)

# Regex for Go import statements
# Single import: import "path" or import alias "path"
SINGLE_IMPORT_RE = re.compile(
    r'^import\s+(?:\w+\s+)?"(?P<path>[^"]+)"',
    re.MULTILINE,
)

# Import block: import ( ... )
IMPORT_BLOCK_RE = re.compile(
    r"import\s*\(\s*(?P<imports>.*?)\s*\)",
    re.DOTALL,
)

# Individual import within block
BLOCK_IMPORT_RE = re.compile(
    r'(?:\w+\s+)?"(?P<path>[^"]+)"',
)


class GoDetector(BaseDetector):
    """Detect SDK usage in Go files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".go"})

    def _is_ai_sdk(self, import_path: str) -> bool:
        """Check if import path is an AI SDK."""
        return import_path in AI_SDK_IMPORTS

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in Go file content.

        Args:
            content: Go source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_imports: set[str] = set()

        # Check single imports
        for match in SINGLE_IMPORT_RE.finditer(content):
            import_path = match.group("path")

            if self._is_ai_sdk(import_path) and import_path not in seen_imports:
                seen_imports.add(import_path)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=import_path,
                        import_statement=match.group(0).strip(),
                    ),
                )

        # Check import blocks
        for block_match in IMPORT_BLOCK_RE.finditer(content):
            block_content = block_match.group("imports")
            block_start = block_match.start()

            for import_match in BLOCK_IMPORT_RE.finditer(block_content):
                import_path = import_match.group("path")

                if self._is_ai_sdk(import_path) and import_path not in seen_imports:
                    seen_imports.add(import_path)
                    # Calculate line number within block
                    line = self._find_line_number(content, block_start + import_match.start())
                    yield Finding(
                        type=FindingType.SDK_USAGE,
                        file_path=str(path),
                        line=line,
                        confidence=1.0,
                        sdk_usage=SDKUsage(
                            sdk=import_path,
                            import_statement=f'import "{import_path}"',
                        ),
                    )
