"""Pytest fixtures for scanner tests."""

import tempfile
from pathlib import Path

import pytest
from ai_finder_scanner.analyzers import is_tree_sitter_available

# Skip test_analyzers.py if tree-sitter is not available (Python < 3.10)
collect_ignore = []
if not is_tree_sitter_available():
    collect_ignore.append("test_analyzers.py")


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
