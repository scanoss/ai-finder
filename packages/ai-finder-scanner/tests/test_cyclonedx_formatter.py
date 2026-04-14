"""Extended tests for CycloneDX output formatter to increase coverage."""

from __future__ import annotations

import json

from ai_finder_scanner.models import (
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
from ai_finder_scanner.output.cyclonedx import CycloneDXFormatter


class TestCycloneDXLearningTypeInference:
    """Tests for learning type inference."""

    def test_infer_learning_type_supervised_default(self) -> None:
        formatter = CycloneDXFormatter()
        assert formatter._infer_learning_type(None) == "supervised"
        assert formatter._infer_learning_type("llama") == "supervised"

    def test_infer_learning_type_self_supervised_embed(self) -> None:
        formatter = CycloneDXFormatter()
        assert formatter._infer_learning_type("text-embedding-ada") == "self-supervised"
        assert formatter._infer_learning_type("bert-base") == "self-supervised"
        assert formatter._infer_learning_type("BERT-large") == "self-supervised"

    def test_infer_learning_type_reinforcement(self) -> None:
        formatter = CycloneDXFormatter()
        assert formatter._infer_learning_type("ppo-model") == "reinforcement-learning"
        assert formatter._infer_learning_type("dqn-agent") == "reinforcement-learning"
        assert formatter._infer_learning_type("rl-trained") == "reinforcement-learning"


class TestCycloneDXIOFormatInference:
    """Tests for input/output format inference."""

    def test_infer_io_format_default_text(self) -> None:
        formatter = CycloneDXFormatter()
        inputs, outputs = formatter._infer_io_format(None)
        assert inputs == [{"format": "string"}]
        assert outputs == [{"format": "string"}]

    def test_infer_io_format_image_models(self) -> None:
        formatter = CycloneDXFormatter()
        for arch in ["resnet50", "vgg16", "yolov8", "vit-base", "CLIP"]:
            inputs, outputs = formatter._infer_io_format(arch)
            assert inputs == [{"format": "image"}]
            assert outputs == [{"format": "tensor"}]

    def test_infer_io_format_audio_models(self) -> None:
        formatter = CycloneDXFormatter()
        for arch in ["whisper-large", "wav2vec2"]:
            inputs, outputs = formatter._infer_io_format(arch)
            assert inputs == [{"format": "audio"}]
            assert outputs == [{"format": "string"}]

    def test_infer_io_format_multimodal(self) -> None:
        formatter = CycloneDXFormatter()
        inputs, outputs = formatter._infer_io_format("llava-1.5")
        assert {"format": "string"} in inputs
        assert {"format": "image"} in inputs
        assert outputs == [{"format": "string"}]

    def test_infer_io_format_llm_default(self) -> None:
        formatter = CycloneDXFormatter()
        inputs, outputs = formatter._infer_io_format("llama-3-8b")
        assert inputs == [{"format": "string"}]
        assert outputs == [{"format": "string"}]


class TestCycloneDXFindingToComponent:
    """Tests for finding to component conversion."""

    def test_model_file_with_full_metadata(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.MODEL_FILE,
            file_path="models/llama-3-8b.gguf",
            confidence=1.0,
            model_info=ModelInfo(
                format="gguf",
                architecture="llama",
                parameter_count=8000000000,
                quantization="Q4_K_M",
            ),
        )
        component = formatter._finding_to_component(finding)
        assert component is not None
        assert component["type"] == "machine-learning-model"
        assert component["name"] == "llama-3-8b.gguf"
        assert "modelCard" in component
        assert "modelParameters" in component["modelCard"]
        assert component["modelCard"]["modelParameters"]["learningType"] == "supervised"
        assert component["modelCard"]["modelParameters"]["modelArchitecture"] == "llama"
        assert component["modelCard"]["modelParameters"]["architectureFamily"] == "transformer"

    def test_model_file_architecture_families(self) -> None:
        formatter = CycloneDXFormatter()
        test_cases = [
            ("llama", "transformer"),
            ("mistral", "transformer"),
            ("gpt", "transformer"),
            ("bert", "transformer"),
            ("resnet", "convolutional neural network"),
            ("yolo", "convolutional neural network"),
            ("lstm", "recurrent neural network"),
        ]
        for arch, expected_family in test_cases:
            finding = Finding(
                type=FindingType.MODEL_FILE,
                file_path=f"model-{arch}.bin",
                confidence=1.0,
                model_info=ModelInfo(format="bin", architecture=arch),
            )
            component = formatter._finding_to_component(finding)
            arch_family = component["modelCard"]["modelParameters"].get("architectureFamily")
            assert arch_family == expected_family

    def test_model_file_properties(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.MODEL_FILE,
            file_path="model.gguf",
            confidence=1.0,
            model_info=ModelInfo(
                format="gguf",
                quantization="Q4_K_M",
                parameter_count=7000000000,
            ),
        )
        component = formatter._finding_to_component(finding)
        assert "properties" in component
        props = {p["name"]: p["value"] for p in component["properties"]}
        assert props["ai-finder:model:format"] == "gguf"
        assert props["ai-finder:model:quantization"] == "Q4_K_M"
        assert props["ai-finder:model:parameters"] == "7000000000"

    def test_mcp_server_with_ai_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.MCP_SERVER,
            file_path="server.py",
            confidence=1.0,
            ai_component=AIComponent(component_type="mcp_server", name="my-mcp-server"),
        )
        component = formatter._finding_to_component(finding)
        assert component is not None
        assert component["name"] == "my-mcp-server"
        assert component["type"] == "library"
        props = {p["name"]: p["value"] for p in component["properties"]}
        assert props["ai-finder:mcp:role"] == "server"

    def test_mcp_server_without_ai_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.MCP_SERVER,
            file_path="server.py",
            confidence=1.0,
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "mcp-server"

    def test_mcp_client(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.MCP_CLIENT,
            file_path="client.py",
            confidence=1.0,
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "mcp-client"
        props = {p["name"]: p["value"] for p in component["properties"]}
        assert props["ai-finder:mcp:role"] == "client"

    def test_agent_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=1.0,
            agent_info=AgentInfo(framework="autogen"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "autogen-agent"
        assert component["type"] == "library"

    def test_tool_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.TOOL,
            file_path="tool.py",
            confidence=1.0,
            tool_info=ToolInfo(name="web_search"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "web_search"

    def test_embedding_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.EMBEDDING,
            file_path="embed.py",
            confidence=1.0,
            embedding_info=EmbeddingInfo(provider="cohere", model="embed-english-v3"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "cohere-embeddings"

    def test_vector_store_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.VECTOR_STORE,
            file_path="store.py",
            confidence=1.0,
            vector_store_info=VectorStoreInfo(provider="chromadb"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "chromadb"

    def test_prompt_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.PROMPT,
            file_path="prompt.py",
            confidence=1.0,
            prompt_info=PromptInfo(template_type="system"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "prompt-system"

    def test_guardrail_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.GUARDRAIL,
            file_path="guard.py",
            confidence=1.0,
            guardrail_info=GuardrailInfo(framework="nemo-guardrails"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "nemo-guardrails"

    def test_dataset_component(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(name="imdb", source="huggingface"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "imdb"
        assert component["type"] == "data"
        assert "data:" in component["bom-ref"]

    def test_dataset_component_no_name(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(source="local"),
        )
        component = formatter._finding_to_component(finding)
        assert component["name"] == "local-dataset"


class TestCycloneDXPhase2ComponentName:
    """Tests for _get_phase2_component_name."""

    def test_unknown_component_fallback(self) -> None:
        formatter = CycloneDXFormatter()
        finding = Finding(
            type=FindingType.TOOL,
            file_path="test.py",
            confidence=1.0,
        )
        name = formatter._get_phase2_component_name(finding)
        assert name == "unknown-component"


class TestCycloneDXFormatWithGraph:
    """Tests for format method with component graph."""

    def test_format_with_graph_adds_file_components(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        graph.add_edge("main.py", "openai", "contains")

        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=1,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should have file component
        file_components = [c for c in data["components"] if c["type"] == "file"]
        assert len(file_components) == 1
        assert file_components[0]["name"] == "main.py"

        # Should have dependencies
        assert "dependencies" in data

    def test_format_with_graph_builds_dependencies(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        graph.add_edge("main.py", "openai", "contains")
        graph.add_edge("openai", "httpx", "dependsOn")

        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=2,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="httpx", import_statement="import httpx"),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=1,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Check dependencies structure
        assert "dependencies" in data
        assert len(data["dependencies"]) > 0, "Expected dependencies to be generated"
        deps_by_ref = {d["ref"]: d["dependsOn"] for d in data["dependencies"]}

        # openai should depend on httpx per the graph edge
        openai_ref = "pkg:openai"
        assert openai_ref in deps_by_ref, (
            f"Expected {openai_ref} in dependencies, got: {list(deps_by_ref.keys())}"
        )
        assert any("httpx" in dep for dep in deps_by_ref[openai_ref]), (
            f"Expected httpx in {openai_ref} dependencies, got: {deps_by_ref[openai_ref]}"
        )

    def test_format_skips_function_paths(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        graph.add_edge("main.py::my_func", "openai", "contains")
        graph.add_edge("main.py", "openai", "contains")

        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=1,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Function path should not be a component
        component_names = [c["name"] for c in data["components"]]
        assert "main.py::my_func" not in component_names
        assert "main.py" in component_names


class TestCycloneDXDeduplication:
    """Tests for component deduplication."""

    def test_format_deduplicates_components(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="other.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="from openai import Client"),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=2,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        openai_components = [c for c in data["components"] if c["name"] == "openai"]
        assert len(openai_components) == 1

    def test_format_updates_version_from_manifest(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
            Finding(
                type=FindingType.MANIFEST_DEP,
                file_path="requirements.txt",
                line=1,
                confidence=1.0,
                manifest_dep=ManifestDep(
                    name="openai",
                    version="1.5.0",
                    manifest_file="requirements.txt",
                ),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=2,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        openai_comp = next(c for c in data["components"] if c["name"] == "openai")
        assert openai_comp.get("version") == "1.5.0"


class TestCycloneDXPurlBuilding:
    """Tests for PURL building."""

    def test_build_purl_npm_scoped(self) -> None:
        formatter = CycloneDXFormatter()
        purl = formatter._build_purl("npm", "@vercel/ai", "2.0.0")
        assert purl == "pkg:npm/vercel/ai@2.0.0"

    def test_build_purl_golang_path(self) -> None:
        formatter = CycloneDXFormatter()
        purl = formatter._build_purl("golang", "github.com/anthropics/anthropic-sdk-go", "v0.1.0")
        assert "github.com/anthropics/anthropic-sdk-go" in purl
        assert "@v0.1.0" in purl

    def test_build_purl_strips_version_prefix(self) -> None:
        formatter = CycloneDXFormatter()
        assert "@1.0.0" in formatter._build_purl("pypi", "test", "^1.0.0")
        assert "@2.0.0" in formatter._build_purl("pypi", "test", ">=2.0.0")
        assert "@3.0.0" in formatter._build_purl("pypi", "test", "~3.0.0")


class TestCycloneDXLicenseHandling:
    """Tests for license handling."""

    def test_components_get_noassertion_license(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai"),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=1,
            duration_ms=10,
        )

        formatter = CycloneDXFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        comp = data["components"][0]
        assert "licenses" in comp
        assert comp["licenses"][0]["expression"] == "NOASSERTION"
