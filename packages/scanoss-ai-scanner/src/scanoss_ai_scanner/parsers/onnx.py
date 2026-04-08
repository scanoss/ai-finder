"""ONNX model file parser."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# ONNX magic bytes (protobuf wire format)
# ONNX files start with a protobuf message, field 1 (ir_version) as varint
ONNX_MIN_SIZE = 8


class ONNXParser(BaseModelParser):
    """Parser for ONNX model files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".onnx"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse ONNX file and extract metadata.

        Args:
            file_path: Absolute path to the ONNX file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid ONNX.
        """
        try:
            file_size = file_path.stat().st_size
            if file_size < ONNX_MIN_SIZE:
                return None

            with open(file_path, "rb") as f:
                # ONNX uses protobuf format
                # First byte should be field tag (0x08 = field 1, varint)
                first_byte = f.read(1)
                if not first_byte or first_byte[0] != 0x08:
                    return None

                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=0.9,  # Lower confidence without full protobuf parse
                    model_info=ModelInfo(
                        format="onnx",
                        architecture=self._guess_architecture(relative_path.name),
                    ),
                )

        except OSError as e:
            logger.debug("Failed to read ONNX file %s: %s", file_path, e)
            return None

    def _guess_architecture(self, filename: str) -> str | None:
        """Guess model architecture from filename."""
        filename_lower = filename.lower()
        architectures = {
            "bert": "bert",
            "gpt": "gpt",
            "resnet": "resnet",
            "vit": "vit",
            "yolo": "yolo",
            "whisper": "whisper",
            "llama": "llama",
            "clip": "clip",
        }
        for pattern, arch in architectures.items():
            if pattern in filename_lower:
                return arch
        return None
