"""Keras model parser (.h5, .keras)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# HDF5 magic bytes (used by .h5 files)
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"

# Keras v3 uses ZIP format
ZIP_MAGIC = b"PK\x03\x04"


class KerasParser(BaseModelParser):
    """Parse Keras model files (.h5, .keras)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".h5", ".keras"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse Keras model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)

            if len(header) < 4:
                return None

            # Check for HDF5 format (.h5)
            if header[:8] == HDF5_MAGIC:
                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=0.9,
                    model_info=ModelInfo(
                        format="keras-h5",
                        architecture=None,
                        parameter_count=None,
                        quantization=None,
                    ),
                )

            # Check for ZIP format (.keras - Keras v3)
            if header[:4] == ZIP_MAGIC:
                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=0.9,
                    model_info=ModelInfo(
                        format="keras",
                        architecture=None,
                        parameter_count=None,
                        quantization=None,
                    ),
                )

            return None

        except OSError as e:
            logger.debug("Failed to read Keras file %s: %s", file_path, e)
            return None
