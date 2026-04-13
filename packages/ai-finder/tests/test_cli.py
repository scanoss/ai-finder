"""Tests for the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_cli import __version__
from ai_finder_cli.main import main
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project with AI dependencies."""
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "requirements.txt").write_text("openai>=1.0.0\n")
    return tmp_path


class TestCLI:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "AI Finder" in result.output 

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_scan_command_exists(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "scan" in result.output.lower()

    def test_scan_directory(self, runner: CliRunner, temp_project: Path) -> None:
        result = runner.invoke(main, ["scan", str(temp_project)])
        assert result.exit_code == 0

    def test_scan_with_output_format(self, runner: CliRunner, temp_project: Path) -> None:
        result = runner.invoke(main, ["scan", str(temp_project), "--format", "json"])
        assert result.exit_code == 0

    def test_scan_with_cyclonedx_format(self, runner: CliRunner, temp_project: Path) -> None:
        result = runner.invoke(main, ["scan", str(temp_project), "--format", "cyclonedx"])
        assert result.exit_code == 0
        assert "CycloneDX" in result.output

    def test_scan_nonexistent_path(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["scan", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_scan_output_to_file(
        self, runner: CliRunner, temp_project: Path, tmp_path: Path
    ) -> None:
        output_file = tmp_path / "output.json"
        result = runner.invoke(
            main,
            ["scan", str(temp_project), "--output", str(output_file)],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    def test_scan_quiet_mode(self, runner: CliRunner, temp_project: Path) -> None:
        result = runner.invoke(main, ["scan", str(temp_project), "--quiet"])
        assert result.exit_code == 0
