"""PaddlePaddle model parser (.pdparams)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# PaddlePaddle uses pickle format
PICKLE_MAGIC = (b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05")


class PaddleParser(BaseModelParser):
    """Parse PaddlePaddle model files (.pdparams, .pdmodel)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".pdparams", ".pdmodel", ".pdopt"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse PaddlePaddle model file.

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

            # PaddlePaddle .pdparams uses pickle format
            if header[:2] in PICKLE_MAGIC:
                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=0.85,
                    model_info=ModelInfo(
                        format="paddle",
                        architecture=None,
                        parameter_count=None,
                        quantization=None,
                    ),
                )

            # .pdmodel uses protobuf
            if header[0] in (0x08, 0x0A, 0x10, 0x12):
                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=0.8,
                    model_info=ModelInfo(
                        format="paddle",
                        architecture=None,
                        parameter_count=None,
                        quantization=None,
                    ),
                )

            return None

        except OSError as e:
            logger.debug("Failed to read PaddlePaddle file %s: %s", file_path, e)
            return None
