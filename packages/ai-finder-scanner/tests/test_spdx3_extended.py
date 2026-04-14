"""Extended tests for SPDX 3.0 output formatter to increase coverage."""

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
from ai_finder_scanner.output.spdx3 import SPDX3Formatter


class TestSPDX3DomainInference:
    """Tests for AI domain inference."""

    def test_infer_domain_text_generation(self) -> None:
        formatter = SPDX3Formatter()
        for arch in ["llama", "gpt", "mistral", "phi", "gemma"]:
            assert formatter._infer_domain(arch) == "text-generation"

    def test_infer_domain_embedding(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._infer_domain("bert-base") == "embedding"
        assert formatter._infer_domain("text-embed-3") == "embedding"

    def test_infer_domain_speech(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._infer_domain("whisper-large") == "speech-to-text"
        assert formatter._infer_domain("wav2vec2") == "speech-to-text"

    def test_infer_domain_image_generation(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._infer_domain("stable-diffusion-xl") == "image-generation"
        assert formatter._infer_domain("sdxl-turbo") == "image-generation"

    def test_infer_domain_image_classification(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._infer_domain("resnet50") == "image-classification"
        assert formatter._infer_domain("yolov8") == "image-classification"
        assert formatter._infer_domain("vgg16") == "image-classification"

    def test_infer_domain_unknown(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._infer_domain(None) == "NOASSERTION"
        assert formatter._infer_domain("custom-model") == "NOASSERTION"


class TestSPDX3PathNormalization:
    """Tests for path normalization."""

    def test_normalize_path_unix(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._normalize_path("models/llama/model.bin") == "models/llama/model.bin"

    def test_normalize_path_windows(self) -> None:
        formatter = SPDX3Formatter()
        assert formatter._normalize_path("models\\llama\\model.bin") == "models/llama/model.bin"


class TestSPDX3IdGeneration:
    """Tests for SPDX ID generation."""

    def test_generate_stable_spdx_id_with_version(self) -> None:
        formatter = SPDX3Formatter()
        id1 = formatter._generate_stable_spdx_id("package", "openai", "1.0.0")
        id2 = formatter._generate_stable_spdx_id("package", "openai", "1.0.0")
        assert id1 == id2  # Stable/deterministic

    def test_generate_stable_spdx_id_different_versions(self) -> None:
        formatter = SPDX3Formatter()
        id1 = formatter._generate_stable_spdx_id("package", "openai", "1.0.0")
        id2 = formatter._generate_stable_spdx_id("package", "openai", "2.0.0")
        assert id1 != id2  # Different versions = different IDs

    def test_generate_stable_spdx_id_normalizes_version(self) -> None:
        formatter = SPDX3Formatter()
        id1 = formatter._generate_stable_spdx_id("package", "openai", "^1.0.0")
        id2 = formatter._generate_stable_spdx_id("package", "openai", "1.0.0")
        assert id1 == id2  # ^1.0.0 normalized to 1.0.0

    def test_generate_stable_spdx_id_handles_special_chars(self) -> None:
        formatter = SPDX3Formatter()
        spdx_id = formatter._generate_stable_spdx_id("package", "@anthropic-ai/sdk", "1.0.0")
        assert "@" not in spdx_id
        assert "anthropic-ai" in spdx_id


class TestSPDX3Phase2ElementName:
    """Tests for Phase 2 element naming."""

    def test_agent_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=1.0,
            agent_info=AgentInfo(framework="langchain"),
        )
        assert formatter._get_phase2_element_name(finding) == "langchain-agent"

    def test_embedding_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.EMBEDDING,
            file_path="embed.py",
            confidence=1.0,
            embedding_info=EmbeddingInfo(provider="openai", model="text-embedding-3"),
        )
        assert formatter._get_phase2_element_name(finding) == "openai-embeddings"

    def test_vector_store_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.VECTOR_STORE,
            file_path="store.py",
            confidence=1.0,
            vector_store_info=VectorStoreInfo(provider="weaviate"),
        )
        assert formatter._get_phase2_element_name(finding) == "weaviate"

    def test_tool_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.TOOL,
            file_path="tool.py",
            confidence=1.0,
            tool_info=ToolInfo(name="calculator"),
        )
        assert formatter._get_phase2_element_name(finding) == "calculator"

    def test_guardrail_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.GUARDRAIL,
            file_path="guard.py",
            confidence=1.0,
            guardrail_info=GuardrailInfo(framework="llm-guard"),
        )
        assert formatter._get_phase2_element_name(finding) == "llm-guard"

    def test_prompt_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.PROMPT,
            file_path="prompt.py",
            confidence=1.0,
            prompt_info=PromptInfo(template_type="few-shot"),
        )
        assert formatter._get_phase2_element_name(finding) == "prompt-few-shot"

    def test_unknown_element_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=1.0,
        )
        assert formatter._get_phase2_element_name(finding) == "unknown-component"


