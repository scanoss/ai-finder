"""Tests for model file parsers."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from scanoss_ai_scanner.models import FindingType
from scanoss_ai_scanner.parsers.base import BaseModelParser
from scanoss_ai_scanner.parsers.gguf import GGUFParser
from scanoss_ai_scanner.parsers.onnx import ONNXParser
from scanoss_ai_scanner.parsers.pytorch import PyTorchParser
from scanoss_ai_scanner.parsers.safetensors import SafeTensorsParser


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
