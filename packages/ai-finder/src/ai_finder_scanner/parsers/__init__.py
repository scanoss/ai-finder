"""Model file parsers."""

from __future__ import annotations

from .base import BaseModelParser
from .coreml import CoreMLParser
from .gguf import GGUFParser
from .jax import JAXParser
from .keras import KerasParser
from .mxnet import MXNetParser
from .onnx import ONNXParser
from .paddle import PaddleParser
from .pickle import PickleParser
from .pytorch import PyTorchParser
from .safetensors import SafeTensorsParser
from .tensorflow import TensorFlowParser
from .tflite import TFLiteParser

__all__ = [
    "BaseModelParser",
    "CoreMLParser",
    "GGUFParser",
    "JAXParser",
    "KerasParser",
    "MXNetParser",
    "ONNXParser",
    "PaddleParser",
    "PickleParser",
    "PyTorchParser",
    "SafeTensorsParser",
    "TensorFlowParser",
    "TFLiteParser",
]
