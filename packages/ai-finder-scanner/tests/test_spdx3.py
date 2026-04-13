"""Tests for SPDX 3.0 output formatter."""

from __future__ import annotations

import json

import pytest
from ai_finder_scanner.models import (
    Finding,
    FindingType,
    ManifestDep,
    ScanResult,
    SDKUsage,
)
from ai_finder_scanner.output.spdx3 import SPDX3Formatter


@pytest.fixture
def sample_result() -> ScanResult:
    """Create a sample scan result for testing."""
    findings = [
        Finding(
            type=FindingType.SDK_USAGE,
            file_path="main.py",
            line=1,
            confidence=1.0,
            sdk_usage=SDKUsage(
                sdk="openai",
                import_statement="import openai",
                version="1.0.0",
            ),
        ),
    ]
    return ScanResult(
        root_path="/test/project",
        findings=findings,
        files_scanned=10,
        duration_ms=100,
    )


@pytest.fixture
def model_file_result() -> ScanResult:
    """Create a scan result with a model file finding."""
    from ai_finder_scanner.models import ModelInfo

    findings = [
        Finding(
            type=FindingType.MODEL_FILE,
            file_path="models/llama-3-8b.gguf",
            confidence=1.0,
            model_info=ModelInfo(
                format="gguf",
                architecture="llama",
                parameter_count=8000000000,
                quantization="Q4_K_M",
            ),
        ),
    ]
    return ScanResult(
        root_path="/test/project",
        findings=findings,
        files_scanned=5,
        duration_ms=50,
    )


class TestSPDX3Formatter:
    def test_format_returns_valid_json(self, sample_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_has_jsonld_context(self, sample_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)
        assert "@context" in data
        assert "spdx" in data["@context"].lower()

    def test_format_has_graph_structure(self, sample_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)
        assert "@graph" in data
        assert isinstance(data["@graph"], list)
        assert len(data["@graph"]) >= 1

    def test_format_has_spdx_document(self, sample_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)
        doc = next(
            (e for e in data["@graph"] if e.get("type") == "SpdxDocument"),
            None,
        )
        assert doc is not None
        assert "spdxId" in doc
        assert "creationInfo" in doc

    def test_format_model_as_ai_package(self, model_file_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(model_file_result)
        data = json.loads(output)

        # Find AIPackage in graph
        ai_pkg = next(
            (e for e in data["@graph"] if e.get("type") == "ai_AIPackage"),
            None,
        )
        assert ai_pkg is not None
        # Model name now uses full path to avoid collisions between
        # models with same filename in different directories
        assert ai_pkg["name"] == "models/llama-3-8b.gguf"
        assert ai_pkg["ai_typeOfModel"] == "llama"
        assert ai_pkg["ai_domain"] == "text-generation"
        assert ai_pkg["ai_autonomyType"] == "assistive"

    def test_format_model_has_hyperparameters(self, model_file_result: ScanResult) -> None:
        formatter = SPDX3Formatter()
        output = formatter.format(model_file_result)
        data = json.loads(output)

        ai_pkg = next(
            (e for e in data["@graph"] if e.get("type") == "ai_AIPackage"),
            None,
        )
        assert ai_pkg is not None
        assert "ai_hyperparameter" in ai_pkg

        # Check parameter_count hyperparameter
        param_count = next(
            (h for h in ai_pkg["ai_hyperparameter"] if h["name"] == "parameter_count"),
            None,
        )
        assert param_count is not None
        assert param_count["value"] == "8000000000"

    def test_normalize_version(self) -> None:
        formatter = SPDX3Formatter()
        # v prefix
        assert formatter._normalize_version("v1.0.0") == "1.0.0"
        assert formatter._normalize_version("V2.3.4") == "2.3.4"
        # Semver range prefixes
        assert formatter._normalize_version("^1.2.3") == "1.2.3"
        assert formatter._normalize_version("~1.2.3") == "1.2.3"
        # Comparison operators
        assert formatter._normalize_version(">=2.0.0") == "2.0.0"
        assert formatter._normalize_version("==1.0.0") == "1.0.0"
        assert formatter._normalize_version(">3.0") == "3.0"
        # Whitespace
        assert formatter._normalize_version("  1.0.0  ") == "1.0.0"
        # No change needed
        assert formatter._normalize_version("1.2.3") == "1.2.3"

    def test_versioned_spdx_id_includes_normalized_version(self) -> None:
        """Test that spdxId includes normalized version for deduplication."""
        findings = [
            Finding(
                type=FindingType.SDK_USAGE,
                file_path="main.py",
                line=1,
                confidence=1.0,
                sdk_usage=SDKUsage(
                    sdk="openai",
                    import_statement="import openai",
                    version="^1.0.0",  # Has semver prefix
                ),
            ),
        ]
        result = ScanResult(
            root_path="/test/project",
            findings=findings,
            files_scanned=1,
            duration_ms=10,
        )
        formatter = SPDX3Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        pkg = next(
            (e for e in data["@graph"] if e.get("type") == "software_Package"),
            None,
        )
        assert pkg is not None
        # Version should be normalized in spdxId (^1.0.0 → 1.0.0)
        assert "1.0.0" in pkg["spdxId"]
        assert "^" not in pkg["spdxId"]
