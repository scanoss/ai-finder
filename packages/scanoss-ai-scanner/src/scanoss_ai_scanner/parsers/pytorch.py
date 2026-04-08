"""PyTorch model file parser."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# PyTorch .pt/.pth files are either:
# 1. Pickle files (legacy) - start with pickle opcodes
# 2. ZIP files (torch.save with _use_new_zipfile_serialization=True)
PICKLE_MAGIC = b"\x80"  # Protocol 2+ pickle


class PyTorchParser(BaseModelParser):
    """Parser for PyTorch model files (.pt, .pth, .bin)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".pt", ".pth", ".bin"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse PyTorch file and extract metadata.

        Args:
            file_path: Absolute path to the PyTorch file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid PyTorch.
        """
        try:
            file_size = file_path.stat().st_size
            if file_size < 4:
                return None

            # Check if it's a ZIP file (modern PyTorch format)
            if zipfile.is_zipfile(file_path):
                return self._parse_zip_format(file_path, relative_path)

            # Check for pickle format (legacy)
            with open(file_path, "rb") as f:
                first_byte = f.read(1)
                if first_byte == PICKLE_MAGIC:
                    return Finding(
                        type=FindingType.MODEL_FILE,
                        file_path=str(relative_path),
                        confidence=0.8,  # Lower confidence for pickle
                        model_info=ModelInfo(
                            format="pytorch",
                            architecture=self._guess_architecture(relative_path.name),
                        ),
                    )

            return None

        except OSError as e:
            logger.debug("Failed to read PyTorch file %s: %s", file_path, e)
            return None

    def _parse_zip_format(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse modern ZIP-based PyTorch format."""
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()
                # PyTorch ZIP files typically contain data.pkl and version
                is_pytorch = any(
                    "data.pkl" in n or "version" in n or "byteorder" in n for n in names
                )
                if is_pytorch:
                    return Finding(
                        type=FindingType.MODEL_FILE,
                        file_path=str(relative_path),
                        confidence=0.95,
                        model_info=ModelInfo(
                            format="pytorch",
                            architecture=self._guess_architecture(relative_path.name),
                        ),
                    )
        except zipfile.BadZipFile:
            pass
        return None

    def _guess_architecture(self, filename: str) -> str | None:
        """Guess model architecture from filename."""
        filename_lower = filename.lower()
        architectures = {
            "bert": "bert",
            "gpt": "gpt",
            "llama": "llama",
            "mistral": "mistral",
            "resnet": "resnet",
            "vit": "vit",
            "clip": "clip",
            "whisper": "whisper",
            "stable": "stable-diffusion",
        }
        for pattern, arch in architectures.items():
            if pattern in filename_lower:
                return arch
        return None
