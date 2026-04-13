"""Tests for SPDX 3.0 output formatter."""

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
from scanoss_ai_scanner.output.spdx3 import SPDX3Formatter


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
