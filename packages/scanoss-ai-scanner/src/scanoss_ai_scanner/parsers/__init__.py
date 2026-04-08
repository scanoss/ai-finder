"""Model file parsers."""

from __future__ import annotations

from .base import BaseModelParser
from .gguf import GGUFParser
from .onnx import ONNXParser
from .pytorch import PyTorchParser
from .safetensors import SafeTensorsParser

__all__ = [
    "BaseModelParser",
    "GGUFParser",
    "ONNXParser",
    "PyTorchParser",
    "SafeTensorsParser",
]
