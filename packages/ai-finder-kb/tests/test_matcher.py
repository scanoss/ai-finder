"""Tests for KB matcher."""

import json

import pytest
from ai_finder_kb.database import Database
from ai_finder_kb.matcher import Matcher
from ai_finder_kb.models import MCPMatch, ModelMatch, SDKMatch


@pytest.fixture
def db_with_data(temp_db_path):
    """Create a database with test data."""
    with Database(temp_db_path) as db:
        db.initialize()

        # Insert test SDKs
        db.execute(
            "INSERT INTO sdks (id, purl, patterns, category, license) VALUES (?, ?, ?, ?, ?)",
            (
                "openai-python",
                "pkg:pypi/openai",
                json.dumps(["openai", "from openai"]),
                "llm-client",
                "MIT",
            ),
        )
        db.execute(
            "INSERT INTO sdks (id, purl, patterns, category, license) VALUES (?, ?, ?, ?, ?)",
            (
                "anthropic-python",
                "pkg:pypi/anthropic",
                json.dumps(["anthropic", "from anthropic"]),
                "llm-client",
                "MIT",
            ),
        )

        # Insert test model
        db.execute(
            "INSERT INTO models (purl, name, organization, architecture, license) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "pkg:huggingface/TinyLlama/TinyLlama-1.1B",
                "TinyLlama-1.1B",
                "TinyLlama",
                "llama",
                "Apache-2.0",
            ),
        )
        db.execute(
            "INSERT INTO models (purl, name, organization, architecture, license) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "pkg:huggingface/mistralai/Mistral-7B-v0.1",
                "Mistral-7B-v0.1",
                "mistralai",
                "mistral",
                "Apache-2.0",
            ),
        )

        # Insert test MCP server
        db.execute(
            "INSERT INTO mcp_servers (id, purl, patterns, description) VALUES (?, ?, ?, ?)",
            (
                "mcp-filesystem",
                "pkg:npm/@modelcontextprotocol/server-filesystem",
                json.dumps(["@modelcontextprotocol/server-filesystem"]),
                "MCP filesystem server",
            ),
        )

        db.commit()
        yield db


class TestMatcherSDK:
    def test_match_sdk_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_sdk("openai")

        assert result is not None
        assert isinstance(result, SDKMatch)
        assert result.id == "openai-python"
        assert result.purl == "pkg:pypi/openai"

    def test_match_sdk_pattern_match(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_sdk("from openai import ChatCompletion")

        assert result is not None
        assert result.id == "openai-python"

    def test_match_sdk_not_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_sdk("unknown-sdk")
        assert result is None

    def test_match_all_sdks(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        results = list(matcher.match_all_sdks(["openai", "anthropic", "unknown"]))

        assert len(results) == 2
        ids = {r.id for r in results}
        assert "openai-python" in ids
        assert "anthropic-python" in ids

    def test_lookup_sdk_by_purl(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.lookup_sdk("pkg:pypi/openai")

        assert result is not None
        assert isinstance(result, SDKMatch)
        assert result.id == "openai-python"
        assert result.purl == "pkg:pypi/openai"
        assert result.category == "llm-client"

    def test_lookup_sdk_not_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.lookup_sdk("pkg:pypi/nonexistent")
        assert result is None


class TestMatcherModel:
    def test_match_model_by_name(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_model("tinyllama-1.1b.gguf")

        assert result is not None
        assert isinstance(result, ModelMatch)
        assert "TinyLlama" in result.name

    def test_match_model_case_insensitive(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_model("TINYLLAMA-1.1B")

        assert result is not None
        assert "TinyLlama" in result.name

    def test_match_model_not_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_model("unknown-model.bin")
        assert result is None

    def test_lookup_model_by_purl(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.lookup_model("pkg:huggingface/TinyLlama/TinyLlama-1.1B")

        assert result is not None
        assert result.name == "TinyLlama-1.1B"


class TestMatcherMCP:
    def test_match_mcp_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_mcp("@modelcontextprotocol/server-filesystem")

        assert result is not None
        assert isinstance(result, MCPMatch)
        assert result.id == "mcp-filesystem"

    def test_match_mcp_not_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.match_mcp("unknown-mcp-server")
        assert result is None

    def test_lookup_mcp_by_purl(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.lookup_mcp("pkg:npm/@modelcontextprotocol/server-filesystem")

        assert result is not None
        assert isinstance(result, MCPMatch)
        assert result.id == "mcp-filesystem"
        assert result.description == "MCP filesystem server"

    def test_lookup_mcp_not_found(self, db_with_data) -> None:
        matcher = Matcher(db_with_data)
        result = matcher.lookup_mcp("pkg:npm/nonexistent")
        assert result is None
