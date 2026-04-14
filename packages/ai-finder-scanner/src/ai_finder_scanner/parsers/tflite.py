"""TensorFlow Lite model parser."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# TFLite magic bytes (FlatBuffers format)
# TFLite files start with a FlatBuffer identifier
TFLITE_IDENTIFIER = b"TFL3"


class TFLiteParser(BaseModelParser):
    """Parse TensorFlow Lite model files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".tflite"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse TFLite model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                # TFLite uses FlatBuffers format
                # The identifier is at offset 4
                header = f.read(8)

            if len(header) < 8:
                return None

            # Check for TFLite identifier at offset 4
            identifier = header[4:8]
            # Accept TFL3 (current) and older versions TFL2, TFL1
            if identifier not in (TFLITE_IDENTIFIER, b"TFL2", b"TFL1"):
                return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.95,
                model_info=ModelInfo(
                    format="tflite",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read TFLite file %s: %s", file_path, e)
            return None
