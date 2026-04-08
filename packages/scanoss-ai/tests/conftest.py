"""Pytest fixtures for CLI tests."""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
