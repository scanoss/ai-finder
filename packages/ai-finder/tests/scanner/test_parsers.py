"""Tests for model file parsers."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from ai_finder_scanner.models import FindingType
from ai_finder_scanner.parsers.base import BaseModelParser
from ai_finder_scanner.parsers.coreml import CoreMLParser
from ai_finder_scanner.parsers.gguf import GGUFParser
from ai_finder_scanner.parsers.jax import JAXParser
from ai_finder_scanner.parsers.keras import KerasParser
from ai_finder_scanner.parsers.mxnet import MXNetParser
from ai_finder_scanner.parsers.onnx import ONNXParser
from ai_finder_scanner.parsers.paddle import PaddleParser
from ai_finder_scanner.parsers.pickle import PickleParser
from ai_finder_scanner.parsers.pytorch import PyTorchParser
from ai_finder_scanner.parsers.safetensors import SafeTensorsParser
from ai_finder_scanner.parsers.tensorflow import TensorFlowParser
from ai_finder_scanner.parsers.tflite import TFLiteParser


class TestBaseModelParser:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseModelParser()  # type: ignore


class TestGGUFParser:
    @pytest.fixture
    def parser(self) -> GGUFParser:
        return GGUFParser()

    def test_supported_extensions(self, parser: GGUFParser) -> None:
        assert ".gguf" in parser.extensions

    def test_parse_valid_gguf_header(self, parser: GGUFParser, tmp_path: Path) -> None:
        # Create minimal GGUF file with magic number and version
        gguf_file = tmp_path / "model.gguf"
        # GGUF magic: "GGUF" (0x46554747) + version (3) + tensor count + kv count
        header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 0)
        gguf_file.write_bytes(header + b"\x00" * 100)

        finding = parser.parse(gguf_file, Path("model.gguf"))

        assert finding is not None
        assert finding.type == FindingType.MODEL_FILE
        assert finding.model_info is not None
        assert finding.model_info.format == "gguf"

    def test_parse_invalid_magic(self, parser: GGUFParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "not_gguf.bin"
        bad_file.write_bytes(b"NOTG" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("not_gguf.bin"))
        assert finding is None

    def test_parse_file_too_small(self, parser: GGUFParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.gguf"
        small_file.write_bytes(b"GGU")

        finding = parser.parse(small_file, Path("small.gguf"))
        assert finding is None


class TestSafeTensorsParser:
    @pytest.fixture
    def parser(self) -> SafeTensorsParser:
        return SafeTensorsParser()

    def test_supported_extensions(self, parser: SafeTensorsParser) -> None:
        assert ".safetensors" in parser.extensions

    def test_parse_valid_safetensors(self, parser: SafeTensorsParser, tmp_path: Path) -> None:
        # SafeTensors format: 8-byte header size (little endian) + JSON header
        st_file = tmp_path / "model.safetensors"
        header_json = b'{"__metadata__": {"format": "pt"}}'
        header_size = struct.pack("<Q", len(header_json))
        st_file.write_bytes(header_size + header_json + b"\x00" * 100)

        finding = parser.parse(st_file, Path("model.safetensors"))

        assert finding is not None
        assert finding.type == FindingType.MODEL_FILE
        assert finding.model_info is not None
        assert finding.model_info.format == "safetensors"

    def test_parse_invalid_header_size(self, parser: SafeTensorsParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.safetensors"
        # Header size larger than file
        bad_file.write_bytes(struct.pack("<Q", 999999) + b"\x00" * 10)

        finding = parser.parse(bad_file, Path("bad.safetensors"))
        assert finding is None

    def test_parse_file_too_small(self, parser: SafeTensorsParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.safetensors"
        small_file.write_bytes(b"\x00" * 4)

        finding = parser.parse(small_file, Path("small.safetensors"))
        assert finding is None


class TestONNXParser:
    @pytest.fixture
    def parser(self) -> ONNXParser:
        return ONNXParser()

    def test_supported_extensions(self, parser: ONNXParser) -> None:
        assert ".onnx" in parser.extensions

    def test_parse_valid_onnx(self, parser: ONNXParser, tmp_path: Path) -> None:
        # ONNX files start with protobuf field 1 (ir_version) as varint
        onnx_file = tmp_path / "model.onnx"
        # 0x08 = field 1, varint; 0x07 = value 7 (ir_version)
        onnx_file.write_bytes(b"\x08\x07" + b"\x00" * 100)

        finding = parser.parse(onnx_file, Path("model.onnx"))

        assert finding is not None
        assert finding.type == FindingType.MODEL_FILE
        assert finding.model_info is not None
        assert finding.model_info.format == "onnx"

    def test_parse_invalid_header(self, parser: ONNXParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.onnx"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.onnx"))
        assert finding is None

    def test_parse_file_too_small(self, parser: ONNXParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.onnx"
        small_file.write_bytes(b"\x08")

        finding = parser.parse(small_file, Path("small.onnx"))
        assert finding is None


class TestPyTorchParser:
    @pytest.fixture
    def parser(self) -> PyTorchParser:
        return PyTorchParser()

    def test_supported_extensions(self, parser: PyTorchParser) -> None:
        assert ".pt" in parser.extensions
        assert ".pth" in parser.extensions
        assert ".bin" in parser.extensions

    def test_parse_pickle_format(self, parser: PyTorchParser, tmp_path: Path) -> None:
        # Pickle protocol 2+ starts with 0x80
        pt_file = tmp_path / "model.pt"
        pt_file.write_bytes(b"\x80\x02" + b"\x00" * 100)

        finding = parser.parse(pt_file, Path("model.pt"))

        assert finding is not None
        assert finding.type == FindingType.MODEL_FILE
        assert finding.model_info is not None
        assert finding.model_info.format == "pytorch"

    def test_parse_invalid_format(self, parser: PyTorchParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.pt"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.pt"))
        assert finding is None

    def test_parse_file_too_small(self, parser: PyTorchParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.pt"
        small_file.write_bytes(b"\x80")

        finding = parser.parse(small_file, Path("small.pt"))
        assert finding is None


# ============ NEW MODEL PARSER TESTS ============


class TestTensorFlowParser:
    @pytest.fixture
    def parser(self) -> TensorFlowParser:
        return TensorFlowParser()

    def test_supported_extensions(self, parser: TensorFlowParser) -> None:
        assert ".pb" in parser.extensions

    def test_parse_protobuf_format(self, parser: TensorFlowParser, tmp_path: Path) -> None:
        # Protobuf starts with varint field tag
        pb_file = tmp_path / "saved_model.pb"
        pb_file.write_bytes(b"\x08\x01" + b"\x00" * 100)

        finding = parser.parse(pb_file, Path("saved_model.pb"))

        assert finding is not None
        assert finding.model_info.format == "tensorflow"

    def test_parse_invalid_format(self, parser: TensorFlowParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.pb"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.pb"))
        assert finding is None


class TestTFLiteParser:
    @pytest.fixture
    def parser(self) -> TFLiteParser:
        return TFLiteParser()

    def test_supported_extensions(self, parser: TFLiteParser) -> None:
        assert ".tflite" in parser.extensions

    def test_parse_tflite_format(self, parser: TFLiteParser, tmp_path: Path) -> None:
        # TFLite has identifier at offset 4
        tflite_file = tmp_path / "model.tflite"
        tflite_file.write_bytes(b"\x00\x00\x00\x00TFL3" + b"\x00" * 100)

        finding = parser.parse(tflite_file, Path("model.tflite"))

        assert finding is not None
        assert finding.model_info.format == "tflite"

    def test_parse_invalid_format(self, parser: TFLiteParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.tflite"
        bad_file.write_bytes(b"\x00\x00\x00\x00XXXX" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.tflite"))
        assert finding is None


class TestCoreMLParser:
    @pytest.fixture
    def parser(self) -> CoreMLParser:
        return CoreMLParser()

    def test_supported_extensions(self, parser: CoreMLParser) -> None:
        assert ".mlmodel" in parser.extensions
        assert ".mlpackage" in parser.extensions

    def test_parse_mlmodel_format(self, parser: CoreMLParser, tmp_path: Path) -> None:
        # CoreML uses protobuf
        mlmodel_file = tmp_path / "model.mlmodel"
        mlmodel_file.write_bytes(b"\x08\x01" + b"\x00" * 100)

        finding = parser.parse(mlmodel_file, Path("model.mlmodel"))

        assert finding is not None
        assert finding.model_info.format == "coreml"

    def test_parse_invalid_format(self, parser: CoreMLParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.mlmodel"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.mlmodel"))
        assert finding is None


class TestKerasParser:
    @pytest.fixture
    def parser(self) -> KerasParser:
        return KerasParser()

    def test_supported_extensions(self, parser: KerasParser) -> None:
        assert ".h5" in parser.extensions
        assert ".keras" in parser.extensions

    def test_parse_h5_format(self, parser: KerasParser, tmp_path: Path) -> None:
        # HDF5 magic bytes
        h5_file = tmp_path / "model.h5"
        h5_file.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 100)

        finding = parser.parse(h5_file, Path("model.h5"))

        assert finding is not None
        assert finding.model_info.format == "keras-h5"

    def test_parse_keras_zip_format(self, parser: KerasParser, tmp_path: Path) -> None:
        # ZIP magic bytes (Keras v3)
        keras_file = tmp_path / "model.keras"
        keras_file.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        finding = parser.parse(keras_file, Path("model.keras"))

        assert finding is not None
        assert finding.model_info.format == "keras"

    def test_parse_invalid_format(self, parser: KerasParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.h5"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.h5"))
        assert finding is None


class TestJAXParser:
    @pytest.fixture
    def parser(self) -> JAXParser:
        return JAXParser()

    def test_supported_extensions(self, parser: JAXParser) -> None:
        assert ".msgpack" in parser.extensions

    def test_parse_msgpack_format(self, parser: JAXParser, tmp_path: Path) -> None:
        # MessagePack fixmap format
        msgpack_file = tmp_path / "params.msgpack"
        msgpack_file.write_bytes(b"\x80" + b"\x00" * 100)

        finding = parser.parse(msgpack_file, Path("params.msgpack"))

        assert finding is not None
        assert finding.model_info.format == "jax"

    def test_parse_invalid_format(self, parser: JAXParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.msgpack"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.msgpack"))
        assert finding is None


class TestMXNetParser:
    @pytest.fixture
    def parser(self) -> MXNetParser:
        return MXNetParser()

    def test_supported_extensions(self, parser: MXNetParser) -> None:
        assert ".params" in parser.extensions

    def test_parse_params_format(self, parser: MXNetParser, tmp_path: Path) -> None:
        # MXNet params file (needs to be large enough)
        params_file = tmp_path / "model.params"
        params_file.write_bytes(b"\x00" * 1000)

        finding = parser.parse(params_file, Path("model.params"))

        assert finding is not None
        assert finding.model_info.format == "mxnet"

    def test_parse_file_too_small(self, parser: MXNetParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.params"
        small_file.write_bytes(b"\x00" * 10)

        finding = parser.parse(small_file, Path("small.params"))
        assert finding is None


class TestPaddleParser:
    @pytest.fixture
    def parser(self) -> PaddleParser:
        return PaddleParser()

    def test_supported_extensions(self, parser: PaddleParser) -> None:
        assert ".pdparams" in parser.extensions
        assert ".pdmodel" in parser.extensions

    def test_parse_pdparams_format(self, parser: PaddleParser, tmp_path: Path) -> None:
        # Pickle format
        pdparams_file = tmp_path / "model.pdparams"
        pdparams_file.write_bytes(b"\x80\x04" + b"\x00" * 100)

        finding = parser.parse(pdparams_file, Path("model.pdparams"))

        assert finding is not None
        assert finding.model_info.format == "paddle"

    def test_parse_invalid_format(self, parser: PaddleParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.pdparams"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 100)

        finding = parser.parse(bad_file, Path("bad.pdparams"))
        assert finding is None


class TestPickleParser:
    @pytest.fixture
    def parser(self) -> PickleParser:
        return PickleParser()

    def test_supported_extensions(self, parser: PickleParser) -> None:
        assert ".pkl" in parser.extensions
        assert ".pickle" in parser.extensions

    def test_parse_pickle_format(self, parser: PickleParser, tmp_path: Path) -> None:
        # Pickle protocol 4
        pkl_file = tmp_path / "model.pkl"
        pkl_file.write_bytes(b"\x80\x04" + b"\x00" * 2000)

        finding = parser.parse(pkl_file, Path("model.pkl"))

        assert finding is not None
        assert finding.model_info.format == "pickle"

    def test_parse_file_too_small(self, parser: PickleParser, tmp_path: Path) -> None:
        small_file = tmp_path / "small.pkl"
        small_file.write_bytes(b"\x80\x04" + b"\x00" * 10)

        finding = parser.parse(small_file, Path("small.pkl"))
        assert finding is None

    def test_parse_invalid_format(self, parser: PickleParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.pkl"
        bad_file.write_bytes(b"\x00\x00" + b"\x00" * 2000)

        finding = parser.parse(bad_file, Path("bad.pkl"))
        assert finding is None
