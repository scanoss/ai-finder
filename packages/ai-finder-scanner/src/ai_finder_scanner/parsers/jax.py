"""JAX/Flax model parser (.msgpack)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)


class JAXParser(BaseModelParser):
    """Parse JAX/Flax model files (.msgpack)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".msgpack"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse JAX model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)

            if len(header) < 1:
                return None

            # MessagePack format detection
            # Map types: 0x80-0x8f (fixmap), 0xde (map16), 0xdf (map32)
            # Array types: 0x90-0x9f (fixarray), 0xdc (array16), 0xdd (array32)
            first_byte = header[0]
            is_msgpack = (
                (0x80 <= first_byte <= 0x8F)  # fixmap
                or (0x90 <= first_byte <= 0x9F)  # fixarray
                or first_byte in (0xDC, 0xDD, 0xDE, 0xDF)  # array/map 16/32
            )

            if not is_msgpack:
                return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.7,  # Lower confidence - msgpack is generic format
                model_info=ModelInfo(
                    format="jax",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read JAX file %s: %s", file_path, e)
            return None
