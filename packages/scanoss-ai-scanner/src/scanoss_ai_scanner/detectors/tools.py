"""Tools detector for function tools."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import Finding, FindingType, ToolInfo


@dataclass
class ToolPattern:
    """Pattern for detecting tools."""

    pattern: re.Pattern[str]
    source: str


class ToolsDetector:
    """Detect function tools in code."""

    PATTERNS = [
        # LangChain tools
        ToolPattern(re.compile(r"@tool\b|from\s+langchain\.tools\s+import\s+tool"), "langchain"),
        ToolPattern(re.compile(r"StructuredTool|BaseTool"), "langchain"),
        # OpenAI function calling
        ToolPattern(re.compile(r'"type":\s*"function"'), "openai"),
        ToolPattern(re.compile(r"function_declarations"), "openai"),
        # Anthropic tools
        ToolPattern(re.compile(r"tool_use|tools.*input_schema"), "anthropic"),
    ]

    @property
    def extensions(self) -> frozenset[str]:
        """File extensions this detector handles."""
        return frozenset({".py"})

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(self, content: str, path: Path | str, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect tool usage in code.

        Args:
            content: Source code content.
            path: Path to source file.
            matcher: Optional KB Matcher (unused for now).

        Yields:
            Finding for each tool detected.
        """
        path_str = str(path)
        seen_sources: set[str] = set()

        for match in re.finditer(r"^.*$", content, re.MULTILINE):
            line = match.group()
            line_num = content[:match.start()].count("\n") + 1

            for tool_pattern in self.PATTERNS:
                if tool_pattern.pattern.search(line):
                    if tool_pattern.source not in seen_sources:
                        seen_sources.add(tool_pattern.source)
                        yield Finding(
                            type=FindingType.TOOL,
                            file_path=path_str,
                            confidence=0.85,
                            line=line_num,
                            tool_info=ToolInfo(name="detected_tool"),
                        )
                    break
