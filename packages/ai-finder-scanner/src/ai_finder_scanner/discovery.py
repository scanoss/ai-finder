"""File discovery for scanning."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

# Directories to always ignore
IGNORE_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        ".bzr",
        "node_modules",
        "__pycache__",
        ".tox",
        ".nox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
    }
)

# Source file extensions by language
SOURCE_EXTENSIONS = frozenset(
    {
        # Python
        ".py",
        # JavaScript/TypeScript
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        # Go
        ".go",
        # Rust
        ".rs",
        # Java
        ".java",
        # Kotlin
        ".kt",
        ".kts",
        # Scala
        ".scala",
        ".sc",
        # C/C++
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",
        ".hxx",
        # C#
        ".cs",
        # Ruby
        ".rb",
        # PHP
        ".php",
        # Swift
        ".swift",
    }
)

# Manifest file names
MANIFEST_FILES = frozenset(
    {
        # Python
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "poetry.lock",
        # JavaScript/Node
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        # Go
        "go.mod",
        "go.sum",
        # Rust
        "Cargo.toml",
        "Cargo.lock",
        # Java
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        # Ruby
        "Gemfile",
        "Gemfile.lock",
        # PHP
        "composer.json",
        "composer.lock",
    }
)

# Model file extensions
MODEL_EXTENSIONS = frozenset(
    {
        ".gguf",
        ".safetensors",
        ".bin",
        ".pt",
        ".pth",
        ".onnx",
        ".tflite",
        ".mlmodel",
        ".h5",
        ".keras",
        ".pb",
        ".pkl",
    }
)

# Config files that may contain AI references
CONFIG_PATTERNS = frozenset(
    {
        "claude_desktop_config.json",
        "mcp.json",
        ".mcp.json",
        "cline_mcp_settings.json",
    }
)


class FileDiscovery:
    """Discover files for scanning in a directory tree."""

    def __init__(self, root: Path) -> None:
        """Initialize file discovery.

        Args:
            root: Root directory to scan.
        """
        self.root = Path(root).resolve()
        # Cache for single-pass scanning
        self._cached_files: dict[str, list[Path]] | None = None

    def _should_skip_dir(self, path: Path) -> bool:
        """Check if a directory should be skipped."""
        return path.name in IGNORE_DIRS

    def _walk_files(self) -> Iterator[Path]:
        """Walk all files, skipping ignored directories.

        Uses os.walk with in-place directory pruning for efficiency.
        This avoids traversing into large ignored directories like node_modules.
        """
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories IN-PLACE (prevents descent)
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

            for filename in filenames:
                full_path = Path(dirpath) / filename
                yield full_path.relative_to(self.root)

    def _build_cache(self) -> None:
        """Build file cache with single directory walk (efficient for large codebases)."""
        if self._cached_files is not None:
            return

        self._cached_files = {
            "source": [],
            "manifest": [],
            "model": [],
            "config": [],
        }

        for path in self._walk_files():
            ext = path.suffix.lower()
            name = path.name

            if ext in SOURCE_EXTENSIONS:
                self._cached_files["source"].append(path)
            if name in MANIFEST_FILES:
                self._cached_files["manifest"].append(path)
            if ext in MODEL_EXTENSIONS:
                self._cached_files["model"].append(path)
            if name in CONFIG_PATTERNS:
                self._cached_files["config"].append(path)

    def collect_all(self) -> dict[str, list[Path]]:
        """Collect all files in a single pass (optimized for large codebases).

        Returns:
            Dict with keys 'source', 'manifest', 'model', 'config' containing file lists.
        """
        self._build_cache()
        return self._cached_files  # type: ignore

    def source_files(self) -> Iterator[Path]:
        """Yield source code files.

        Returns:
            Iterator of paths relative to root.
        """
        for path in self._walk_files():
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                yield path

    def manifest_files(self) -> Iterator[Path]:
        """Yield manifest/dependency files.

        Returns:
            Iterator of paths relative to root.
        """
        for path in self._walk_files():
            if path.name in MANIFEST_FILES:
                yield path

    def model_files(self) -> Iterator[Path]:
        """Yield model files.

        Returns:
            Iterator of paths relative to root.
        """
        for path in self._walk_files():
            if path.suffix.lower() in MODEL_EXTENSIONS:
                yield path

    def config_files(self) -> Iterator[Path]:
        """Yield config files that may reference AI components.

        Returns:
            Iterator of paths relative to root.
        """
        for path in self._walk_files():
            if path.name in CONFIG_PATTERNS:
                yield path

    def all_files(self) -> Iterator[Path]:
        """Yield all scannable files.

        Returns:
            Iterator of paths relative to root.
        """
        seen: set[Path] = set()

        for path in self.source_files():
            if path not in seen:
                seen.add(path)
                yield path

        for path in self.manifest_files():
            if path not in seen:
                seen.add(path)
                yield path

        for path in self.model_files():
            if path not in seen:
                seen.add(path)
                yield path

        for path in self.config_files():
            if path not in seen:
                seen.add(path)
                yield path

    def count_files(self) -> int:
        """Count all scannable files.

        Returns:
            Number of files.
        """
        return sum(1 for _ in self.all_files())
