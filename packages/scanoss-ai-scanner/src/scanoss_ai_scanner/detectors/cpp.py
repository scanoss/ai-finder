"""C++ SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# Fallback AI/ML SDK headers (used when no KB matcher provided)
AI_SDK_HEADERS_FALLBACK = frozenset(
    {
        "onnxruntime",
        "tensorflow",
        "torch",
        "libtorch",
        "ATen",
        "caffe",
        "caffe2",
        "mxnet",
        "opencv",
        "dlib",
        "llama",
        "whisper",
        "ggml",
    }
)

# Regex for #include statements
INCLUDE_RE = re.compile(
    r'^(?P<statement>#include\s*[<"](?P<header>[^>"]+)[>"])',
    re.MULTILINE,
)


class CppDetector(BaseDetector):
    """Detect SDK usage in C++ files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".cpp", ".cc", ".cxx", ".hpp", ".h", ".hxx"})

    def _get_base_header(self, header: str) -> str:
        """Get the base header name (first directory component or filename)."""
        # Remove .h/.hpp suffix for matching
        clean = header.replace(".h", "").replace(".hpp", "")
        # Get first path component
        return clean.split("/")[0]

    def _is_ai_sdk_fallback(self, header: str) -> bool:
        """Check if header is an AI SDK using fallback patterns."""
        base = self._get_base_header(header)
        return base in AI_SDK_HEADERS_FALLBACK

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect SDK usage in C++ file content.

        Args:
            content: C++ source code.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup.

        Yields:
            Finding for each SDK usage detected.
        """
        seen_headers: set[str] = set()

        for match in INCLUDE_RE.finditer(content):
            header = match.group("header")
            base_header = self._get_base_header(header)

            if base_header in seen_headers:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(header)
                if sdk_match:
                    seen_headers.add(base_header)
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
            elif self._is_ai_sdk_fallback(header):
                seen_headers.add(base_header)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=base_header,
                        import_statement=match.group("statement").strip(),
                    ),
                )
