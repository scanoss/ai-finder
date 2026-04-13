"""Tests for scanner data models."""

from scanoss_ai_scanner.models import (
    AgentInfo,
    AIComponent,
    DatasetInfo,
    EmbeddingInfo,
    Finding,
    FindingType,
    GuardrailInfo,
    ManifestDep,
    ModelInfo,
    PromptInfo,
    ScanResult,
    SDKUsage,
    ToolInfo,
    VectorStoreInfo,
)


class TestFindingType:
    def test_enum_values(self) -> None:
        assert FindingType.SDK_USAGE.value == "sdk_usage"
        assert FindingType.MANIFEST_DEP.value == "manifest_dep"
        assert FindingType.MODEL_FILE.value == "model_file"
        assert FindingType.MCP_SERVER.value == "mcp_server"
        assert FindingType.AI_COMPONENT.value == "ai_component"
        # New Phase 2 types
        assert FindingType.MCP_CLIENT.value == "mcp_client"
        assert FindingType.AGENT.value == "agent"
        assert FindingType.TOOL.value == "tool"
        assert FindingType.EMBEDDING.value == "embedding"
        assert FindingType.VECTOR_STORE.value == "vector_store"
        assert FindingType.PROMPT.value == "prompt"
        assert FindingType.GUARDRAIL.value == "guardrail"
        assert FindingType.DATASET.value == "dataset"


class TestSDKUsage:
    def test_create_sdk_usage(self) -> None:
        usage = SDKUsage(
            sdk="openai",
            import_statement="import openai",
        )
        assert usage.sdk == "openai"
        assert usage.import_statement == "import openai"
        assert usage.version is None

    def test_sdk_usage_with_version(self) -> None:
        usage = SDKUsage(
            sdk="openai",
            import_statement="from openai import ChatCompletion",
            version="1.0.0",
        )
        assert usage.version == "1.0.0"


class TestManifestDep:
    def test_create_manifest_dep(self) -> None:
        dep = ManifestDep(
            name="openai",
            version=">=1.0.0",
            manifest_file="requirements.txt",
        )
        assert dep.name == "openai"
        assert dep.version == ">=1.0.0"
        assert dep.manifest_file == "requirements.txt"


class TestModelInfo:
    def test_create_model_info(self) -> None:
        info = ModelInfo(format="gguf")
        assert info.format == "gguf"
        assert info.architecture is None
        assert info.parameter_count is None

    def test_model_info_full(self) -> None:
        info = ModelInfo(
            format="gguf",
            architecture="llama",
            parameter_count=7_000_000_000,
            quantization="Q4_K_M",
        )
        assert info.architecture == "llama"
        assert info.parameter_count == 7_000_000_000
        assert info.quantization == "Q4_K_M"


class TestAIComponent:
    def test_create_ai_component(self) -> None:
        comp = AIComponent(
            component_type="mcp_server",
            name="filesystem",
        )
        assert comp.component_type == "mcp_server"
        assert comp.name == "filesystem"


class TestAgentInfo:
    def test_create_agent_info(self) -> None:
        info = AgentInfo(framework="langchain", agent_type="react")
        assert info.framework == "langchain"
        assert info.agent_type == "react"

    def test_agent_info_minimal(self) -> None:
        info = AgentInfo(framework="crewai")
        assert info.framework == "crewai"
        assert info.agent_type is None


class TestToolInfo:
    def test_create_tool_info(self) -> None:
        info = ToolInfo(name="search", description="Search the web")
        assert info.name == "search"
        assert info.description == "Search the web"


class TestEmbeddingInfo:
    def test_create_embedding_info(self) -> None:
        info = EmbeddingInfo(provider="openai", model="text-embedding-3-small")
        assert info.provider == "openai"
        assert info.model == "text-embedding-3-small"


class TestVectorStoreInfo:
    def test_create_vector_store_info(self) -> None:
        info = VectorStoreInfo(provider="chroma", collection_name="docs")
        assert info.provider == "chroma"
        assert info.collection_name == "docs"


