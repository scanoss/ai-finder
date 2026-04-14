"""GGUF model file parser."""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

# GGUF magic number: "GGUF" in little-endian
GGUF_MAGIC = b"GGUF"
GGUF_HEADER_SIZE = 24  # magic(4) + version(4) + tensor_count(8) + kv_count(8)


class GGUFParser(BaseModelParser):
    """Parser for GGUF model files (llama.cpp format)."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".gguf"})

    def parse(self, file_path: Path, relative_path: Path) -> Finding | None:
        """Parse GGUF file and extract metadata.

        Args:
            file_path: Absolute path to the GGUF file.
            relative_path: Path relative to scan root.

        Returns:
            Finding with model info, or None if not valid GGUF.
        """
        try:
            with open(file_path, "rb") as f:
                # Read and validate magic number
                magic = f.read(4)
                if magic != GGUF_MAGIC:
                    return None

                # Read version
                version_bytes = f.read(4)
                if len(version_bytes) < 4:
                    return None
                struct.unpack("<I", version_bytes)  # Validate version field

                # Read tensor count and kv count
                counts = f.read(16)
                if len(counts) < 16:
                    return None

                tensor_count, kv_count = struct.unpack("<QQ", counts)

                # Extract quantization from filename if present
                quantization = self._extract_quantization(relative_path.name)

                return Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=str(relative_path),
                    confidence=1.0,
                    model_info=ModelInfo(
                        format="gguf",
                        architecture=self._guess_architecture(relative_path.name),
                        quantization=quantization,
                    ),
                )

        except OSError as e:
            logger.debug("Failed to read GGUF file %s: %s", file_path, e)
            return None

    def _extract_quantization(self, filename: str) -> str | None:
        """Extract quantization type from filename."""
        filename_upper = filename.upper()
        # Common GGUF quantization patterns
        quant_patterns = [
            "Q4_K_M",
            "Q4_K_S",
            "Q5_K_M",
            "Q5_K_S",
            "Q6_K",
            "Q8_0",
            "Q4_0",
            "Q4_1",
            "Q5_0",
            "Q5_1",
            "IQ4_NL",
            "IQ4_XS",
            "IQ3_XXS",
            "IQ2_XXS",
            "F16",
            "F32",
            "BF16",
        ]
        for pattern in quant_patterns:
            if pattern in filename_upper:
                return pattern
        return None

    def _guess_architecture(self, filename: str) -> str | None:
        """Guess model architecture from filename."""
        filename_lower = filename.lower()
        architectures = {
            "llama": "llama",
            "mistral": "mistral",
            "mixtral": "mixtral",
            "phi": "phi",
            "gemma": "gemma",
            "qwen": "qwen",
            "falcon": "falcon",
            "mpt": "mpt",
            "starcoder": "starcoder",
            "codellama": "llama",
        }
        for pattern, arch in architectures.items():
            if pattern in filename_lower:
                return arch
        return None
