"""Tests for the main scanner orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.models import FindingType
from ai_finder_scanner.scanner import Scanner


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project with AI dependencies."""
    # Python file with AI import
    (tmp_path / "main.py").write_text("import openai\n")

    # requirements.txt with AI deps
    (tmp_path / "requirements.txt").write_text("openai>=1.0.0\nanthropicic\n")

    # JavaScript file
    (tmp_path / "app.js").write_text('import OpenAI from "openai";\n')

    # package.json
    (tmp_path / "package.json").write_text('{"dependencies": {"langchain": "^0.1.0"}}')

    # Non-AI file
    (tmp_path / "utils.py").write_text("import os\n")

    return tmp_path


class TestScanner:
    def test_scan_returns_result(self, temp_project: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(temp_project)

        assert result.root_path == str(temp_project)
        assert result.files_scanned > 0
        assert result.duration_ms >= 0

    def test_scan_finds_sdk_usage(self, temp_project: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(temp_project)

        sdk_findings = [f for f in result.findings if f.type == FindingType.SDK_USAGE]
        assert len(sdk_findings) >= 1

        sdks = {f.sdk_usage.sdk for f in sdk_findings if f.sdk_usage}
        assert "openai" in sdks

    def test_scan_finds_manifest_deps(self, temp_project: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(temp_project)

        manifest_findings = [f for f in result.findings if f.type == FindingType.MANIFEST_DEP]
        assert len(manifest_findings) >= 1

        deps = {f.manifest_dep.name for f in manifest_findings if f.manifest_dep}
        assert "openai" in deps or "langchain" in deps

    def test_scan_multiple_languages(self, temp_project: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(temp_project)

        # Should find both Python and JS SDK usage
        files_with_findings = {f.file_path for f in result.findings}
        assert any(".py" in f for f in files_with_findings)
        assert any(".js" in f for f in files_with_findings)

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(tmp_path)

        assert result.files_scanned == 0
        assert len(result.findings) == 0

    def test_scan_nonexistent_path_raises(self) -> None:
        scanner = Scanner()
        with pytest.raises(FileNotFoundError):
            scanner.scan(Path("/nonexistent/path"))

    def test_files_scanned_count(self, temp_project: Path) -> None:
        scanner = Scanner()
        result = scanner.scan(temp_project)

        # Should count source files, manifests, etc.
        assert result.files_scanned >= 4  # main.py, app.js, requirements.txt, package.json

    def test_scan_with_kb_integration(
        self, temp_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scanner should work with or without KB."""
        scanner = Scanner()
        result = scanner.scan(temp_project)

        # Should still find SDK usage even without KB enrichment
        assert any(f.type == FindingType.SDK_USAGE for f in result.findings)
