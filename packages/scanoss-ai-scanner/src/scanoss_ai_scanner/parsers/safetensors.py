"""SafeTensors model file parser."""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)


class SafeTensorsParser(BaseModelParser):
    """Parser for SafeTensors model files."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".safetensors"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse SafeTensors file and extract metadata.

        Args:
            file_path: Absolute path to the SafeTensors file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid SafeTensors.
        """
        try:
            with open(file_path, "rb") as f:
                # Read header size (8 bytes, little-endian)
                header_size_bytes = f.read(8)
                if len(header_size_bytes) < 8:
                    return None

                header_size = struct.unpack("<Q", header_size_bytes)[0]

                # Sanity check: header shouldn't be larger than 100MB
                if header_size > 100 * 1024 * 1024:
                    return None

                # Check if file is large enough
                file_size = file_path.stat().st_size
                if file_size < 8 + header_size:
                    return None

                # Read and parse header JSON
                header_bytes = f.read(header_size)
                if len(header_bytes) < header_size:
                    return None

                try:
                    header = json.loads(header_bytes.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return None

                # Extract metadata
                metadata = header.get("__metadata__", {})
                architecture = self._guess_architecture(relative_path.name, metadata)

                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=1.0,
                    model_info=ModelInfo(
                        format="safetensors",
                        architecture=architecture,
                    ),
                )

        except OSError as e:
            logger.debug("Failed to read SafeTensors file %s: %s", file_path, e)
            return None

    def _guess_architecture(
        self, filename: str, metadata: dict[str, str]
    ) -> str | None:
        """Guess model architecture from filename or metadata."""
        # Check metadata first
        if "model_type" in metadata:
            return str(metadata["model_type"])

        # Fall back to filename matching
        filename_lower = filename.lower()
        architectures = {
            "llama": "llama",
            "mistral": "mistral",
            "mixtral": "mixtral",
            "phi": "phi",
            "gemma": "gemma",
            "qwen": "qwen",
            "falcon": "falcon",
            "bert": "bert",
            "gpt2": "gpt2",
            "t5": "t5",
            "whisper": "whisper",
            "stable-diffusion": "stable-diffusion",
            "sdxl": "sdxl",
        }
        for pattern, arch in architectures.items():
            if pattern in filename_lower:
                return arch
        return None
