"""SCANOSS AI CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from scanoss_ai_scanner.output import CycloneDXFormatter, JSONFormatter, SPDXFormatter
from scanoss_ai_scanner.scanner import Scanner

VERSION = "0.1.0"


@click.group()
@click.version_option(VERSION, prog_name="scanoss-ai")
def main() -> None:
    """SCANOSS AI - AI artifact scanner for supply chain security."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["json", "cyclonedx", "spdx", "text"]),
    default="text",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file (default: stdout)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output",
)
def scan(
    path: Path,
    output_format: str,
    output: Path | None,
    quiet: bool,
) -> None:
    """Scan a directory for AI artifacts.

    PATH is the directory to scan.
    """
    scanner = Scanner()

    if not quiet:
        click.echo(f"Scanning {path}...", err=True)

    try:
        result = scanner.scan(path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not quiet:
        click.echo(
            f"Scanned {result.files_scanned} files in {result.duration_ms}ms",
            err=True,
        )
        click.echo(f"Found {len(result.findings)} AI artifacts", err=True)

    # Format output
    formatted: str
    if output_format == "json":
        formatted = JSONFormatter(indent=2).format(result)
    elif output_format == "cyclonedx":
        formatted = CycloneDXFormatter().format(result)
    elif output_format == "spdx":
        formatted = SPDXFormatter().format(result)
    else:
        # Text format - simple summary
        lines = [
            "SCANOSS AI Scan Results",
            "=======================",
            f"Path: {result.root_path}",
            f"Files scanned: {result.files_scanned}",
            f"Duration: {result.duration_ms}ms",
            f"Findings: {len(result.findings)}",
            "",
        ]
        for finding in result.findings:
            if finding.sdk_usage:
                lines.append(f"  SDK: {finding.sdk_usage.sdk} ({finding.file_path}:{finding.line})")
            elif finding.manifest_dep:
                lines.append(f"  Dep: {finding.manifest_dep.name} ({finding.file_path})")
            elif finding.model_info:
                lines.append(f"  Model: {finding.file_path} ({finding.model_info.format})")
        formatted = "\n".join(lines)

    # Output result
    if output:
        output.write_text(formatted)
        if not quiet:
            click.echo(f"Output written to {output}", err=True)
    else:
        click.echo(formatted)


if __name__ == "__main__":
    main()
