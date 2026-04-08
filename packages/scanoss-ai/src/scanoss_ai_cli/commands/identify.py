"""identify command - identify a single AI artifact file."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import click
from scanoss_ai_scanner.parsers import GGUFParser, ONNXParser, PyTorchParser, SafeTensorsParser
from scanoss_ai_scanner.parsers.base import BaseModelParser


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@click.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def identify(file: Path, output_format: str) -> None:
    """Identify a single AI artifact file.

    Parses FILE, computes hashes, and outputs metadata.
    Exit code 0 on success, 1 if unrecognised format, 2 on error.
    """
    parsers: list[BaseModelParser] = [
        GGUFParser(),
        SafeTensorsParser(),
        ONNXParser(),
        PyTorchParser(),
    ]

    file_path = file.resolve()

    try:
        # Compute hash
        sha256 = _compute_sha256(file_path)

        # Try each parser based on extension
        matched_finding = None
        ext = file_path.suffix.lower()

        for parser in parsers:
            if ext in parser.extensions:
                finding = parser.parse(file_path, file_path)
                if finding and finding.model_info:
                    matched_finding = finding
                    break

        info: dict[str, Any] = {
            "file": str(file_path),
            "sha256": sha256,
            "recognized": matched_finding is not None,
        }

        if matched_finding and matched_finding.model_info:
            mi = matched_finding.model_info
            info["format"] = mi.format
            if mi.architecture:
                info["architecture"] = mi.architecture
            if mi.parameter_count is not None:
                info["parameter_count"] = mi.parameter_count
            if mi.quantization:
                info["quantization"] = mi.quantization

        if output_format == "json":
            click.echo(json.dumps(info, indent=2))
        else:
            _print_text(info)

        sys.exit(0 if info["recognized"] else 1)

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)


def _print_text(info: dict[str, Any]) -> None:
    """Print identify result in human-readable text format."""
    click.echo(f"File:       {info['file']}")
    click.echo(f"SHA-256:    {info['sha256']}")
    recognized = info.get("recognized", False)
    click.echo(f"Recognized: {'yes' if recognized else 'no'}")
    if recognized:
        if info.get("format"):
            click.echo(f"Format:     {info['format']}")
        if info.get("architecture"):
            click.echo(f"Architecture: {info['architecture']}")
        if info.get("parameter_count") is not None:
            click.echo(f"Parameters: {info['parameter_count']:,}")
        if info.get("quantization"):
            click.echo(f"Quantization: {info['quantization']}")
