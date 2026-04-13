"""Tests for identify command."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from click.testing import CliRunner
from ai_finder_cli.commands.identify import identify


class TestIdentifyCommand:
    def test_identify_gguf_file(self, tmp_path: Path) -> None:
        runner = CliRunner()

        # Create minimal GGUF file
        gguf_file = tmp_path / "model.gguf"
        header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 0)
        gguf_file.write_bytes(header + b"\x00" * 100)

        result = runner.invoke(identify, [str(gguf_file)])

        assert result.exit_code == 0
        assert "Recognized: yes" in result.output
        assert "Format:" in result.output
        assert "gguf" in result.output.lower()

    def test_identify_safetensors_file(self, tmp_path: Path) -> None:
        runner = CliRunner()

        # Create minimal SafeTensors file
        st_file = tmp_path / "model.safetensors"
        header_json = b'{"__metadata__": {"format": "pt"}}'
        header_size = struct.pack("<Q", len(header_json))
        st_file.write_bytes(header_size + header_json + b"\x00" * 100)

        result = runner.invoke(identify, [str(st_file)])

        assert result.exit_code == 0
        assert "Recognized: yes" in result.output
        assert "safetensors" in result.output.lower()

    def test_identify_unrecognized_file(self, tmp_path: Path) -> None:
        runner = CliRunner()

        # Create random file
        random_file = tmp_path / "random.bin"
        random_file.write_bytes(b"\x00\x01\x02\x03" * 100)

        result = runner.invoke(identify, [str(random_file)])

        assert result.exit_code == 1
        assert "Recognized: no" in result.output

    def test_identify_json_format(self, tmp_path: Path) -> None:
        runner = CliRunner()

        # Create minimal GGUF file
        gguf_file = tmp_path / "model.gguf"
        header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 0)
        gguf_file.write_bytes(header + b"\x00" * 100)

        result = runner.invoke(identify, [str(gguf_file), "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["recognized"] is True
        assert data["format"] == "gguf"
        assert "sha256" in data

    def test_identify_nonexistent_file(self) -> None:
        runner = CliRunner()

        result = runner.invoke(identify, ["/nonexistent/file.gguf"])

        assert result.exit_code == 2

    def test_identify_shows_hashes(self, tmp_path: Path) -> None:
        runner = CliRunner()

        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"test content")

        result = runner.invoke(identify, [str(test_file)])

        # Should show SHA-256 hash even for unrecognized files
        assert "SHA-256:" in result.output
