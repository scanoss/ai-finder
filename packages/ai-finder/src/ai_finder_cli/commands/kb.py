"""kb command group - knowledge base operations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from ai_finder_cli import telemetry


def _default_kb_path() -> Path:
    """Return the default KB database path, respecting AI_FINDER_KB_PATH env var."""
    env_path = os.environ.get("AI_FINDER_KB_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path("~/.ai-finder/kb/ai-finder.db").expanduser()


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards (% and _) in a string.

    Uses backslash as escape character - must be used with ESCAPE '\\'.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ensure_kb_exists(db_path: Path) -> bool:
    """Ensure KB exists, auto-initializing from seed if needed.

    Returns True if KB exists (or was created), False on error.
    """
    import shutil

    from ai_finder_kb import get_seed_db_path

    if db_path.exists():
        return True

    # Auto-initialize from seed
    seed_path = get_seed_db_path()
    if seed_path and seed_path.exists():
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(seed_path, db_path)
            click.echo(f"Knowledge base auto-initialized at {db_path}", err=True)
            return True
        except Exception as e:
            click.echo(f"Failed to initialize KB: {e}", err=True)
            return False

    click.echo(
        f"Knowledge base not found at {db_path} and no seed database available.",
        err=True,
    )
    return False


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
    help="Path to KB database (default: ~/.ai-finder/kb/ai-finder.db or AI_FINDER_KB_PATH)",
)
def init(kb_path: Path | None) -> None:
    """Initialize the local knowledge base database."""
    import shutil

    from ai_finder_kb import Database, get_seed_db_path

    with telemetry.track_command("kb.init"):
        db_path = kb_path if kb_path else _default_kb_path()

        try:
            # Create parent directory if needed
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy seed database if available, otherwise create empty
            seed_path = get_seed_db_path()
            if seed_path and seed_path.exists():
                shutil.copy(seed_path, db_path)
                click.echo(f"Knowledge base initialized from seed at {db_path}")
            else:
                with Database(db_path) as db:
                    db.initialize()
                click.echo(f"Knowledge base initialized (empty) at {db_path}")
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
    from ai_finder_kb import Database, KBSync

    with telemetry.track_command("kb.status", {"format": output_format}) as ctx:
        # Emit discrete feature events
        telemetry.track_feature("kb.status", "format", output_format)

        db_path = kb_path if kb_path else _default_kb_path()

        if not _ensure_kb_exists(db_path):
            telemetry.track_feature("kb.status", "db", "not_found")
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

                # Get sync state
                sync = KBSync(db)
                kb_version = sync.get_local_version()
                last_sync = sync.get_last_sync()

            stat_data = {
                "db_path": str(db_path),
                "schema_version": schema_version,
                "kb_version": kb_version,
                "last_sync": last_sync.isoformat() if last_sync else None,
                "table_counts": table_counts,
            }

            # Track KB stats (anonymous - no paths)
            ctx["schema_version"] = schema_version
            ctx["kb_version"] = kb_version
            ctx["total_entries"] = sum(table_counts.values())
            ctx["output_format"] = output_format

            # Emit discrete events for KB state
            total = sum(table_counts.values())
            if total == 0:
                telemetry.track_feature("kb.status", "entries", "empty")
            elif total < 100:
                telemetry.track_feature("kb.status", "entries", "small")
            elif total < 1000:
                telemetry.track_feature("kb.status", "entries", "medium")
            else:
                telemetry.track_feature("kb.status", "entries", "large")

            if output_format == "json":
                click.echo(json.dumps(stat_data, indent=2))
            else:
                click.echo(f"DB path:        {db_path}")
                click.echo(f"Schema version: {schema_version}")
                click.echo(f"KB version:     {kb_version}")
                if last_sync:
                    click.echo(f"Last sync:      {last_sync.isoformat()}")
                else:
                    click.echo("Last sync:      never")
                click.echo("Table counts:")
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
    from ai_finder_kb import Database

    # Validate PURL before entering telemetry context
    try:
        _parse_purl(purl)  # Validate format
    except ValueError as exc:
        click.echo(f"Invalid PURL: {exc}", err=True)
        sys.exit(2)

    db_path = kb_path if kb_path else _default_kb_path()

    if not _ensure_kb_exists(db_path):
        sys.exit(2)

    exit_code = 0
    results: list[dict[str, str | int | None]] = []

    try:
        # Track command (PURL is not a file path, but don't send it anyway for privacy)
        with telemetry.track_command("kb.lookup", {"format": output_format}) as ctx:
            # Emit discrete feature events
            telemetry.track_feature("kb.lookup", "format", output_format)

            with Database(db_path) as db:
                # Escape LIKE wildcards in purl to prevent SQL injection
                escaped_purl = _escape_like(purl)

                # Search SDKs
                cursor = db.execute(
                    "SELECT id, purl, category, license FROM sdks "
                    "WHERE purl = ? OR purl LIKE ? ESCAPE '\\'",
                    (purl, f"{escaped_purl}%"),
                )
                for row in cursor:
                    results.append({"type": "sdk", **dict(row)})

                # Search models
                cursor = db.execute(
                    "SELECT purl, name, organization, architecture, license "
                    "FROM models WHERE purl = ? OR purl LIKE ? ESCAPE '\\'",
                    (purl, f"{escaped_purl}%"),
                )
                for row in cursor:
                    results.append({"type": "model", **dict(row)})

                # Search packages
                try:
                    cursor = db.execute(
                        "SELECT purl, name, ecosystem, version, license, ai_category "
                        "FROM packages WHERE purl = ? OR purl LIKE ? ESCAPE '\\'",
                        (purl, f"{escaped_purl}%"),
                    )
                    for row in cursor:
                        results.append({"type": "package", **dict(row)})
                except Exception:
                    pass  # Table may not exist in older DBs

                # Search MCP servers
                try:
                    cursor = db.execute(
                        "SELECT id, purl, description FROM mcp_servers "
                        "WHERE purl = ? OR purl LIKE ? ESCAPE '\\'",
                        (purl, f"{escaped_purl}%"),
                    )
                    for row in cursor:
                        results.append({"type": "mcp_server", **dict(row)})
                except Exception:
                    pass  # Table may not exist in older DBs

            # Track result count (anonymous)
            ctx["results_count"] = len(results)

            # Emit discrete result events
            if not results:
                telemetry.track_feature("kb.lookup", "result", "not_found")
                click.echo(f"No results found for {purl}")
                exit_code = 1
            else:
                telemetry.track_feature("kb.lookup", "result", "found")
                # Track what types were found
                found_types = set(str(r["type"]) for r in results)
                for t in found_types:
                    telemetry.track_feature("kb.lookup", "found_type", t)

            if output_format == "json":
                click.echo(json.dumps(results, indent=2))
            else:
                for result in results:
                    click.echo(f"Type:    {result['type']}")
                    click.echo(f"PURL:    {result.get('purl', 'N/A')}")
                    if result.get("id"):
                        click.echo(f"ID:      {result['id']}")
                    if result.get("name"):
                        click.echo(f"Name:    {result['name']}")
                    if result.get("ecosystem"):
                        click.echo(f"Ecosystem: {result['ecosystem']}")
                    if result.get("version"):
                        click.echo(f"Version: {result['version']}")
                    if result.get("category") or result.get("ai_category"):
                        click.echo(
                            f"Category: {result.get('category') or result.get('ai_category')}"
                        )
                    if result.get("architecture"):
                        click.echo(f"Arch:    {result['architecture']}")
                    if result.get("description"):
                        click.echo(f"Desc:    {result['description']}")
                    if result.get("license"):
                        click.echo(f"License: {result['license']}")
                    click.echo("---")

    except Exception as exc:
        # Telemetry already tracked the error via context manager
        click.echo(f"Error looking up PURL: {exc}", err=True)
        sys.exit(2)

    # Exit after telemetry context closes (so success is recorded correctly)
    if exit_code != 0:
        sys.exit(exit_code)


@kb.command("crawl")
@click.argument("source", type=click.Choice(["huggingface", "pypi", "npm", "all"]))
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to KB database (default: ~/.ai-finder/kb/ai-finder.db)",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Maximum items to crawl (HuggingFace only).",
)
@click.option(
    "--token",
    default=None,
    envvar="HF_TOKEN",
    help="HuggingFace API token (or set HF_TOKEN env var).",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
def crawl(
    source: str,
    kb_path: Path | None,
    limit: int | None,
    token: str | None,
    verbose: bool,
) -> None:
    """Crawl external APIs to populate the knowledge base.

    SOURCE can be: huggingface, pypi, npm, or all.

    Examples:

        ai-finder kb crawl huggingface --limit 100

        ai-finder kb crawl pypi

        ai-finder kb crawl all
    """
    with telemetry.track_command("kb.crawl", {"source": source}) as ctx:
        # Emit discrete source event
        telemetry.track_feature("kb.crawl", "source", source)

        db_path = kb_path if kb_path else _default_kb_path()

        # Ensure DB exists (auto-init from seed if needed)
        if not db_path.exists():
            telemetry.track_feature("kb.crawl", "db_init", "created")
            if not _ensure_kb_exists(db_path):
                sys.exit(2)

        results = []
        total_items_added = 0
        total_errors = 0

        if source in ("huggingface", "all"):
            from ai_finder_kb.crawlers import HuggingFaceCrawler

            telemetry.track_feature("kb.crawl", "crawler", "huggingface")
            click.echo("Crawling HuggingFace Hub...")
            hf_crawler = HuggingFaceCrawler(db_path, verbose=verbose, token=token)
            hf_result = hf_crawler.crawl(limit=limit)
            results.append(f"HuggingFace: {hf_result.models_added} models")
            total_items_added += hf_result.models_added
            if hf_result.models_added > 0:
                telemetry.track_feature("kb.crawl.huggingface", "result", "success")
            if hf_result.errors:
                total_errors += len(hf_result.errors)
                telemetry.track_feature("kb.crawl.huggingface", "errors", "yes")
                click.echo(f"  Errors: {len(hf_result.errors)}", err=True)

        if source in ("pypi", "all"):
            from ai_finder_kb.crawlers import PyPICrawler

            telemetry.track_feature("kb.crawl", "crawler", "pypi")
            click.echo("Crawling PyPI...")
            pypi_crawler = PyPICrawler(db_path, verbose=verbose)
            pypi_result = pypi_crawler.crawl()
            results.append(f"PyPI: {pypi_result.packages_added} packages")
            if pypi_result.packages_added > 0:
                telemetry.track_feature("kb.crawl.pypi", "result", "success")
            total_items_added += pypi_result.packages_added
            if pypi_result.errors:
                total_errors += len(pypi_result.errors)
                telemetry.track_feature("kb.crawl.pypi", "errors", "yes")
                click.echo(f"  Errors: {len(pypi_result.errors)}", err=True)

        if source in ("npm", "all"):
            from ai_finder_kb.crawlers import NpmCrawler

            telemetry.track_feature("kb.crawl", "crawler", "npm")
            click.echo("Crawling npm...")
            npm_crawler = NpmCrawler(db_path, verbose=verbose)
            npm_result = npm_crawler.crawl()
            results.append(f"npm: {npm_result.packages_added} packages")
            total_items_added += npm_result.packages_added
            if npm_result.packages_added > 0:
                telemetry.track_feature("kb.crawl.npm", "result", "success")
            if npm_result.errors:
                total_errors += len(npm_result.errors)
                telemetry.track_feature("kb.crawl.npm", "errors", "yes")
                click.echo(f"  Errors: {len(npm_result.errors)}", err=True)

        # Track crawl metrics (anonymous)
        ctx["items_added"] = total_items_added
        ctx["error_count"] = total_errors

        # Emit overall result
        if total_items_added > 0:
            telemetry.track_feature("kb.crawl", "result", "success")
        else:
            telemetry.track_feature("kb.crawl", "result", "empty")
        if total_errors > 0:
            telemetry.track_feature("kb.crawl", "had_errors", "yes")

        click.echo("Crawl complete:")
        for r in results:
            click.echo(f"  {r}")


@kb.command("check-updates")
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to the knowledge base database.",
)
@click.option(
    "--remote-url",
    default=None,
    help="Custom URL for remote seed data.",
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
def check_updates(
    kb_path: Path | None, remote_url: str | None, output_format: str
) -> None:
    """Check if KB updates are available from the remote server."""
    from ai_finder_kb import Database, KBSync

    with telemetry.track_command("kb.check_updates", {"format": output_format}) as ctx:
        db_path = kb_path if kb_path else _default_kb_path()

        if not _ensure_kb_exists(db_path):
            sys.exit(2)

        try:
            with Database(db_path) as db:
                sync = KBSync(db, remote_url) if remote_url else KBSync(db)
                status = sync.check_for_updates()

            ctx["local_version"] = status.local_version
            ctx["remote_version"] = status.remote_version
            ctx["update_available"] = status.update_available

            if output_format == "json":
                result = {
                    "local_version": status.local_version,
                    "remote_version": status.remote_version,
                    "last_sync": status.last_sync.isoformat() if status.last_sync else None,
                    "update_available": status.update_available,
                    "error": status.error,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Local version:  {status.local_version}")
                remote = status.remote_version if status.remote_version is not None else "unknown"
                click.echo(f"Remote version: {remote}")
                if status.last_sync:
                    click.echo(f"Last sync:      {status.last_sync.isoformat()}")
                else:
                    click.echo("Last sync:      never")

                if status.error:
                    click.echo(f"Error:          {status.error}", err=True)
                elif status.update_available:
                    click.echo("\nUpdate available! Run 'ai-finder kb update' to sync.")
                else:
                    click.echo("\nKB is up to date.")

        except Exception as exc:
            click.echo(f"Error checking for updates: {exc}", err=True)
            sys.exit(2)


@kb.command("update")
@click.option(
    "--kb-path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to the knowledge base database.",
)
@click.option(
    "--remote-url",
    default=None,
    help="Custom URL for remote seed data.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force sync even if no update is available.",
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
def update(
    kb_path: Path | None,
    remote_url: str | None,
    force: bool,
    output_format: str,
) -> None:
    """Update the KB from the remote seed data server.

    This downloads the latest SDK patterns, model definitions, and MCP server
    entries from the remote server and updates the local knowledge base.

    Data with source='crawled' or source='user' will NOT be overwritten.
    Only data with source='seed' will be updated.
    """
    from ai_finder_kb import Database, KBSync

    with telemetry.track_command("kb.update", {"force": force, "format": output_format}) as ctx:
        telemetry.track_feature("kb.update", "force", "yes" if force else "no")

        db_path = kb_path if kb_path else _default_kb_path()

        if not _ensure_kb_exists(db_path):
            sys.exit(2)

        try:
            with Database(db_path) as db:
                sync = KBSync(db, remote_url) if remote_url else KBSync(db)

                if not force:
                    # Check for updates first
                    status = sync.check_for_updates()
                    if status.error:
                        click.echo(f"Error checking for updates: {status.error}", err=True)
                        sys.exit(2)
                    if not status.update_available:
                        if output_format == "json":
                            msg = {"success": True, "message": "Already up to date"}
                            click.echo(json.dumps(msg))
                        else:
                            click.echo("KB is already up to date.")
                        telemetry.track_feature("kb.update", "result", "already_up_to_date")
                        return

                if output_format != "json":
                    click.echo("Syncing KB from remote server...")
                result = sync.sync(force=force)

            ctx["success"] = result.success
            ctx["previous_version"] = result.previous_version
            ctx["new_version"] = result.new_version
            ctx["sdks_updated"] = result.sdks_updated
            ctx["models_updated"] = result.models_updated
            ctx["mcp_servers_updated"] = result.mcp_servers_updated

            if output_format == "json":
                output = {
                    "success": result.success,
                    "previous_version": result.previous_version,
                    "new_version": result.new_version,
                    "sdks_updated": result.sdks_updated,
                    "models_updated": result.models_updated,
                    "mcp_servers_updated": result.mcp_servers_updated,
                    "error": result.error,
                }
                click.echo(json.dumps(output, indent=2))
            else:
                if result.success:
                    click.echo("KB sync complete!")
                    click.echo(f"  Version: {result.previous_version} -> {result.new_version}")
                    click.echo(f"  SDKs updated: {result.sdks_updated}")
                    click.echo(f"  Models updated: {result.models_updated}")
                    click.echo(f"  MCP servers updated: {result.mcp_servers_updated}")
                    telemetry.track_feature("kb.update", "result", "success")
                else:
                    click.echo(f"Sync failed: {result.error}", err=True)
                    telemetry.track_feature("kb.update", "result", "failed")
                    sys.exit(2)

        except Exception as exc:
            click.echo(f"Error updating KB: {exc}", err=True)
            sys.exit(2)
