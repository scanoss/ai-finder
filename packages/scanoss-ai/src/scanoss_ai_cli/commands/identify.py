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

from scanoss_ai_cli import telemetry


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
@click.option(
    "--no-enrich",
    is_flag=True,
    help="Disable KB lookup for model identification.",
)
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    envvar="SCANOSS_KB_PATH",
    help="Path to KB database (default: ~/.scanoss-ai/kb/scanoss-ai.db)",
)
def identify(file: Path, output_format: str, no_enrich: bool, kb_path: Path | None) -> None:
    """Identify a single AI artifact file.

    Parses FILE, computes hashes, and outputs metadata.
    Exit code 0 on success, 1 if unrecognised format, 2 on error.
    """
    exit_code = 0

    try:
        # Track command with telemetry (no file paths sent)
        with telemetry.track_command(
            "identify", {"format": output_format, "enrich": not no_enrich}
        ) as ctx:
            # Emit discrete feature events for funnel analysis
            telemetry.track_feature("identify", "format", output_format)
            if not no_enrich:
                telemetry.track_feature("identify", "enrich", "enabled")

            parsers: list[BaseModelParser] = [
                GGUFParser(),
                SafeTensorsParser(),
                ONNXParser(),
                PyTorchParser(),
            ]

            file_path = file.resolve()

            # Compute hash
            sha256 = _compute_sha256(file_path)

            # Try each parser based on extension
            matched_finding = None
            ext = file_path.suffix.lower()

            # Track extension for understanding coverage gaps
            known_extensions: set[str] = set()
            for parser in parsers:
                known_extensions.update(parser.extensions)

            if ext not in known_extensions:
                telemetry.track_feature(
                    "identify", "unknown_extension", ext[:10] if ext else "none"
                )

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
                # Emit model format event
                telemetry.track_feature("identify", "model_format", mi.format.lower())

            # Emit recognition result
            telemetry.track_feature("identify", "recognized", "yes" if info["recognized"] else "no")

            # KB lookup for model identification (enabled by default)
            if not no_enrich:
                from scanoss_ai_scanner.enrichment import KBEnricher

                enricher_path = kb_path
                if enricher_path is None:
                    enricher_path = Path("~/.scanoss-ai/kb/scanoss-ai.db").expanduser()

                kb_exists = enricher_path.exists()
                ctx["kb_available"] = kb_exists

                # Track KB availability
                if kb_exists:
                    telemetry.track_feature("identify", "kb_source", "local")
                else:
                    telemetry.track_feature("identify", "kb_source", "live_only")

                # Create enricher with telemetry callback and live fallback
                with KBEnricher(
                    db_path=enricher_path if kb_exists else None,
                    enable_live_fallback=True,
                    telemetry_callback=telemetry.track_event,
                ) as enricher:
                    model_data = enricher.lookup_model(file_path.name)
                    if model_data:
                        info["kb_match"] = True
                        info["known_model"] = model_data.purl
                        if model_data.license:
                            info["license"] = model_data.license
                        if model_data.organization:
                            info["organization"] = model_data.organization
                        if model_data.parameter_count and "parameter_count" not in info:
                            info["parameter_count"] = model_data.parameter_count
                        if model_data.architecture and "architecture" not in info:
                            info["architecture"] = model_data.architecture
                        if model_data.source_url:
                            info["source_url"] = model_data.source_url
                        if model_data.base_model_purl:
                            info["base_model"] = model_data.base_model_purl
                        # Emit KB match event
                        telemetry.track_feature("identify", "kb_match", "found")
                    else:
                        telemetry.track_feature("identify", "kb_match", "not_found")

            # Add anonymous metrics to telemetry
            ctx["recognized"] = info["recognized"]
            ctx["kb_match"] = info.get("kb_match", False)
            ctx["output_format"] = output_format
            if info.get("format"):
                ctx["model_format"] = info["format"]

            if output_format == "json":
                click.echo(json.dumps(info, indent=2))
            else:
                _print_text(info)

            # Set exit code (0=recognized, 1=unrecognized - both are successful runs)
            exit_code = 0 if info["recognized"] else 1

    except Exception as exc:
        # Telemetry already tracked the error via context manager
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    # Exit after telemetry context closes (so success is recorded correctly)
    # Note: exit_code 1 (unrecognized) is still a successful command execution
    if exit_code == 1:
        sys.exit(1)


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

    # KB match info
    if info.get("kb_match"):
        click.echo("--- KB Match ---")
        if info.get("known_model"):
            click.echo(f"Known Model: {info['known_model']}")
        if info.get("organization"):
            click.echo(f"Organization: {info['organization']}")
        if info.get("license"):
            click.echo(f"License:    {info['license']}")
        if info.get("source_url"):
            click.echo(f"Source:     {info['source_url']}")
        if info.get("base_model"):
            click.echo(f"Base Model: {info['base_model']}")
