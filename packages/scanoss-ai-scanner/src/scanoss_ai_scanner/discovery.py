"""File discovery for scanning."""

from __future__ import annotations

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
        # C/C++
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",
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

    def _should_skip_dir(self, path: Path) -> bool:
        """Check if a directory should be skipped."""
        return path.name in IGNORE_DIRS

    def _walk_files(self) -> Iterator[Path]:
        """Walk all files, skipping ignored directories."""
        for item in self.root.rglob("*"):
            # Skip if any parent is an ignored directory
            skip = False
            for parent in item.relative_to(self.root).parents:
                if parent.name in IGNORE_DIRS:
                    skip = True
                    break
            if skip:
                continue

            if item.is_file():
                yield item.relative_to(self.root)

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
