"""Scanner caching for incremental scanning."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
CACHE_FILE = "scan_cache.json"


class ScanCache:
    """File-based cache for incremental scanning.

    Tracks file hashes and mtimes to skip unchanged files.
    """

    def __init__(self, cache_dir: Path) -> None:
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files.
        """
        self._cache_dir = Path(cache_dir)
        self._cache_file = self._cache_dir / CACHE_FILE
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False

    def load(self) -> None:
        """Load cache from disk."""
        if not self._cache_file.exists():
            return

        try:
            with open(self._cache_file, encoding="utf-8") as f:
                data = json.load(f)

            # Check version compatibility
            if data.get("version") != CACHE_VERSION:
                logger.info("Cache version mismatch, clearing cache")
                self._entries = {}
                return

            self._entries = data.get("entries", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load cache: %s", e)
            self._entries = {}

    def save(self) -> None:
        """Save cache to disk."""
        if not self._dirty:
            return

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": CACHE_VERSION,
            "entries": self._entries,
        }

        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._dirty = False
        except OSError as e:
            logger.warning("Failed to save cache: %s", e)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._entries = {}
        self._dirty = True

    def get_file_hash(self, file_path: Path) -> str | None:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to file.

        Returns:
            Hex-encoded SHA256 hash, or None if file doesn't exist.
        """
        if not file_path.exists():
            return None

        try:
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError as e:
            logger.debug("Failed to hash file %s: %s", file_path, e)
            return None

    def _get_file_mtime(self, file_path: Path) -> float:
        """Get file modification time."""
        try:
            return file_path.stat().st_mtime
        except OSError:
            return 0.0

    def _cache_key(self, file_path: Path) -> str:
        """Generate cache key for a file path."""
        return str(file_path.resolve())

    def is_file_changed(self, file_path: Path) -> bool:
        """Check if a file has changed since last scan.

        Uses mtime as quick check, falls back to hash if mtime changed.

        Args:
            file_path: Path to file.

        Returns:
            True if file has changed or is not in cache, False otherwise.
        """
        if not file_path.exists():
            return True

        key = self._cache_key(file_path)
        entry = self._entries.get(key)

        if entry is None:
            return True

        current_mtime = self._get_file_mtime(file_path)

        # Quick check: if mtime unchanged, assume file unchanged
        if entry.get("mtime") == current_mtime:
            return False

        # Mtime changed, check actual content hash
        current_hash = self.get_file_hash(file_path)
        return entry.get("hash") != current_hash

    def mark_file_scanned(self, file_path: Path) -> None:
        """Mark a file as scanned (store its hash and mtime).

        Args:
            file_path: Path to file.
        """
        if not file_path.exists():
            return

        key = self._cache_key(file_path)
        file_hash = self.get_file_hash(file_path)
        mtime = self._get_file_mtime(file_path)

        self._entries[key] = {
            "hash": file_hash,
            "mtime": mtime,
        }
        self._dirty = True

    def store_finding(self, file_path: Path, finding: dict[str, Any]) -> None:
        """Store a finding for a file.

        Args:
            file_path: Path to file.
            finding: Finding data to cache.
        """
        key = self._cache_key(file_path)
        file_hash = self.get_file_hash(file_path)
        mtime = self._get_file_mtime(file_path)

        self._entries[key] = {
            "hash": file_hash,
            "mtime": mtime,
            "finding": finding,
        }
        self._dirty = True

    def get_cached_finding(self, file_path: Path) -> dict[str, Any] | None:
        """Get cached finding for a file if still valid.

        Args:
            file_path: Path to file.

        Returns:
            Cached finding data, or None if not cached or invalidated.
        """
        if self.is_file_changed(file_path):
            return None

        key = self._cache_key(file_path)
        entry = self._entries.get(key)

        if entry is None:
            return None

        return entry.get("finding")

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache stats (cached_files, cache_size).
        """
        cache_size = 0
        if self._cache_file.exists():
            cache_size = self._cache_file.stat().st_size

        return {
            "cached_files": len(self._entries),
            "cache_size": cache_size,
        }
