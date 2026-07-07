"""Agent detector for AI agent frameworks."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import AgentInfo, Finding, FindingType


@dataclass
class AgentPattern:
    """Pattern for detecting agents."""

    pattern: re.Pattern[str]
    framework: str
    agent_type: str | None = None


class AgentDetector:
    """Detect AI agent usage in code."""

    PATTERNS = [
        # LangChain agents
        AgentPattern(
            re.compile(r"from\s+langchain\.agents\s+import|langchain\.agents\.", re.IGNORECASE),
            "langchain",
        ),
        AgentPattern(
            re.compile(
                r"create_react_agent|create_openai_functions_agent|AgentExecutor",
                re.IGNORECASE,
            ),
            "langchain",
            "react",
        ),
        # CrewAI
        AgentPattern(
            re.compile(r"from\s+crewai\s+import|crewai\.Agent|crewai\.Crew", re.IGNORECASE),
            "crewai",
        ),
        # AutoGen
        AgentPattern(
            re.compile(
                r"from\s+autogen\s+import|autogen\.AssistantAgent|autogen\.UserProxyAgent",
                re.IGNORECASE,
            ),
            "autogen",
        ),
        # LangGraph
        AgentPattern(
            re.compile(r"from\s+langgraph\.|langgraph\.graph|StateGraph", re.IGNORECASE),
            "langgraph",
        ),
        # Strands Agents
        AgentPattern(
            re.compile(
                r"from\s+strands\s+import|from\s+strands\.|strands\.Agent\b|strands_agents",
                re.IGNORECASE,
            ),
            "strands",
        ),
    ]

    @property
    def extensions(self) -> frozenset[str]:
        """File extensions this detector handles.

        Returns:
            Set of extensions (e.g., {".py"}).
        """
        return frozenset({".py"})

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def detect(
        self, content: str, path: Path | str, matcher: Any | None = None
    ) -> Iterator[Finding]:
        """Detect agent usage in code.

        Args:
            content: Source code content.
            path: Path to source file.
            matcher: Optional KB Matcher (unused for now).

        Yields:
            Finding for each agent framework detected.
        """
        seen_frameworks: set[str] = set()
        path_str = str(path)

        for match in re.finditer(r"^.*$", content, re.MULTILINE):
            line = match.group()
            line_num = content[: match.start()].count("\n") + 1

            for agent_pattern in self.PATTERNS:
                if agent_pattern.pattern.search(line):
                    framework = agent_pattern.framework

                    # Report each framework only once per file
                    if framework not in seen_frameworks:
                        seen_frameworks.add(framework)
                        yield Finding(
                            type=FindingType.AGENT,
                            file_path=path_str,
                            confidence=0.9,
                            line=line_num,
                            agent_info=AgentInfo(
                                framework=framework,
                                agent_type=agent_pattern.agent_type,
                            ),
                        )
                    break  # One finding per line
