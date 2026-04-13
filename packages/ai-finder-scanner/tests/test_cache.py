"""Tests for scanner caching."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from ai_finder_scanner.cache import ScanCache


class TestScanCache:
    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        cache = tmp_path / ".scanoss-cache"
        cache.mkdir()
        return cache

    @pytest.fixture
    def cache(self, cache_dir: Path) -> ScanCache:
        return ScanCache(cache_dir)

    def test_cache_file_hash(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # First call computes hash
        hash1 = cache.get_file_hash(test_file)
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256 hex length

        # Same file returns same hash
        hash2 = cache.get_file_hash(test_file)
        assert hash1 == hash2

    def test_cache_detects_file_changes(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        hash1 = cache.get_file_hash(test_file)

        # Modify file
        time.sleep(0.01)  # Ensure mtime changes
        test_file.write_text("print('world')")

        hash2 = cache.get_file_hash(test_file)
        assert hash1 != hash2

    def test_is_file_changed_when_not_cached(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # File not in cache yet
        assert cache.is_file_changed(test_file) is True

    def test_is_file_changed_when_unchanged(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Store in cache
        cache.mark_file_scanned(test_file)

        # File unchanged
        assert cache.is_file_changed(test_file) is False

    def test_is_file_changed_when_modified(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Store in cache
        cache.mark_file_scanned(test_file)

        # Modify file
        time.sleep(0.01)
        test_file.write_text("print('modified')")

        # File changed
        assert cache.is_file_changed(test_file) is True

    def test_store_and_retrieve_finding(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("import openai")

        finding_data = {
            "type": "sdk_usage",
            "file_path": str(test_file),
            "sdk": "openai",
        }

        # Store finding
        cache.store_finding(test_file, finding_data)

        # Retrieve finding
        cached = cache.get_cached_finding(test_file)
        assert cached is not None
        assert cached["sdk"] == "openai"

    def test_cached_finding_invalidated_on_change(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("import openai")

        finding_data = {"type": "sdk_usage", "sdk": "openai"}
        cache.store_finding(test_file, finding_data)

        # Modify file
        time.sleep(0.01)
        test_file.write_text("import anthropic")

        # Cached finding should be invalidated
        cached = cache.get_cached_finding(test_file)
        assert cached is None

    def test_clear_cache(self, cache: ScanCache, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        cache.mark_file_scanned(test_file)
        assert cache.is_file_changed(test_file) is False

        cache.clear()

        # After clear, file should be considered changed
        assert cache.is_file_changed(test_file) is True

    def test_save_and_load_cache(self, cache: ScanCache, cache_dir: Path, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        cache.mark_file_scanned(test_file)
        cache.save()

        # Create new cache instance and load
        cache2 = ScanCache(cache_dir)
        cache2.load()

        # File should still be marked as unchanged
        assert cache2.is_file_changed(test_file) is False

    def test_nonexistent_file_returns_none(self, cache: ScanCache, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent.py"

        assert cache.get_file_hash(nonexistent) is None
        assert cache.is_file_changed(nonexistent) is True
        assert cache.get_cached_finding(nonexistent) is None

    def test_cache_stats(self, cache: ScanCache, tmp_path: Path) -> None:
        # Create some files and cache them
        for i in range(3):
            f = tmp_path / f"file{i}.py"
            f.write_text(f"code {i}")
            cache.mark_file_scanned(f)

        # Save to get cache_size on disk
        cache.save()

        stats = cache.stats()
        assert stats["cached_files"] == 3
        assert stats["cache_size"] > 0
