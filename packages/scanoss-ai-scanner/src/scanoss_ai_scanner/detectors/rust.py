"""Rust SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# AI/ML crate names to detect
AI_SDK_CRATES = frozenset(
    {
        "async_openai",
        "openai_api",
        "candle_core",
        "candle_nn",
        "candle_transformers",
        "llm",
        "llm_chain",
        "rust_bert",
        "ort",  # ONNX Runtime
        "tch",  # PyTorch bindings
        "tract",  # ML inference
    }
)

# Regex for use statements: use crate_name::...
USE_RE = re.compile(
    r"^(?P<statement>use\s+(?P<crate>[\w_]+)(?:::.+)?)\s*;",
    re.MULTILINE,
)

# Regex for extern crate: extern crate crate_name;
EXTERN_CRATE_RE = re.compile(
    r"^(?P<statement>extern\s+crate\s+(?P<crate>[\w_]+))\s*;",
    re.MULTILINE,
)


class RustDetector(BaseDetector):
    """Detect SDK usage in Rust files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".rs"})

    def _is_ai_sdk(self, crate: str) -> bool:
        """Check if crate is an AI SDK."""
        return crate in AI_SDK_CRATES

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path) -> Iterator[Finding]:
        """Detect SDK usage in Rust file content.

        Args:
            content: Rust source code.
            path: File path (relative to scan root).

        Yields:
            Finding for each SDK usage detected.
        """
        seen_crates: set[str] = set()

        # Check use statements
        for match in USE_RE.finditer(content):
            crate = match.group("crate")

            if self._is_ai_sdk(crate) and crate not in seen_crates:
                seen_crates.add(crate)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=crate,
                        import_statement=match.group("statement").strip(),
                    ),
                )

        # Check extern crate statements
        for match in EXTERN_CRATE_RE.finditer(content):
            crate = match.group("crate")

            if self._is_ai_sdk(crate) and crate not in seen_crates:
                seen_crates.add(crate)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=crate,
                        import_statement=match.group("statement").strip(),
                    ),
                )
