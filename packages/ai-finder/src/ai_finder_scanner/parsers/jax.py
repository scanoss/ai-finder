"""JAX/Flax model parser (.msgpack)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Finding, FindingType, ModelInfo
from .base import BaseModelParser

logger = logging.getLogger(__name__)

_SNIFF_BYTES = 64 * 1024
# Flax's msgpack ext type codes: 1 ndarray, 2 native complex, 3 numpy scalar.
_FLAX_EXT_TYPES = frozenset({1, 2, 3})
# Payload width of the fixed-size msgpack scalars, keyed by type byte.
_FIXED_WIDTH = {
    0xCA: 4,
    0xCB: 8,
    0xCC: 1,
    0xCD: 2,
    0xCE: 4,
    0xCF: 8,
    0xD0: 1,
    0xD1: 2,
    0xD2: 4,
    0xD3: 8,
}


def _has_flax_array(buf: bytes) -> bool:
    """Walk the msgpack values in buf and report whether any is a Flax array ext.

    Walks the structure rather than searching bytes, so a str or bin payload that
    happens to contain ext-like bytes is skipped by its length. Stops quietly
    at the end of buf, which is only the head of the file.
    """
    pos, pending = 0, 1
    n = len(buf)

    def uint(at: int, size: int) -> int:
        return int.from_bytes(buf[at : at + size], "big")

    while pending and pos < n:
        b = buf[pos]
        pending -= 1
        if b <= 0x7F or b >= 0xE0 or b in (0xC0, 0xC2, 0xC3):  # fixint, nil, bool
            pos += 1
        elif 0x80 <= b <= 0x8F:  # fixmap
            pending += 2 * (b & 0x0F)
            pos += 1
        elif 0x90 <= b <= 0x9F:  # fixarray
            pending += b & 0x0F
            pos += 1
        elif 0xA0 <= b <= 0xBF:  # fixstr
            pos += 1 + (b & 0x1F)
        elif b in (0xC4, 0xD9):  # bin8, str8
            pos += 2 + uint(pos + 1, 1)
        elif b in (0xC5, 0xDA):  # bin16, str16
            pos += 3 + uint(pos + 1, 2)
        elif b in (0xC6, 0xDB):  # bin32, str32
            pos += 5 + uint(pos + 1, 4)
        elif b in (0xC7, 0xC8, 0xC9):  # ext8/16/32: size, type, data
            width = {0xC7: 1, 0xC8: 2, 0xC9: 4}[b]
            if pos + 1 + width < n and buf[pos + 1 + width] in _FLAX_EXT_TYPES:
                return True
            pos += 2 + width + uint(pos + 1, width)
        elif 0xD4 <= b <= 0xD8:  # fixext 1/2/4/8/16: type, data
            if pos + 1 < n and buf[pos + 1] in _FLAX_EXT_TYPES:
                return True
            pos += 2 + (1 << (b - 0xD4))
        elif b in _FIXED_WIDTH:  # float32/64, uint8-64, int8-64
            pos += 1 + _FIXED_WIDTH[b]
        elif b in (0xDC, 0xDD):  # array16/32
            width = 2 if b == 0xDC else 4
            pending += uint(pos + 1, width)
            pos += 1 + width
        elif b in (0xDE, 0xDF):  # map16/32
            width = 2 if b == 0xDE else 4
            pending += 2 * uint(pos + 1, width)
            pos += 1 + width
        else:  # 0xC1 is never used: not msgpack
            return False
    return False


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
                head = f.read(_SNIFF_BYTES)

            if len(head) < 1:
                return None

            # A Flax checkpoint is a msgpack map (the parameter tree) whose leaves
            # are arrays stored as msgpack ext values of Flax's ndarray type.
            # .msgpack is a generic data format, so both are required.
            first_byte = head[0]
            is_map = 0x80 <= first_byte <= 0x8F or first_byte in (0xDE, 0xDF)
            if not is_map or not _has_flax_array(head):
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
