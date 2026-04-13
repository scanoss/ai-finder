"""Tests for kb commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from ai_finder_cli.commands.kb import kb


class TestKbInit:
    def test_kb_init_creates_database(self, tmp_path: Path) -> None:
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        result = runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        assert result.exit_code == 0
        assert "initialized" in result.output.lower()
        assert db_path.exists()

    def test_kb_init_default_path(self, tmp_path: Path, monkeypatch) -> None:
        runner = CliRunner()
        # Set env var to use temp path
        monkeypatch.setenv("SCANOSS_KB_PATH", str(tmp_path / "default.db"))

        result = runner.invoke(kb, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / "default.db").exists()


class TestKbStatus:
    def test_kb_status_shows_info(self, tmp_path: Path) -> None:
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        # Initialize first
        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        # Check status
        result = runner.invoke(kb, ["status", "--kb-path", str(db_path)])

        assert result.exit_code == 0
        assert "version" in result.output.lower() or "schema" in result.output.lower()

    def test_kb_status_json_format(self, tmp_path: Path) -> None:
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(kb, ["status", "--kb-path", str(db_path), "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "schema_version" in data

    def test_kb_status_auto_init(self, tmp_path: Path) -> None:
        """Test that kb status auto-initializes from seed if available."""
        runner = CliRunner()
        db_path = tmp_path / "nonexistent.db"

        result = runner.invoke(kb, ["status", "--kb-path", str(db_path)])

        # If seed is available, auto-init succeeds; otherwise fails
        if result.exit_code == 0:
            # Auto-initialized successfully
            assert db_path.exists()
            assert "auto-initialized" in result.output.lower() or "version" in result.output.lower()
        else:
            # No seed available
            assert result.exit_code == 2
            assert "not found" in result.output.lower()


class TestKbLookup:
    def test_kb_lookup_not_found(self, tmp_path: Path) -> None:
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        # Initialize first
        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(kb, ["lookup", "pkg:pypi/nonexistent", "--kb-path", str(db_path)])

        assert result.exit_code == 1
        assert "no results" in result.output.lower()

    def test_kb_lookup_invalid_purl(self, tmp_path: Path) -> None:
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(kb, ["lookup", "invalid-purl", "--kb-path", str(db_path)])

        assert result.exit_code == 2
        assert "invalid" in result.output.lower()

    def test_kb_lookup_auto_init(self, tmp_path: Path) -> None:
        """Test that kb lookup auto-initializes from seed if available."""
        runner = CliRunner()
        db_path = tmp_path / "none.db"

        result = runner.invoke(kb, ["lookup", "pkg:pypi/openai", "--kb-path", str(db_path)])

        # If seed is available, auto-init succeeds; otherwise fails
        if result.exit_code == 1:
            # Auto-initialized but no results found (normal behavior)
            assert db_path.exists()
            assert "no results" in result.output.lower()
        elif result.exit_code == 0:
            # Auto-initialized and found results
            assert db_path.exists()
        else:
            # No seed available
            assert result.exit_code == 2
            assert "not found" in result.output.lower()
