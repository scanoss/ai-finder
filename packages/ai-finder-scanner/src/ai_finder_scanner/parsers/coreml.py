"""Apple CoreML model parser."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)


class CoreMLParser(BaseModelParser):
    """Parse Apple CoreML model files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".mlmodel", ".mlpackage"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse CoreML model file.

        Args:
            file_path: Absolute path to the model file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid.
        """
        try:
            # .mlpackage is a directory bundle
            if file_path.suffix == ".mlpackage":
                if not file_path.is_dir():
                    return None
                # Check for required manifest
                manifest = file_path / "Manifest.json"
                if not manifest.exists():
                    return None
            else:
                # .mlmodel is a protobuf file
                with open(file_path, "rb") as f:
                    header = f.read(16)

                if len(header) < 1:
                    return None

                # CoreML uses protobuf format
                if header[0] not in (0x08, 0x0A, 0x10, 0x12):
                    return None

            return Finding(
                type=FindingType.MODEL_FILE,
                file_path=str(relative_path),
                confidence=0.9,
                model_info=ModelInfo(
                    format="coreml",
                    architecture=None,
                    parameter_count=None,
                    quantization=None,
                ),
            )

        except OSError as e:
            logger.debug("Failed to read CoreML file %s: %s", file_path, e)
            return None
