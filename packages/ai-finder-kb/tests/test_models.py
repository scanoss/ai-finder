"""Tests for KB data models."""

from ai_finder_kb.models import AncestryEdge, MCPMatch, ModelMatch, SDKMatch


class TestSDKMatch:
    def test_create_sdk_match(self) -> None:
        match = SDKMatch(
            id="openai-python",
            purl="pkg:pypi/openai",
            category="llm-client",
            license="MIT",
            confidence=1.0,
        )
        assert match.id == "openai-python"
        assert match.purl == "pkg:pypi/openai"
        assert match.category == "llm-client"
        assert match.license == "MIT"
        assert match.confidence == 1.0

    def test_sdk_match_defaults(self) -> None:
        match = SDKMatch(
            id="test",
            purl="pkg:pypi/test",
            category="test",
        )
        assert match.license is None
        assert match.confidence == 1.0


class TestModelMatch:
    def test_create_model_match(self) -> None:
        match = ModelMatch(
            purl="pkg:huggingface/TinyLlama/TinyLlama-1.1B",
            name="TinyLlama-1.1B",
            organization="TinyLlama",
            architecture="llama",
            license="Apache-2.0",
            confidence=0.95,
        )
        assert match.purl == "pkg:huggingface/TinyLlama/TinyLlama-1.1B"
        assert match.name == "TinyLlama-1.1B"
        assert match.architecture == "llama"
        assert match.organization == "TinyLlama"

    def test_model_match_defaults(self) -> None:
        match = ModelMatch(
            purl="pkg:huggingface/test/model",
            name="test-model",
        )
        assert match.organization is None
        assert match.architecture is None
        assert match.format is None
        assert match.parameter_count is None
        assert match.license is None
        assert match.confidence == 1.0


class TestMCPMatch:
    def test_create_mcp_match(self) -> None:
        match = MCPMatch(
            id="mcp-filesystem",
            purl="pkg:npm/@modelcontextprotocol/server-filesystem",
            description="MCP server for filesystem access",
            confidence=1.0,
        )
        assert match.id == "mcp-filesystem"
        assert "filesystem" in match.description.lower()

    def test_mcp_match_defaults(self) -> None:
        match = MCPMatch(
            id="test",
            purl="pkg:npm/test",
            description="Test server",
        )
        assert match.confidence == 1.0


class TestAncestryEdge:
    def test_create_ancestry_edge(self) -> None:
        edge = AncestryEdge(
            source_purl="pkg:huggingface/user/my-model",
            target_purl="pkg:huggingface/meta-llama/Llama-2-7b",
            relation_type="fine-tuned",
            confidence=0.85,
            declared=False,
        )
        assert edge.source_purl == "pkg:huggingface/user/my-model"
        assert edge.target_purl == "pkg:huggingface/meta-llama/Llama-2-7b"
        assert edge.relation_type == "fine-tuned"
        assert not edge.declared

    def test_ancestry_edge_defaults(self) -> None:
        edge = AncestryEdge(
            source_purl="pkg:test/source",
            target_purl="pkg:test/target",
            relation_type="derived",
            confidence=0.5,
        )
        assert edge.declared is False
