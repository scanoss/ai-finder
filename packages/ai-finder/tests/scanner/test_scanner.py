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

    def test_scan_wires_agent_and_tool_detectors(self, tmp_path: Path) -> None:
        # Regression: the semantic detectors (agent/tool/RAG/dataset) must run
        # during a scan, not just the per-language SDK detectors. A Strands
        # agent app should surface agent + tool findings, not only sdk_usage.
        (tmp_path / "orchestrator.py").write_text(
            "from strands import Agent, tool\n\n@tool\ndef search(q: str) -> str:\n    return q\n"
        )
        result = Scanner().scan(tmp_path)
        types = {f.type for f in result.findings}
        assert FindingType.AGENT in types
        assert FindingType.TOOL in types
        agent = next(f for f in result.findings if f.type == FindingType.AGENT)
        assert agent.agent_info and agent.agent_info.framework == "strands"

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


class TestModelFormatsReachedByProjectScan:
    """A parser that discovery never hands a file to is dead in a project scan."""

    def test_every_parser_extension_is_discovered(self) -> None:
        from ai_finder_scanner.discovery import MODEL_EXTENSIONS

        parser_exts = {ext for p in Scanner()._model_parsers for ext in p.extensions}
        # .mlpackage is a directory bundle; discovery walks files only.
        assert parser_exts - {".mlpackage"} <= MODEL_EXTENSIONS

    def test_scan_finds_jax_mxnet_paddle_and_pickle(self, tmp_path: Path) -> None:
        from test_parsers import FLAX_CHECKPOINT, MXNET_PARAMS_HEADER

        pickle_bytes = b"\x80\x04" + b"\x00" * 2000
        (tmp_path / "flax_model.msgpack").write_bytes(FLAX_CHECKPOINT)
        (tmp_path / "model.params").write_bytes(MXNET_PARAMS_HEADER + b"\x00" * 200)
        (tmp_path / "model.pdparams").write_bytes(pickle_bytes)
        (tmp_path / "inference.pdmodel").write_bytes(b"\x0a\x04blk0" + b"\x00" * 50)
        (tmp_path / "optim.pdopt").write_bytes(pickle_bytes)
        (tmp_path / "weights.pickle").write_bytes(pickle_bytes)

        result = Scanner(hash_model_files=False).scan(tmp_path)

        found = {
            f.file_path: f.model_info.format
            for f in result.findings
            if f.type == FindingType.MODEL_FILE and f.model_info
        }
        assert found == {
            "flax_model.msgpack": "jax",
            "model.params": "mxnet",
            "model.pdparams": "paddle",
            "inference.pdmodel": "paddle",
            "optim.pdopt": "paddle",
            "weights.pickle": "pickle",
        }

    def test_non_model_files_with_shared_extensions_are_not_reported(self, tmp_path: Path) -> None:
        from test_parsers import PLAIN_MSGPACK

        (tmp_path / "data.msgpack").write_bytes(PLAIN_MSGPACK)
        (tmp_path / "train.params").write_bytes(b"lr=0.01\nepochs=10\n" * 100)

        result = Scanner(hash_model_files=False).scan(tmp_path)

        assert [f for f in result.findings if f.type == FindingType.MODEL_FILE] == []
        assert result.files_scanned >= 2  # both were reached, then rejected