class TestSPDX3FindingToElement:
    """Tests for finding to element conversion."""

    def test_mcp_server_element(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.MCP_SERVER,
            file_path="server.py",
            confidence=1.0,
            ai_component=AIComponent(component_type="mcp_server", name="my-server"),
        )
        element = formatter._finding_to_element(finding)
        assert element is not None
        assert element["type"] == "software_Package"
        assert element["name"] == "my-server"
        assert "MCP" in element["summary"]
        assert "server" in element["comment"]

    def test_mcp_client_element(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.MCP_CLIENT,
            file_path="client.py",
            confidence=1.0,
        )
        element = formatter._finding_to_element(finding)
        assert element["name"] == "mcp-client"
        assert "client" in element["comment"]

    def test_dataset_element(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(name="glue", source="huggingface", split="train"),
        )
        element = formatter._finding_to_element(finding)
        assert element is not None
        assert element["type"] == "dataset_DatasetPackage"
        assert element["name"] == "glue"
        assert element["dataset_datasetType"] == "text"
        assert "training" in element["dataset_intendedUse"]

    def test_dataset_element_no_name(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(source="local"),
        )
        element = formatter._finding_to_element(finding)
        assert element["name"] == "local-dataset"

    def test_agent_element(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=1.0,
            agent_info=AgentInfo(framework="crewai"),
        )
        element = formatter._finding_to_element(finding)
        assert element is not None
        assert element["type"] == "software_Package"
        assert element["name"] == "crewai-agent"

    def test_model_file_element(self) -> None:
        formatter = SPDX3Formatter()
        finding = Finding(
            type=FindingType.MODEL_FILE,
            file_path="models/llama.gguf",
            confidence=1.0,
            model_info=ModelInfo(
                format="gguf",
                architecture="llama",
                parameter_count=7000000000,
                quantization="Q4_K_M",
            ),
        )
        element = formatter._finding_to_element(finding)
        assert element is not None
        assert element["type"] == "ai_AIPackage"
        assert element["name"] == "models/llama.gguf"
        assert element["ai_typeOfModel"] == "llama"
        assert element["ai_domain"] == "text-generation"
        assert element["ai_autonomyType"] == "assistive"
        assert "ai_hyperparameter" in element
        hyperparams = {h["name"]: h["value"] for h in element["ai_hyperparameter"]}
        assert hyperparams["parameter_count"] == "7000000000"
        assert hyperparams["quantization"] == "Q4_K_M"


class TestSPDX3MergeMetadata:
    """Tests for element metadata merging."""

    def test_merge_replaces_noassertion(self) -> None:
        formatter = SPDX3Formatter()
        existing = {
            "type": "software_Package",
            "name": "test",
            "software_declaredLicense": "NOASSERTION",
        }
        new = {
            "type": "software_Package",
            "name": "test",
            "software_declaredLicense": "MIT",
        }
        formatter._merge_element_metadata(existing, new)
        assert existing["software_declaredLicense"] == "MIT"

    def test_merge_does_not_replace_real_value(self) -> None:
        formatter = SPDX3Formatter()
        existing = {
            "type": "software_Package",
            "name": "test",
            "software_declaredLicense": "Apache-2.0",
        }
        new = {
            "type": "software_Package",
            "name": "test",
            "software_declaredLicense": "MIT",
        }
        formatter._merge_element_metadata(existing, new)
        assert existing["software_declaredLicense"] == "Apache-2.0"

    def test_merge_adds_missing_fields(self) -> None:
        formatter = SPDX3Formatter()
        existing = {"type": "software_Package", "name": "test"}
        new = {
            "type": "software_Package",
            "name": "test",
            "software_packageVersion": "1.0.0",
            "summary": "Test package",
        }
        formatter._merge_element_metadata(existing, new)
        assert existing["software_packageVersion"] == "1.0.0"
        assert existing["summary"] == "Test package"

    def test_merge_appends_comments(self) -> None:
        formatter = SPDX3Formatter()
        existing = {"type": "software_Package", "name": "test", "comment": "First comment"}
        new = {"type": "software_Package", "name": "test", "comment": "Second comment"}
        formatter._merge_element_metadata(existing, new)
        assert "First comment" in existing["comment"]
        assert "Second comment" in existing["comment"]

    def test_merge_skips_duplicate_comments(self) -> None:
        formatter = SPDX3Formatter()
        existing = {"type": "software_Package", "name": "test", "comment": "Same comment"}
        new = {"type": "software_Package", "name": "test", "comment": "Same comment"}
        formatter._merge_element_metadata(existing, new)
        assert existing["comment"].count("Same comment") == 1

    def test_merge_hyperparameters(self) -> None:
        formatter = SPDX3Formatter()
        existing = {"type": "ai_AIPackage", "name": "model"}
        new = {
            "type": "ai_AIPackage",
            "name": "model",
            "ai_hyperparameter": [{"name": "param", "value": "123"}],
        }
        formatter._merge_element_metadata(existing, new)
        assert existing["ai_hyperparameter"] == [{"name": "param", "value": "123"}]


