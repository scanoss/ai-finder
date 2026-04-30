"""Base manifest parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding


class BaseManifestParser(ABC):
    """Base class for manifest parsers."""

    @property
    @abstractmethod
    def manifest_names(self) -> frozenset[str]:
        """Manifest file names this parser handles.

        Returns:
            Set of file names (e.g., {"requirements.txt", "pyproject.toml"}).
        """

    @abstractmethod
    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse manifest content for AI dependencies.

        Args:
            content: Manifest file content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency found.
        """
