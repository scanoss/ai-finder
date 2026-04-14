"""Extended tests for SPDX 2.3 output formatter to increase coverage."""

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
from ai_finder_scanner.output.spdx import SPDX23Formatter


class TestSPDX23PurlInference:
    """Tests for PURL type inference methods."""

    def test_infer_purl_type_from_sdk_golang_github(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("github.com/sashabaranov/go-openai") == "golang"

    def test_infer_purl_type_from_sdk_golang_org(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("golang.org/x/oauth2") == "golang"

    def test_infer_purl_type_from_sdk_npm_scoped(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("@anthropic-ai/sdk") == "npm"

    def test_infer_purl_type_from_sdk_cargo_async(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("async-openai") == "cargo"

    def test_infer_purl_type_from_sdk_cargo_rs_suffix(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("anthropic-rs") == "cargo"

    def test_infer_purl_type_from_sdk_default_pypi(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_sdk("openai") == "pypi"

    def test_infer_purl_type_from_manifest_requirements(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("requirements.txt") == "pypi"
        assert formatter._infer_purl_type_from_manifest("requirements-dev.txt") == "pypi"

    def test_infer_purl_type_from_manifest_package_json(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("package.json") == "npm"
        assert formatter._infer_purl_type_from_manifest("package-lock.json") == "npm"

    def test_infer_purl_type_from_manifest_go_mod(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("go.mod") == "golang"

    def test_infer_purl_type_from_manifest_cargo(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("Cargo.toml") == "cargo"

    def test_infer_purl_type_from_manifest_gemfile(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("Gemfile") == "gem"

    def test_infer_purl_type_from_manifest_csproj(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("MyProject.csproj") == "nuget"

    def test_infer_purl_type_from_manifest_unknown_defaults_pypi(self) -> None:
        formatter = SPDX23Formatter()
        assert formatter._infer_purl_type_from_manifest("unknown.file") == "pypi"


class TestSPDX23BuildPurl:
    """Tests for PURL building."""

    def test_build_purl_npm_scoped(self) -> None:
        formatter = SPDX23Formatter()
        purl = formatter._build_purl("npm", "@anthropic-ai/sdk", "1.0.0")
        assert purl == "pkg:npm/anthropic-ai/sdk@1.0.0"

    def test_build_purl_npm_scoped_no_version(self) -> None:
        formatter = SPDX23Formatter()
        purl = formatter._build_purl("npm", "@openai/sdk")
        assert purl == "pkg:npm/openai/sdk"

    def test_build_purl_npm_malformed_scope(self) -> None:
        formatter = SPDX23Formatter()
        purl = formatter._build_purl("npm", "@malformed")
        assert purl == "pkg:npm/%40malformed"

    def test_build_purl_golang(self) -> None:
        formatter = SPDX23Formatter()
        purl = formatter._build_purl("golang", "github.com/sashabaranov/go-openai", "v1.0.0")
        assert purl == "pkg:golang/github.com/sashabaranov/go-openai@v1.0.0"

    def test_build_purl_pypi(self) -> None:
        formatter = SPDX23Formatter()
        purl = formatter._build_purl("pypi", "openai", "1.0.0")
        assert purl == "pkg:pypi/openai@1.0.0"

    def test_build_purl_strips_version_operators(self) -> None:
        formatter = SPDX23Formatter()
        assert ">=1.0.0" not in formatter._build_purl("pypi", "openai", ">=1.0.0")
        assert "@1.0.0" in formatter._build_purl("pypi", "openai", ">=1.0.0")


class TestSPDX23FindingToPackage:
    """Tests for finding to package conversion."""

    def test_model_file_to_package(self) -> None:
        formatter = SPDX23Formatter()
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
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "llama-3-8b.gguf"
        assert package["primaryPackagePurpose"] == "APPLICATION"
        assert "gguf" in package["comment"]
        assert "llama" in package["comment"]
        assert "Q4_K_M" in package["comment"]
        assert "8,000,000,000" in package["comment"]

    def test_model_file_to_package_minimal(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.MODEL_FILE,
            file_path="model.bin",
            confidence=1.0,
            model_info=ModelInfo(format="unknown"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "model.bin"

    def test_mcp_server_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.MCP_SERVER,
            file_path="server.py",
            confidence=1.0,
            ai_component=AIComponent(component_type="mcp_server", name="my-mcp-server"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "my-mcp-server"
        assert "MCP server" in package["comment"]

    def test_mcp_client_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.MCP_CLIENT,
            file_path="client.py",
            confidence=1.0,
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "mcp-client"
        assert "MCP client" in package["comment"]

    def test_agent_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="agent.py",
            confidence=1.0,
            agent_info=AgentInfo(framework="crewai"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "crewai-agent"

    def test_tool_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.TOOL,
            file_path="tool.py",
            confidence=1.0,
            tool_info=ToolInfo(name="search_tool"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "search_tool"

    def test_embedding_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.EMBEDDING,
            file_path="embed.py",
            confidence=1.0,
            embedding_info=EmbeddingInfo(provider="openai", model="text-embedding-3-small"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "openai-embeddings"

    def test_vector_store_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.VECTOR_STORE,
            file_path="store.py",
            confidence=1.0,
            vector_store_info=VectorStoreInfo(provider="pinecone"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "pinecone"

    def test_prompt_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.PROMPT,
            file_path="prompt.py",
            confidence=1.0,
            prompt_info=PromptInfo(template_type="chat"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "prompt-chat"

    def test_guardrail_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.GUARDRAIL,
            file_path="guard.py",
            confidence=1.0,
            guardrail_info=GuardrailInfo(framework="guardrails-ai"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "guardrails-ai"

    def test_dataset_to_package(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(
                name="squad",
                source="huggingface",
                split="train",
            ),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "squad"
        assert "huggingface" in package["comment"]
        assert "train" in package["comment"]

    def test_dataset_to_package_no_name(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.DATASET,
            file_path="data.py",
            confidence=1.0,
            dataset_info=DatasetInfo(source="huggingface"),
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is not None
        assert package["name"] == "huggingface-dataset"

    def test_unknown_finding_returns_none(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.SDK_USAGE,
            file_path="test.py",
            confidence=1.0,
            # No sdk_usage data
        )
        package = formatter._finding_to_package(finding, 0)
        assert package is None


class TestSPDX23Phase2PackageName:
    """Tests for _get_phase2_package_name."""

    def test_unknown_component_fallback(self) -> None:
        formatter = SPDX23Formatter()
        finding = Finding(
            type=FindingType.AGENT,
            file_path="test.py",
            confidence=1.0,
            # No specific info attached
        )
        name = formatter._get_phase2_package_name(finding)
        assert name == "unknown-component"


class TestSPDX23FormatWithGraph:
    """Tests for format method with component graph."""

    def test_format_with_graph_adds_file_packages(self) -> None:
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

        formatter = SPDX23Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should have both SDK and file packages
        package_names = [p["name"] for p in data["packages"]]
        assert "openai" in package_names
        assert "main.py" in package_names

        # Should have CONTAINS relationship
        rel_types = [r["relationshipType"] for r in data["relationships"]]
        assert "CONTAINS" in rel_types

    def test_format_with_graph_adds_depends_on(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        graph.add_edge("openai", "httpx", "dependsOn")
        graph.add_edge("main.py", "openai", "contains")

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

        formatter = SPDX23Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should have DEPENDS_ON relationship
        depends_on_rels = [
            r for r in data["relationships"] if r["relationshipType"] == "DEPENDS_ON"
        ]
        assert len(depends_on_rels) > 0

    def test_format_skips_function_paths_in_file_packages(self) -> None:
        from ai_finder_scanner.analyzers.graph import ComponentGraph

        graph = ComponentGraph()
        # Function path should be skipped
        graph.add_edge("main.py::my_function", "openai", "contains")
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

        formatter = SPDX23Formatter()
        output = formatter.format(result, graph=graph)
        data = json.loads(output)

        # Should not have function path as package
        package_names = [p["name"] for p in data["packages"]]
        assert "main.py::my_function" not in package_names
        assert "main.py" in package_names


class TestSPDX23Deduplication:
    """Tests for package deduplication."""

    def test_format_deduplicates_by_name(self) -> None:
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
                line=5,
                confidence=1.0,
                sdk_usage=SDKUsage(
                    sdk="openai",
                    import_statement="from openai import ChatCompletion",
                ),
            ),
        ]
        result = ScanResult(
            root_path="/test",
            findings=findings,
            files_scanned=2,
            duration_ms=10,
        )

        formatter = SPDX23Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        # Should only have one openai package
        openai_packages = [p for p in data["packages"] if p["name"] == "openai"]
        assert len(openai_packages) == 1

    def test_format_updates_version_when_found(self) -> None:
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
                    version="1.0.0",
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

        formatter = SPDX23Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        # Should have version from manifest
        openai_pkg = next(p for p in data["packages"] if p["name"] == "openai")
        assert openai_pkg.get("versionInfo") == "1.0.0"
