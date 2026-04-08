"""Python Pickle model parser (.pkl)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# Pickle protocol magic bytes
PICKLE_MAGIC = (
    b"\x80\x02",  # Protocol 2
    b"\x80\x03",  # Protocol 3
    b"\x80\x04",  # Protocol 4
    b"\x80\x05",  # Protocol 5
)


class PickleParser(BaseModelParser):
    """Parse Python pickle model files (.pkl)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".pkl", ".pickle"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse pickle model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)

            if len(header) < 2:
                return None

            # Check for pickle format
            if header[:2] not in PICKLE_MAGIC:
                return None

            # Check minimum size for a model file
            file_size = file_path.stat().st_size
            if file_size < 1000:  # Less than 1KB is unlikely to be a model
                return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.6,  # Lower confidence - pickle is very generic
                model_info=ModelInfo(
                    format="pickle",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read pickle file %s: %s", file_path, e)
            return None
