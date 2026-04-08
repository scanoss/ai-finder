"""kb command group - knowledge base operations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click


def _default_kb_path() -> Path:
    """Return the default KB database path, respecting SCANOSS_KB_PATH env var."""
    env_path = os.environ.get("SCANOSS_KB_PATH")
    if env_path:
        return Path(env_path)
    return Path("~/.scanoss-ai/kb/scanoss-ai.db").expanduser()


def _parse_purl(purl: str) -> dict[str, str | None]:
    """Parse a Package URL (PURL) into components.

    Args:
        purl: PURL string like pkg:pypi/openai@1.0.0

    Returns:
        Dict with type, namespace, name, version keys.

    Raises:
        ValueError: If PURL is invalid.
    """
    if not purl.startswith("pkg:"):
        raise ValueError("PURL must start with 'pkg:'")

    rest = purl[4:]  # Remove 'pkg:' prefix

    # Split type from remainder
    if "/" not in rest:
        raise ValueError("PURL must have format pkg:<type>/<name>")

    type_part, name_part = rest.split("/", 1)

    # Handle version
    version = None
    if "@" in name_part:
        name_part, version = name_part.rsplit("@", 1)

    # Handle namespace (for types like npm, maven)
    namespace = None
    if "/" in name_part:
        namespace, name_part = name_part.rsplit("/", 1)

    return {
        "type": type_part,
        "namespace": namespace,
        "name": name_part,
        "version": version,
    }


@click.group()
def kb() -> None:
    """Knowledge base operations."""
    pass


@kb.command("init")
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to KB database (default: ~/.scanoss-ai/kb/scanoss-ai.db or SCANOSS_KB_PATH)",
)
def init(kb_path: Path | None) -> None:
    """Initialize the local knowledge base database."""
    from scanoss_ai_kb import Database

    db_path = kb_path if kb_path else _default_kb_path()

    try:
        # Create parent directory if needed
        db_path.parent.mkdir(parents=True, exist_ok=True)

        with Database(db_path) as db:
            db.initialize()
        click.echo(f"Knowledge base initialized at {db_path}")
    except Exception as exc:
        click.echo(f"Error initializing KB: {exc}", err=True)
        sys.exit(2)


@kb.command("status")
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to the knowledge base database.",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def status(kb_path: Path | None, output_format: str) -> None:
    """Show statistics about the knowledge base."""
    from scanoss_ai_kb import Database

    db_path = kb_path if kb_path else _default_kb_path()

    if not db_path.exists():
        click.echo(
            f"Knowledge base not found at {db_path}. Run 'scanoss-ai kb init' first.",
            err=True,
        )
        sys.exit(2)

    try:
        with Database(db_path) as db:
            schema_version = db.get_version()

            # Count rows per known table
            table_counts: dict[str, int] = {}
            for table in ("sdks", "models", "mcp_servers"):
                try:
                    cursor = db.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                    row = cursor.fetchone()
                    table_counts[table] = row[0] if row else 0
                except Exception:
                    table_counts[table] = 0

        stat_data = {
            "db_path": str(db_path),
            "schema_version": schema_version,
            "table_counts": table_counts,
        }

        if output_format == "json":
            click.echo(json.dumps(stat_data, indent=2))
        else:
            click.echo(f"DB path:        {db_path}")
            click.echo(f"Schema version: {schema_version}")
            for table, count in table_counts.items():
                click.echo(f"  {table}: {count} row(s)")

    except Exception as exc:
        click.echo(f"Error reading KB status: {exc}", err=True)
        sys.exit(2)


@kb.command("lookup")
@click.argument("purl")
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to the knowledge base database.",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def lookup(purl: str, kb_path: Path | None, output_format: str) -> None:
    """Look up a model or package by PURL.

    PURL should be in the format: pkg:<type>/<namespace>/<name>@<version>
    """
    from scanoss_ai_kb import Database

    # Validate PURL
    try:
        _parse_purl(purl)  # Validate format
    except ValueError as exc:
        click.echo(f"Invalid PURL: {exc}", err=True)
        sys.exit(2)

    db_path = kb_path if kb_path else _default_kb_path()

    if not db_path.exists():
        click.echo(
            f"Knowledge base not found at {db_path}. Run 'scanoss-ai kb init' first.",
            err=True,
        )
        sys.exit(2)

    try:
        with Database(db_path) as db:
            # Search in multiple tables
            results: list[dict[str, str | int | None]] = []

            # Search SDKs
            cursor = db.execute(
                "SELECT id, purl, category, license FROM sdks WHERE purl = ? OR purl LIKE ?",
                (purl, f"{purl}%"),
            )
            for row in cursor:
                results.append({"type": "sdk", **dict(row)})

            # Search models
            cursor = db.execute(
                "SELECT purl, name, organization, architecture, license "
                "FROM models WHERE purl = ? OR purl LIKE ?",
                (purl, f"{purl}%"),
            )
            for row in cursor:
                results.append({"type": "model", **dict(row)})

        if not results:
            click.echo(f"No results found for {purl}")
            sys.exit(1)

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            for result in results:
                click.echo(f"Type:    {result['type']}")
                click.echo(f"PURL:    {result.get('purl', 'N/A')}")
                if result.get("name"):
                    click.echo(f"Name:    {result['name']}")
                if result.get("category"):
                    click.echo(f"Category: {result['category']}")
                if result.get("architecture"):
                    click.echo(f"Arch:    {result['architecture']}")
                if result.get("license"):
                    click.echo(f"License: {result['license']}")
                click.echo("---")

    except Exception as exc:
        click.echo(f"Error looking up PURL: {exc}", err=True)
        sys.exit(2)
