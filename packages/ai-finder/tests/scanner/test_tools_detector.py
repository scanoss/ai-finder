"""Tests for tools detector."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.detectors.tools import ToolsDetector
from ai_finder_scanner.models import FindingType


class TestToolsDetector:
    @pytest.fixture
    def detector(self) -> ToolsDetector:
        return ToolsDetector()

    def test_detect_langchain_tool_decorator(self, detector: ToolsDetector) -> None:
        code = '''
from langchain.tools import tool

@tool
def search(query: str) -> str:
    """Search the web."""
    return "results"
'''
        findings = list(detector.detect(code, Path("tools.py")))

        assert len(findings) >= 1
        assert findings[0].type == FindingType.TOOL

    def test_indented_tool_decorator_detected(self, detector: ToolsDetector) -> None:
        # Real decorators are often indented (methods, nested defs).
        code = "class A:\n    @tool(context=True)\n    def search(self, q: str) -> str:\n        return q\n"
        findings = list(detector.detect(code, Path("tools.py")))
        assert any(f.type == FindingType.TOOL for f in findings)

    def test_at_tool_in_docstring_is_not_detected(self, detector: ToolsDetector) -> None:
        # Prose mentioning "@tool" (docstring/comment) must NOT be a tool finding.
        code = '"""Each agent is wrapped as a @tool function the orchestrator calls."""\n'
        findings = list(detector.detect(code, Path("orchestrator.py")))
        assert [f for f in findings if f.type == FindingType.TOOL] == []

    def test_detect_structured_tool(self, detector: ToolsDetector) -> None:
        code = """
from langchain.tools import StructuredTool
calculator = StructuredTool.from_function(calculate)
"""
        findings = list(detector.detect(code, Path("tools.py")))

        assert len(findings) >= 1

    def test_detect_openai_function_calling(self, detector: ToolsDetector) -> None:
        code = """
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
        }
    }
]
"""
        findings = list(detector.detect(code, Path("functions.py")))

        assert len(findings) >= 1

    def test_no_false_positives(self, detector: ToolsDetector) -> None:
        code = """
import requests
response = requests.get("https://api.example.com")
"""
        findings = list(detector.detect(code, Path("app.py")))

        assert len(findings) == 0
