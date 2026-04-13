"""Tests for SBOM output formatters."""

from __future__ import annotations

import json

import pytest
from scanoss_ai_scanner.models import (
    Finding,
    FindingType,
    ManifestDep,
    ScanResult,
    SDKUsage,
)
from scanoss_ai_scanner.output.cyclonedx import CycloneDXFormatter
from scanoss_ai_scanner.output.json_output import JSONFormatter
from scanoss_ai_scanner.output.spdx import SPDX23Formatter


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
        Finding(
            type=FindingType.MANIFEST_DEP,
            file_path="requirements.txt",
            line=1,
            confidence=1.0,
            manifest_dep=ManifestDep(
                name="langchain",
                version=">=0.1.0",
                manifest_file="requirements.txt",
            ),
        ),
    ]
    return ScanResult(
        root_path="/test/project",
        findings=findings,
        files_scanned=10,
        duration_ms=100,
    )


class TestJSONFormatter:
    def test_format_returns_valid_json(self, sample_result: ScanResult) -> None:
        formatter = JSONFormatter()
        output = formatter.format(sample_result)

        # Should be valid JSON
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_includes_metadata(self, sample_result: ScanResult) -> None:
        formatter = JSONFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        assert data["root_path"] == "/test/project"
        assert data["files_scanned"] == 10
        assert data["duration_ms"] == 100

    def test_format_includes_findings(self, sample_result: ScanResult) -> None:
        formatter = JSONFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        assert len(data["findings"]) == 2
        assert data["findings"][0]["type"] == "sdk_usage"
        assert data["findings"][0]["file_path"] == "main.py"

    def test_format_empty_result(self) -> None:
        result = ScanResult(
            root_path="/empty",
            findings=[],
            files_scanned=0,
            duration_ms=0,
        )
        formatter = JSONFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        assert data["findings"] == []

    def test_format_indented(self, sample_result: ScanResult) -> None:
        formatter = JSONFormatter(indent=2)
        output = formatter.format(sample_result)

        # Should have newlines for indentation
        assert "\n" in output


class TestCycloneDXFormatter:
    def test_format_returns_valid_json(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)

        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_has_cyclonedx_structure(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # CycloneDX required fields
        assert "bomFormat" in data
        assert data["bomFormat"] == "CycloneDX"
        assert "specVersion" in data
        assert "components" in data

    def test_format_includes_components(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # Should have components from findings
        assert len(data["components"]) >= 1

        # Check component structure
        component = data["components"][0]
        assert "type" in component
        assert "name" in component

    def test_format_sdk_as_library(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # Find openai component
        openai_comp = next((c for c in data["components"] if c["name"] == "openai"), None)
        assert openai_comp is not None
        assert openai_comp["type"] == "library"

    def test_format_includes_purl(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # Check that at least one component has a purl
        components_with_purl = [c for c in data["components"] if "purl" in c]
        assert len(components_with_purl) >= 1

    def test_format_spec_version_1_6(self, sample_result: ScanResult) -> None:
        formatter = CycloneDXFormatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        assert data["specVersion"] == "1.6"

    def test_format_empty_result(self) -> None:
        result = ScanResult(
            root_path="/empty",
            findings=[],
            files_scanned=0,
            duration_ms=0,
        )
        formatter = CycloneDXFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        assert data["components"] == []


class TestSPDX23Formatter:
    def test_format_returns_valid_json(self, sample_result: ScanResult) -> None:
        formatter = SPDX23Formatter()
        output = formatter.format(sample_result)

        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_has_spdx_structure(self, sample_result: ScanResult) -> None:
        formatter = SPDX23Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # SPDX required fields
        assert "spdxVersion" in data
        assert data["spdxVersion"] == "SPDX-2.3"
        assert "SPDXID" in data
        assert "packages" in data
        assert "relationships" in data

    def test_format_includes_packages(self, sample_result: ScanResult) -> None:
        formatter = SPDX23Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # Should have packages from findings
        assert len(data["packages"]) >= 1

        # Check package structure
        package = data["packages"][0]
        assert "SPDXID" in package
        assert "name" in package

    def test_format_includes_purl_in_external_refs(self, sample_result: ScanResult) -> None:
        formatter = SPDX23Formatter()
        output = formatter.format(sample_result)
        data = json.loads(output)

        # Check that packages have external refs with PURLs
        packages_with_purl = [
            p
            for p in data["packages"]
            if "externalRefs" in p
            and any(r.get("referenceType") == "purl" for r in p["externalRefs"])
        ]
        assert len(packages_with_purl) >= 1

    def test_format_empty_result(self) -> None:
        result = ScanResult(
            root_path="/empty",
            findings=[],
            files_scanned=0,
            duration_ms=0,
        )
        formatter = SPDX23Formatter()
        output = formatter.format(result)
        data = json.loads(output)

        assert data["packages"] == []
        assert data["relationships"] == []