class TestPromptInfo:
    def test_create_prompt_info(self) -> None:
        info = PromptInfo(template_type="system", variables=["name", "context"])
        assert info.template_type == "system"
        assert info.variables == ["name", "context"]


class TestGuardrailInfo:
    def test_create_guardrail_info(self) -> None:
        info = GuardrailInfo(framework="nemoguardrails", guardrail_type="input")
        assert info.framework == "nemoguardrails"
        assert info.guardrail_type == "input"


class TestDatasetInfo:
    def test_create_dataset_info(self) -> None:
        info = DatasetInfo(source="huggingface", name="squad", split="train")
        assert info.source == "huggingface"
        assert info.name == "squad"
        assert info.split == "train"


class TestFinding:
    def test_create_sdk_finding(self) -> None:
        finding = Finding(
            type=FindingType.SDK_USAGE,
            file_path="src/main.py",
            line=10,
            confidence=1.0,
            sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
        )
        assert finding.type == FindingType.SDK_USAGE
        assert finding.file_path == "src/main.py"
        assert finding.line == 10
        assert finding.sdk_usage is not None
        assert finding.sdk_usage.sdk == "openai"

    def test_create_model_finding(self) -> None:
        finding = Finding(
            type=FindingType.MODEL_FILE,
            file_path="models/llama.gguf",
            confidence=0.95,
            model_info=ModelInfo(
                format="gguf",
                architecture="llama",
                parameter_count=7_000_000_000,
            ),
        )
        assert finding.model_info is not None
        assert finding.model_info.format == "gguf"
        assert finding.line is None

    def test_create_manifest_finding(self) -> None:
        finding = Finding(
            type=FindingType.MANIFEST_DEP,
            file_path="requirements.txt",
            line=5,
            confidence=1.0,
            manifest_dep=ManifestDep(
                name="langchain",
                version=">=0.1.0",
                manifest_file="requirements.txt",
            ),
        )
        assert finding.manifest_dep is not None
        assert finding.manifest_dep.name == "langchain"

    def test_create_agent_finding(self) -> None:
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=0.9,
            line=10,
            agent_info=AgentInfo(framework="langchain", agent_type="react"),
        )
        assert finding.type == FindingType.AGENT
        assert finding.agent_info is not None
        assert finding.agent_info.framework == "langchain"

    def test_create_embedding_finding(self) -> None:
        finding = Finding(
            type=FindingType.EMBEDDING,
            file_path="rag.py",
            confidence=0.95,
            line=25,
            embedding_info=EmbeddingInfo(provider="openai", model="text-embedding-3-small"),
        )
        assert finding.type == FindingType.EMBEDDING
        assert finding.embedding_info is not None
        assert finding.embedding_info.provider == "openai"

    def test_create_vector_store_finding(self) -> None:
        finding = Finding(
            type=FindingType.VECTOR_STORE,
            file_path="rag.py",
            confidence=0.95,
            line=30,
            vector_store_info=VectorStoreInfo(provider="chroma"),
        )
        assert finding.type == FindingType.VECTOR_STORE
        assert finding.vector_store_info is not None

    def test_create_dataset_finding(self) -> None:
        finding = Finding(
            type=FindingType.DATASET,
            file_path="train.py",
            confidence=0.9,
            line=5,
            dataset_info=DatasetInfo(source="huggingface", name="squad"),
        )
        assert finding.type == FindingType.DATASET
        assert finding.dataset_info is not None


class TestScanResult:
    def test_create_scan_result(self) -> None:
        result = ScanResult(
            root_path="/project",
            findings=[],
            files_scanned=100,
            duration_ms=1500,
        )
        assert result.root_path == "/project"
        assert len(result.findings) == 0
        assert result.files_scanned == 100
        assert result.duration_ms == 1500

    def test_scan_result_with_findings(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
        ]
        result = ScanResult(
            root_path="/project",
            findings=findings,
            files_scanned=50,
            duration_ms=500,
        )
        assert len(result.findings) == 1
        assert result.findings[0].type == FindingType.SDK_USAGE
