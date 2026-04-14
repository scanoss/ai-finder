"""Tests for file discovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.discovery import FileDiscovery


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project structure."""
    # Source files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import openai")
    (tmp_path / "src" / "utils.py").write_text("# utils")
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "src" / "nested" / "deep.py").write_text("# deep")

    # Manifest files
    (tmp_path / "requirements.txt").write_text("openai>=1.0.0")
    (tmp_path / "package.json").write_text('{"dependencies": {}}')

    # Model files
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "llama.gguf").write_bytes(b"\x00" * 100)

    # Config files
    (tmp_path / "claude_desktop_config.json").write_text("{}")

    # Files to ignore
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("# git config")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("// js")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00")

    return tmp_path


class TestFileDiscovery:
    def test_discover_source_files(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        source_files = list(discovery.source_files())

        # Should find .py files
        paths = [f.name for f in source_files]
        assert "main.py" in paths
        assert "utils.py" in paths
        assert "deep.py" in paths

    def test_discover_manifest_files(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        manifest_files = list(discovery.manifest_files())

        names = [f.name for f in manifest_files]
        assert "requirements.txt" in names
        assert "package.json" in names

    def test_discover_model_files(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        model_files = list(discovery.model_files())

        names = [f.name for f in model_files]
        assert "llama.gguf" in names

    def test_discover_config_files(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        config_files = list(discovery.config_files())

        names = [f.name for f in config_files]
        assert "claude_desktop_config.json" in names

    def test_ignore_git_directory(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        all_files = list(discovery.all_files())

        paths = [str(f) for f in all_files]
        assert not any(".git" in p for p in paths)

    def test_ignore_node_modules(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        all_files = list(discovery.all_files())

        paths = [str(f) for f in all_files]
        assert not any("node_modules" in p for p in paths)

    def test_ignore_pycache(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        all_files = list(discovery.all_files())

        paths = [str(f) for f in all_files]
        assert not any("__pycache__" in p for p in paths)

    def test_all_files_combined(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        all_files = list(discovery.all_files())

        # Should include source, manifest, model, and config files
        names = [f.name for f in all_files]
        assert "main.py" in names
        assert "requirements.txt" in names
        assert "llama.gguf" in names
        assert "claude_desktop_config.json" in names

    def test_file_count(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        count = discovery.count_files()

        # 3 py + 2 manifests + 1 model + 1 config = 7
        assert count == 7

    def test_relative_paths(self, temp_project: Path) -> None:
        discovery = FileDiscovery(temp_project)
        source_files = list(discovery.source_files())

        # Paths should be relative to root
        main = next(f for f in source_files if f.name == "main.py")
        assert str(main) == "src/main.py"
