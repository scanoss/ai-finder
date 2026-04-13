"""Rust SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# Fallback AI/ML crate names (used when no KB matcher provided)
AI_SDK_CRATES_FALLBACK = frozenset(
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

    def _is_ai_sdk_fallback(self, crate: str) -> bool:
        """Check if crate is an AI SDK using fallback patterns."""
        return crate in AI_SDK_CRATES_FALLBACK

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect SDK usage in Rust file content.

        Args:
            content: Rust source code.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup.

        Yields:
            Finding for each SDK usage detected.
        """
        seen_crates: set[str] = set()

        # Check use statements
        for match in USE_RE.finditer(content):
            crate = match.group("crate")

            if crate in seen_crates:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(crate)
                if sdk_match:
                    seen_crates.add(crate)
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
            elif self._is_ai_sdk_fallback(crate):
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

            if crate in seen_crates:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(crate)
                if sdk_match:
                    seen_crates.add(crate)
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
            elif self._is_ai_sdk_fallback(crate):
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
