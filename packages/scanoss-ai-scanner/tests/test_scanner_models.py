"""Tests for scanner data models."""

from scanoss_ai_scanner.models import (
    AIComponent,
    Finding,
    FindingType,
    ManifestDep,
    ModelInfo,
    ScanResult,
    SDKUsage,
)


class TestFindingType:
    def test_enum_values(self) -> None:
        assert FindingType.SDK_USAGE.value == "sdk_usage"
        assert FindingType.MANIFEST_DEP.value == "manifest_dep"
        assert FindingType.MODEL_FILE.value == "model_file"
        assert FindingType.MCP_SERVER.value == "mcp_server"
        assert FindingType.AI_COMPONENT.value == "ai_component"


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
