"""Tests for kb commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_finder_cli.commands.kb import kb
from click.testing import CliRunner


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
        monkeypatch.setenv("AI_FINDER_KB_PATH", str(tmp_path / "default.db"))

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


class TestKbCheckUpdates:
    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_updates_shows_status(self, mock_session_class, tmp_path: Path) -> None:
        """Test that check-updates shows version info."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 1}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        runner = CliRunner()
        db_path = tmp_path / "test.db"

        # Initialize first
        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        # Check updates
        result = runner.invoke(kb, ["check-updates", "--kb-path", str(db_path)])

        assert result.exit_code == 0
        assert "local version" in result.output.lower()
        assert "remote version" in result.output.lower()

    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_updates_json_format(self, mock_session_class, tmp_path: Path) -> None:
        """Test check-updates with JSON output."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 2}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(
            kb, ["check-updates", "--kb-path", str(db_path), "--format", "json"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "local_version" in data
        assert "remote_version" in data
        assert "update_available" in data


class TestKbUpdate:
    @patch("ai_finder_kb.sync.requests.Session")
    def test_update_no_update_available(self, mock_session_class, tmp_path: Path) -> None:
        """Test update when no update is available."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 0}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(kb, ["update", "--kb-path", str(db_path)])

        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    @patch("ai_finder_kb.sync.requests.Session")
    def test_update_with_force(self, mock_session_class, tmp_path: Path) -> None:
        """Test update with --force flag."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 1}
        version_response.raise_for_status = MagicMock()

        empty_response = MagicMock()
        empty_response.json.return_value = []
        empty_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            return empty_response

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(kb, ["update", "--kb-path", str(db_path), "--force"])

        assert result.exit_code == 0
        assert "sync complete" in result.output.lower()

    @patch("ai_finder_kb.sync.requests.Session")
    def test_update_json_format(self, mock_session_class, tmp_path: Path) -> None:
        """Test update with JSON output."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 1}
        version_response.raise_for_status = MagicMock()

        empty_response = MagicMock()
        empty_response.json.return_value = []
        empty_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            return empty_response

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        runner = CliRunner()
        db_path = tmp_path / "test.db"

        runner.invoke(kb, ["init", "--kb-path", str(db_path)])

        result = runner.invoke(
            kb, ["update", "--kb-path", str(db_path), "--force", "--format", "json"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "success" in data
        assert "new_version" in data
