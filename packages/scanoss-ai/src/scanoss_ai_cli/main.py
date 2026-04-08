"""SCANOSS AI CLI entry point."""

from __future__ import annotations

import atexit
import sys
from pathlib import Path

import click
from scanoss_ai_scanner.output import CycloneDXFormatter, JSONFormatter, SPDXFormatter
from scanoss_ai_scanner.scanner import Scanner

from scanoss_ai_cli import __version__
from scanoss_ai_cli.commands.identify import identify
from scanoss_ai_cli.commands.kb import kb
from scanoss_ai_cli import telemetry


@click.group()
@click.version_option(__version__, prog_name="scanoss-ai")
@click.option(
    "--no-telemetry",
    is_flag=True,
    help="Disable anonymous usage telemetry for this session.",
)
@click.pass_context
def main(ctx: click.Context, no_telemetry: bool) -> None:
    """SCANOSS AI - AI artifact scanner for supply chain security.

    \b
    Telemetry: This tool collects anonymous usage data to help improve
    the product. No file paths or scan targets are collected.
    Disable with --no-telemetry, SCANOSS_AI_TELEMETRY=0, or DO_NOT_TRACK=1.
    """
    if no_telemetry:
        telemetry.disable()
    else:
        telemetry.track_cli_started()
        atexit.register(telemetry.shutdown)


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
@click.option(
    "--relationships",
    "-r",
    is_flag=True,
    help="Include component relationships in SBOM (dependsOn/contains)",
)
def scan(
    path: Path,
    output_format: str,
    output: Path | None,
    quiet: bool,
    relationships: bool,
) -> None:
    """Scan a directory for AI artifacts.

    PATH is the directory to scan.
    """
    # Track command with telemetry (no file paths sent)
    with telemetry.track_command("scan", {"format": output_format, "quiet": quiet}) as ctx:
        scanner = Scanner()

        if not quiet:
            click.echo(f"Scanning {path}...", err=True)

        try:
            result = scanner.scan(path)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Add anonymous metrics to telemetry
        ctx["files_scanned"] = result.files_scanned
        ctx["findings_count"] = len(result.findings)

        if not quiet:
            click.echo(
                f"Scanned {result.files_scanned} files in {result.duration_ms}ms",
                err=True,
            )
            click.echo(f"Found {len(result.findings)} AI artifacts", err=True)

        # Build relationship graph if requested
        graph = None
        if relationships:
            if not quiet:
                click.echo("Building component relationships...", err=True)
            graph = scanner.build_relationship_graph(path)
            if not quiet:
                click.echo(
                    f"Found {len(graph.nodes)} components, {len(graph.edges)} relationships",
                    err=True,
                )

        # Format output
        formatted: str
        if output_format == "json":
            formatted = JSONFormatter(indent=2).format(result)
        elif output_format == "cyclonedx":
            formatted = CycloneDXFormatter().format(result, graph)
        elif output_format == "spdx":
            formatted = SPDXFormatter().format(result, graph)
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


# Register additional commands
main.add_command(identify)
main.add_command(kb)


if __name__ == "__main__":
    main()