class TestSPDX3FormatWithGraph:
    """Tests for format with component graph."""

    def test_format_with_graph_adds_file_elements(self) -> None:
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

        formatter = SPDX3Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should have file element
        file_elements = [e for e in data["@graph"] if e.get("type") == "software_File"]
        assert len(file_elements) == 1
        assert file_elements[0]["name"] == "main.py"

    def test_format_with_graph_adds_relationships(self) -> None:
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

        formatter = SPDX3Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should have relationship elements
        relationships = [e for e in data["@graph"] if e.get("type") == "Relationship"]
        assert len(relationships) >= 1

        rel_types = [r["relationshipType"] for r in relationships]
        assert "CONTAINS" in rel_types or "DEPENDS_ON" in rel_types

    def test_format_skips_unsupported_relationship_types(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        graph.add_edge("main.py", "openai", "calls")  # Unsupported

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

        formatter = SPDX3Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should not have "calls" relationship (not valid in SPDX 3.0)
        relationships = [e for e in data["@graph"] if e.get("type") == "Relationship"]
        for rel in relationships:
            assert rel["relationshipType"] != "CALLS"


class TestSPDX3Deduplication:
    """Tests for element deduplication."""

    def test_format_deduplicates_by_name_and_version(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai", version="1.0.0"),
            ),
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="other.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(
                    sdk="openai",
                    import_statement="from openai import Client",
                    version="1.0.0",
                ),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=2,
            duration_ms=10,
        )

        formatter = SPDX3Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        # Should only have one openai package
        openai_packages = [
            e
            for e in data["@graph"]
            if e.get("type") == "software_Package" and e.get("name") == "openai"
        ]
        assert len(openai_packages) == 1

    def test_format_keeps_different_versions_separate(self) -> None:
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(sdk="openai", import_statement="import openai", version="1.0.0"),
            ),
            Finding(
                type=FindingType.MANIFEST_DEP,
                file_path="requirements.txt",
                line=1,
                confidence=1.0,
                manifest_dep=ManifestDep(
                    name="openai",
                    version="2.0.0",
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

        formatter = SPDX3Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        # Should have two openai packages (different versions)
        openai_packages = [
            e
            for e in data["@graph"]
            if e.get("type") == "software_Package" and e.get("name") == "openai"
        ]
        assert len(openai_packages) == 2


class TestSPDX3ToolAgent:
    """Tests for tool agent creation."""

    def test_creates_tool_agent(self) -> None:
        formatter = SPDX3Formatter()
        result = ScanResult(
            root_path="/test",
            findings=[],
            files_scanned=0,
            duration_ms=0,
        )
        output = formatter.format(result)
        data = json.loads(output)

        # Should have tool agent
        tool_agents = [e for e in data["@graph"] if e.get("type") == "agent_Tool"]
        assert len(tool_agents) == 1
        assert "ai-finder" in tool_agents[0]["name"]

    def test_document_references_tool_agent(self) -> None:
        formatter = SPDX3Formatter()
        result = ScanResult(
            root_path="/test",
            findings=[],
            files_scanned=0,
            duration_ms=0,
        )
        output = formatter.format(result)
        data = json.loads(output)

        doc = next(e for e in data["@graph"] if e.get("type") == "SpdxDocument")
        tool_agent = next(e for e in data["@graph"] if e.get("type") == "agent_Tool")

        # Document createdBy should reference tool agent
        assert tool_agent["spdxId"] in doc["creationInfo"]["createdBy"]
