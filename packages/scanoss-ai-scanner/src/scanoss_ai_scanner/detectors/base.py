"""Base detector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import Finding

if TYPE_CHECKING:
    pass  # Matcher import would go here when KB is available


class BaseDetector(ABC):
    """Base class for SDK detectors."""

    @property
    @abstractmethod
    def extensions(self) -> frozenset[str]:
        """File extensions this detector handles.

        Returns:
            Set of extensions (e.g., {".py"}).
        """

    @abstractmethod
    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect SDK usage in file content.

        Args:
            content: File content to analyze.
            path: File path (relative to scan root).
            matcher: Optional KB Matcher for pattern lookup. When provided,
                     patterns are loaded from the KB for extensibility.

        Yields:
            Finding for each SDK usage detected.
        """
