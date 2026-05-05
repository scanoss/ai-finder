"""Tests for telemetry opt-out paths.

These guard the four documented disable mechanisms — without them, a future
refactor could silently re-enable event emission for users who opted out:

  1. --no-telemetry CLI flag (calls telemetry.disable())
  2. AI_FINDER_TELEMETRY=0 environment variable
  3. DO_NOT_TRACK=1 environment variable
  4. ~/.ai-finder/config.json with {"telemetry": false}

Plus the placeholder-key short-circuit that keeps source installations quiet.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from ai_finder_cli import telemetry


@pytest.fixture(autouse=True)
def reset_telemetry_state(monkeypatch, tmp_path):
    """Reset module-level state and isolate the config dir for each test."""
    monkeypatch.setattr(telemetry, "_client", None)
    monkeypatch.setattr(telemetry, "_disabled_by_flag", False)
    monkeypatch.delenv("AI_FINDER_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr(telemetry, "_get_config_path", lambda: tmp_path)
    yield


def test_disabled_by_env_ai_finder_telemetry(monkeypatch):
    monkeypatch.setenv("AI_FINDER_TELEMETRY", "0")
    assert telemetry._is_disabled() is True
    assert telemetry._get_client() is None


def test_disabled_by_env_do_not_track(monkeypatch):
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    assert telemetry._is_disabled() is True
    assert telemetry._get_client() is None


def test_disabled_by_config_file(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"telemetry": False}))
    assert telemetry._is_disabled() is True
    assert telemetry._get_client() is None


def test_enabled_by_config_file_does_not_disable(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"telemetry": True}))
    assert telemetry._is_disabled() is False


def test_malformed_config_fails_closed(tmp_path):
    """Privacy-first: an unreadable config file is treated as opt-out."""
    (tmp_path / "config.json").write_text("not valid json {{{")
    assert telemetry._check_config_opt_out() is True


def test_disable_flag_blocks_client():
    telemetry.disable()
    assert telemetry._is_disabled() is True
    assert telemetry._get_client() is None


def test_disable_shuts_down_existing_client(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(telemetry, "_client", fake_client)
    telemetry.disable()
    fake_client.shutdown.assert_called_once()
    assert telemetry._client is None


def test_placeholder_constant_value():
    """The placeholder constant must equal the literal sed substitutes against.

    Constructed dynamically so the build-time sed doesn't clobber it; this test
    asserts that the dynamic construction still produces the right string.
    """
    assert telemetry._INGEST_KEY_PLACEHOLDER == "__TELEMETRY_INGEST_KEY__"


def test_placeholder_key_disables_client(monkeypatch):
    """Source installs ship with the placeholder; client must not initialize."""
    monkeypatch.setattr(telemetry, "_INGEST_KEY", telemetry._INGEST_KEY_PLACEHOLDER)
    assert telemetry._get_client() is None


def test_empty_key_disables_client(monkeypatch):
    monkeypatch.setattr(telemetry, "_INGEST_KEY", "")
    assert telemetry._get_client() is None
