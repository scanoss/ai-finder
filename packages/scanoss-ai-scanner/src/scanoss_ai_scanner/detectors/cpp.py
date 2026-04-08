"""C++ SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML SDK headers to detect
AI_SDK_HEADERS = frozenset(
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

    def _is_ai_sdk(self, header: str) -> bool:
        """Check if header is an AI SDK."""
        base = self._get_base_header(header)
        return base in AI_SDK_HEADERS

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in C++ file content.

        Args:
            content: C++ source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_headers: set[str] = set()

        for match in INCLUDE_RE.finditer(content):
            header = match.group("header")
            base_header = self._get_base_header(header)

            if self._is_ai_sdk(header) and base_header not in seen_headers:
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
