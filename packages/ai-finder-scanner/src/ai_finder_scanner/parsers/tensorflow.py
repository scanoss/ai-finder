"""TensorFlow SavedModel parser."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# TensorFlow SavedModel signature
# saved_model.pb starts with protobuf header
PROTOBUF_MAGIC = b"\x08"  # Varint field tag


class TensorFlowParser(BaseModelParser):
    """Parse TensorFlow SavedModel files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".pb"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse TensorFlow SavedModel file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)

            if len(header) < 1:
                return None

            # Check for protobuf format (starts with varint field tag)
            # This is a heuristic - .pb files are protobuf serialized
            if header[0] not in (0x08, 0x0A, 0x10, 0x12, 0x18, 0x1A, 0x20, 0x22):
                return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.8,
                model_info=ModelInfo(
                    format="tensorflow",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read TensorFlow file %s: %s", file_path, e)
            return None
