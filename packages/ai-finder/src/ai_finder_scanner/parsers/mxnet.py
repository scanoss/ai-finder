"""Apache MXNet model parser (.params)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

_NDARRAY_LIST_HEADER = (0x112).to_bytes(8, "little") + bytes(8)


class MXNetParser(BaseModelParser):
    """Parse Apache MXNet model files (.params)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".params"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse MXNet model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)

            if len(header) < 4:
                return None

            # MXNet .params files are an NDArray list: a little-endian uint64
            # magic (kMXAPINDArrayListMagic = 0x112) then a reserved uint64 of 0.
            # .params is a common extension, so the magic is what separates a
            # model from any other file of that name.
            if header != _NDARRAY_LIST_HEADER:
                return None
            file_size = file_path.stat().st_size
            if file_size < 100:  # Too small to be a real model
                return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.75,
                model_info=ModelInfo(
                    format="mxnet",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read MXNet file %s: %s", file_path, e)
            return None
