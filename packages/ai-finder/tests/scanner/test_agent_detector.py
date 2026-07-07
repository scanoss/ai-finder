"""Tests for agent detector."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.detectors.agents import AgentDetector
from ai_finder_scanner.models import FindingType


class TestAgentDetector:
    @pytest.fixture
    def detector(self) -> AgentDetector:
        return AgentDetector()

    def test_detect_langchain_agent(self, detector: AgentDetector) -> None:
        code = """
from langchain.agents import create_react_agent
agent = create_react_agent(llm, tools, prompt)
"""
        findings = list(detector.detect(code, Path("agent.py")))

        assert len(findings) >= 1
        finding = findings[0]
        assert finding.type == FindingType.AGENT
        assert finding.agent_info is not None
        assert finding.agent_info.framework == "langchain"

    def test_detect_crewai_agent(self, detector: AgentDetector) -> None:
        code = """
from crewai import Agent, Crew
researcher = Agent(role="researcher", goal="Find information")
"""
        findings = list(detector.detect(code, Path("crew.py")))

        assert len(findings) >= 1
        assert findings[0].agent_info.framework == "crewai"

    def test_detect_autogen_agent(self, detector: AgentDetector) -> None:
        code = """
from autogen import AssistantAgent, UserProxyAgent
assistant = AssistantAgent("assistant")
"""
        findings = list(detector.detect(code, Path("autogen_app.py")))

        assert len(findings) >= 1
        assert findings[0].agent_info.framework == "autogen"

    def test_detect_langgraph_agent(self, detector: AgentDetector) -> None:
        code = """
from langgraph.graph import StateGraph
graph = StateGraph(AgentState)
"""
        findings = list(detector.detect(code, Path("graph.py")))

        assert len(findings) >= 1
        assert findings[0].agent_info.framework == "langgraph"

    def test_detect_strands_agent(self, detector: AgentDetector) -> None:
        code = """
from strands import Agent, tool
agent = Agent(name="assistant")
"""
        findings = list(detector.detect(code, Path("orchestrator.py")))

        assert len(findings) >= 1
        assert findings[0].agent_info.framework == "strands"

    def test_strands_tool_import_is_not_agent(self, detector: AgentDetector) -> None:
        code = """
from strands import ToolContext, tool

@tool(context=True)
def search(q: str, tool_context: ToolContext) -> str:
    return q
"""
        findings = list(detector.detect(code, Path("tools.py")))

        assert findings == []

    def test_strands_model_provider_import_is_not_agent(self, detector: AgentDetector) -> None:
        code = """
from strands.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4.1-mini")
"""
        findings = list(detector.detect(code, Path("model_provider.py")))

        assert findings == []

    def test_no_false_positives(self, detector: AgentDetector) -> None:
        code = """
import requests
response = requests.get("https://api.example.com")
"""
        findings = list(detector.detect(code, Path("app.py")))

        assert len(findings) == 0
