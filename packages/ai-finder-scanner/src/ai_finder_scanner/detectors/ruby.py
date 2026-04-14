"""Ruby SDK detector."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, SDKUsage
from .base import BaseDetector

# Fallback AI/ML SDK gem names (used when no KB matcher provided)
AI_SDK_GEMS_FALLBACK = frozenset(
    {
        "ruby-openai",
        "openai",
        "anthropic",
        "langchain",
        "langchainrb",
        "hugging-face",
        "replicate-ruby",
        "cohere-ruby",
    }
)

# Regex for Ruby require/require_relative statements
REQUIRE_RE = re.compile(
    r'^(?P<statement>require(?:_relative)?\s+["\'](?P<gem>[\w/-]+)["\'])',
    re.MULTILINE,
)


class RubyDetector(BaseDetector):
    """Detect SDK usage in Ruby files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".rb"})

    def _normalize_gem_name(self, gem: str) -> str:
        """Normalize gem name for matching."""
        # Ruby gems often use paths like 'openai/client'
        return gem.split("/")[0].replace("_", "-")

    def _is_ai_sdk_fallback(self, gem: str) -> bool:
        """Check if gem is an AI SDK using fallback patterns."""
        normalized = self._normalize_gem_name(gem)
        return normalized in AI_SDK_GEMS_FALLBACK

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect SDK usage in Ruby file content.

        Args:
            content: Ruby source code.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup.

        Yields:
            Finding for each SDK usage detected.
        """
        seen_gems: set[str] = set()

        for match in REQUIRE_RE.finditer(content):
            gem = match.group("gem")
            normalized = self._normalize_gem_name(gem)

            if normalized in seen_gems:
                continue

            # Try KB matcher first, fallback to hardcoded patterns
            if matcher:
                sdk_match = matcher.match_sdk(gem)
                if sdk_match:
                    seen_gems.add(normalized)
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
            elif self._is_ai_sdk_fallback(gem):
                seen_gems.add(normalized)
                yield Finding(
                    type=FindingType.SDK_USAGE,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    sdk_usage=SDKUsage(
                        sdk=normalized,
                        import_statement=match.group("statement").strip(),
                    ),
                )
