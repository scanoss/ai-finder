"""Base model parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import Finding


class BaseModelParser(ABC):
    """Base class for model file parsers."""

    @property
    @abstractmethod
    def extensions(self) -> frozenset[str]:
        """File extensions this parser handles.

        Returns:
            Set of extensions (e.g., {".gguf"}).
        """

    @abstractmethod
    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse a model file and extract metadata.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not a valid model.
        """
