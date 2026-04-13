"""AI Finder CLI entry point."""

from __future__ import annotations

import atexit
import sys
from pathlib import Path

import click
from ai_finder_scanner.output import (
    CycloneDXFormatter,
    JSONFormatter,
    SPDX23Formatter,
    SPDX3Formatter,
)
from ai_finder_scanner.scanner import Scanner

from ai_finder_cli import __version__, telemetry
from ai_finder_cli.commands.identify import identify
from ai_finder_cli.commands.kb import kb


@click.group()
@click.version_option(__version__, prog_name="ai-finder")
@click.option(
    "--no-telemetry",
    is_flag=True,
    help="Disable anonymous usage telemetry for this session.",
)
@click.pass_context
def main(ctx: click.Context, no_telemetry: bool) -> None:
    """AI Finder - AI artifact scanner for supply chain security.

    \b
    Telemetry: This tool collects anonymous usage data to help improve
    the product. No file paths or scan targets are collected.
    Disable with --no-telemetry, AI_FINDER_TELEMETRY=0, or DO_NOT_TRACK=1.
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
@click.option(
    "--no-enrich",
    is_flag=True,
    help="Disable automatic KB enrichment",
)
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    envvar="SCANOSS_KB_PATH",
    help="Path to KB database (default: ~/.ai-finder/kb/ai-finder.db)",
)
@click.option(
    "--spdx-version",
    type=click.Choice(["2.3", "3.0"]),
    default=None,
    help="SPDX version (required when format is 'spdx')",
)
@click.option(
    "--spdx-v2",
    "spdx_version_alias",
    is_flag=True,
    flag_value="2.3",
    default=None,
    help="Shortcut for --spdx-version 2.3",
)
@click.option(
    "--spdx-v3",
    "spdx_version_alias",
    is_flag=True,
    flag_value="3.0",
    help="Shortcut for --spdx-version 3.0",
)
def scan(
    path: Path,
    output_format: str,
    output: Path | None,
    quiet: bool,
    relationships: bool,
    no_enrich: bool,
    kb_path: Path | None,
    spdx_version: str | None,
    spdx_version_alias: str | None,
) -> None:
    """Scan a directory for AI artifacts.

    PATH is the directory to scan.
    """
    # Resolve spdx_version from alias if provided
    if spdx_version_alias and not spdx_version:
        spdx_version = spdx_version_alias

    # Validate spdx_version is provided when format is spdx
    if output_format == "spdx" and spdx_version is None:
        raise click.UsageError("SPDX format requires --spdx-version (2.3 or 3.0), or use --spdx-v2 / --spdx-v3")

    try:
        # Track command with telemetry (no file paths sent)
        with telemetry.track_command(
            "scan",
            {
                "format": output_format,
                "quiet": quiet,
                "enrich": not no_enrich,
                "relationships": relationships,
            },
        ) as ctx:
            # Emit discrete feature events for funnel analysis
            telemetry.track_feature("scan", "format", output_format)
            if not no_enrich:
                telemetry.track_feature("scan", "enrich", "enabled")
            if relationships:
                telemetry.track_feature("scan", "relationships", "enabled")

            scanner = Scanner()

            if not quiet:
                click.echo(f"Scanning {path}...", err=True)

            # Progress callback for large codebases
            progress_bar = None

            def progress_callback(current: int, total: int, phase: str) -> None:
                nonlocal progress_bar
                if quiet:
                    return
                if progress_bar is None and total > 100:
                    # Only show progress bar for larger scans
                    progress_bar = click.progressbar(
                        length=total,
                        label="Scanning",
                        file=sys.stderr,
                        show_pos=True,
                    )
                    progress_bar.__enter__()
                if progress_bar is not None:
                    progress_bar.update(1)

            try:
                result = scanner.scan(
                    path,
                    progress_callback=progress_callback,
                    telemetry_callback=telemetry.track_event,
                )
            finally:
                # Ensure progress bar is cleaned up even on error
                if progress_bar is not None:
                    progress_bar.__exit__(None, None, None)
                    click.echo("", err=True)  # Newline after progress bar

            # Add anonymous metrics to telemetry
            ctx["files_scanned"] = result.files_scanned
            ctx["findings_count"] = len(result.findings)
            ctx["output_format"] = output_format

            # Emit findings count bucket for funnel analysis
            if len(result.findings) == 0:
                telemetry.track_feature("scan", "findings", "none")
            elif len(result.findings) <= 10:
                telemetry.track_feature("scan", "findings", "few")
            else:
                telemetry.track_feature("scan", "findings", "many")

            if not quiet:
                click.echo(
                    f"Scanned {result.files_scanned} files in {result.duration_ms}ms",
                    err=True,
                )
                click.echo(f"Found {len(result.findings)} AI artifacts", err=True)

            # Track artifact types found for dataset improvement
            model_count = sum(1 for f in result.findings if f.model_info)
            sdk_count = sum(1 for f in result.findings if f.sdk_usage)
            manifest_count = sum(1 for f in result.findings if f.manifest_dep)
            ctx["model_count"] = model_count
            ctx["sdk_count"] = sdk_count
            ctx["manifest_count"] = manifest_count

            if model_count > 0:
                telemetry.track_feature("scan", "artifact_type", "model")
            if sdk_count > 0:
                telemetry.track_feature("scan", "artifact_type", "sdk")
            if manifest_count > 0:
                telemetry.track_feature("scan", "artifact_type", "manifest")

            # Build relationship graph if requested
            graph = None
            if relationships:
                if not quiet:
                    click.echo("Building component relationships...", err=True)
                try:
                    graph = scanner.build_relationship_graph(path)
                    ctx["graph_nodes"] = len(graph.nodes)
                    ctx["graph_edges"] = len(graph.edges)
                    telemetry.track_feature("scan", "graph_built", "success")
                    if not quiet:
                        nodes = len(graph.nodes)
                        edges = len(graph.edges)
                        click.echo(f"Found {nodes} components, {edges} relationships", err=True)
                except Exception as e:
                    # Tree-sitter not available (Python < 3.10)
                    error_str = str(e).lower()
                    if "tree-sitter" in error_str or "tree_sitter" in error_str or "3.10" in str(e):
                        click.echo(
                            f"Warning: --relationships requires Python 3.10+ ({e}). "
                            "Skipping relationship analysis.",
                            err=True,
                        )
                        telemetry.track_feature("scan", "graph_built", "unavailable")
                    else:
                        raise

            # Format output with optional KB enrichment
            def format_output(enricher=None):
                if output_format == "json":
                    return JSONFormatter(indent=2).format(result)
                elif output_format == "cyclonedx":
                    return CycloneDXFormatter().format(result, graph, enricher)
                elif output_format == "spdx":
                    if spdx_version == "2.3":
                        return SPDX23Formatter().format(result, graph, enricher)
                    else:  # 3.0
                        return SPDX3Formatter().format(result, graph, enricher)
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
                            sdk = finding.sdk_usage
                            lines.append(f"  SDK: {sdk.sdk} ({finding.file_path}:{finding.line})")
                        elif finding.manifest_dep:
                            lines.append(
                                f"  Dep: {finding.manifest_dep.name} ({finding.file_path})"
                            )
                        elif finding.model_info:
                            lines.append(
                                f"  Model: {finding.file_path} ({finding.model_info.format})"
                            )
                    return "\n".join(lines)

            # Setup KB enricher (enabled by default)
            if not no_enrich:
                from ai_finder_scanner.enrichment import KBEnricher

                enricher_path = kb_path
                if enricher_path is None:
                    enricher_path = Path("~/.ai-finder/kb/ai-finder.db").expanduser()

                # Auto-initialize KB from seed if not present
                if not enricher_path.exists():
                    from ai_finder_cli.commands.kb import _ensure_kb_exists

                    _ensure_kb_exists(enricher_path)

                kb_exists = enricher_path.exists()
                ctx["kb_available"] = kb_exists

                # Track KB availability for understanding dataset coverage
                if kb_exists:
                    telemetry.track_feature("scan", "kb_source", "local")
                else:
                    telemetry.track_feature("scan", "kb_source", "live_only")

                if not quiet:
                    click.echo("Enriching with KB metadata...", err=True)

                # Track enrichment phase start
                telemetry.track_event(
                    "scan.enrichment.started",
                    {
                        "kb_available": kb_exists,
                        "findings_to_enrich": len(result.findings),
                    },
                )

                # Use proper context manager for enricher
                with KBEnricher(
                    db_path=enricher_path if kb_exists else None,
                    enable_live_fallback=True,
                    telemetry_callback=telemetry.track_event,
                ) as enricher:
                    # Track output generation phase
                    telemetry.track_event("scan.output.started", {"format": output_format})
                    formatted = format_output(enricher)
                    telemetry.track_event("scan.output.completed", {"format": output_format})

                # Track enrichment phase completed
                telemetry.track_event(
                    "scan.enrichment.completed",
                    {
                        "kb_available": kb_exists,
                    },
                )
            else:
                # Track output generation phase (no enrichment)
                telemetry.track_event("scan.output.started", {"format": output_format})
                formatted = format_output()
                telemetry.track_event("scan.output.completed", {"format": output_format})

            # Output result
            if output:
                output.write_text(formatted)
                if not quiet:
                    click.echo(f"Output written to {output}", err=True)
            else:
                click.echo(formatted)

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# Register additional commands
main.add_command(identify)
main.add_command(kb)


if __name__ == "__main__":
    main()
