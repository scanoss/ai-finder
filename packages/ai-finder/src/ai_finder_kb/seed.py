"""Seed data for AI Finder Knowledge Base."""

import json
from pathlib import Path

from .database import Database

# Seed data directory
SEED_DIR = Path(__file__).parent / "seed"


def load_seed_data(filename: str) -> list[dict]:
    """Load seed data from a JSON file.

    Args:
        filename: Name of the JSON file in the seed directory.

    Returns:
        List of dictionaries from the JSON file.
    """
    seed_file = SEED_DIR / filename
    if not seed_file.exists():
        return []
    with open(seed_file) as f:
        return json.load(f)


def seed_sdks(db: Database) -> int:
    """Seed the database with SDK patterns.

    Args:
        db: Database instance (must be connected and initialized).

    Returns:
        Number of SDKs inserted.
    """
    sdks = load_seed_data("sdks.json")
    count = 0
    for sdk in sdks:
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO sdks (id, purl, patterns, category, license, source)
                VALUES (?, ?, ?, ?, ?, 'seed')
                """,
                (
                    sdk["id"],
                    sdk["purl"],
                    json.dumps(sdk["patterns"]),
                    sdk.get("category"),
                    sdk.get("license"),
                ),
            )
            count += 1
        except Exception as e:
            print(f"Warning: Failed to insert SDK {sdk['id']}: {e}")

    return count


def seed_models(db: Database) -> int:
    """Seed the database with model data.

    Args:
        db: Database instance (must be connected and initialized).

    Returns:
        Number of models inserted.
    """
    models = load_seed_data("models.json")
    count = 0
    for model in models:
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO models
                (purl, name, organization, architecture, architecture_family,
                 parameter_count, license, format, quantization, task,
                 base_model_purl, source_url, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed')
                """,
                (
                    model["purl"],
                    model["name"],
                    model.get("organization"),
                    model.get("architecture"),
                    model.get("architecture_family"),
                    model.get("parameter_count"),
                    model.get("license"),
                    model.get("format"),
                    model.get("quantization"),
                    model.get("task"),
                    model.get("base_model_purl"),
                    model.get("source_url"),
                ),
            )
            count += 1
        except Exception as e:
            print(f"Warning: Failed to insert model {model['name']}: {e}")

    return count


def seed_model_files(db: Database) -> int:
    """Seed the database with file-level model hashes.

    Rows are keyed to `models` by purl, so this must run after `seed_models()`.
    A row whose purl is not in `models` is skipped: the FK would reject it, and it
    could never be resolved to a purl/license anyway.

    Args:
        db: Database instance (must be connected and initialized).

    Returns:
        Number of file hashes inserted.
    """
    model_files = load_seed_data("model_files.json")
    if not model_files:
        return 0

    # One query instead of ~100k correlated lookups: the seed carries ~20k purls
    # across ~100k rows, so resolving purl -> id per row would dominate the build.
    model_ids = {
        row["purl"]: row["id"] for row in db.execute("SELECT id, purl FROM models").fetchall()
    }

    count = 0
    skipped = 0
    for entry in model_files:
        model_id = model_ids.get(entry.get("purl"))
        if model_id is None:
            skipped += 1
            continue
        try:
            digest = bytes.fromhex(entry["sha256"])
        except (KeyError, ValueError, TypeError):
            # TypeError covers a null or numeric sha256. model_files.json is
            # machine-generated, so one bad row must skip rather than abort the
            # whole build. Matches _sync_model_files, which already catches it.
            skipped += 1
            continue
        if len(digest) != 32:
            skipped += 1
            continue
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO model_files (h, model_id, path, size_bytes)
                VALUES (?, ?, ?, ?)
                """,
                (digest, model_id, entry.get("path"), entry.get("size_bytes")),
            )
            count += 1
        except Exception as e:
            print(f"Warning: Failed to insert model file {entry.get('path')}: {e}")

    if skipped:
        print(f"  note: {skipped} model_files rows skipped (unknown purl or bad digest)")
    return count


def seed_mcp_servers(db: Database) -> int:
    """Seed the database with MCP server data.

    Args:
        db: Database instance (must be connected and initialized).

    Returns:
        Number of MCP servers inserted.
    """
    mcp_servers = load_seed_data("mcp_servers.json")
    count = 0
    for mcp in mcp_servers:
        try:
            db.execute(
                """
                INSERT OR REPLACE INTO mcp_servers (id, purl, patterns, description, source)
                VALUES (?, ?, ?, ?, 'seed')
                """,
                (
                    mcp["id"],
                    mcp["purl"],
                    json.dumps(mcp["patterns"]),
                    mcp.get("description"),
                ),
            )
            count += 1
        except Exception as e:
            print(f"Warning: Failed to insert MCP server {mcp['id']}: {e}")

    return count


def seed_database(db: Database) -> dict[str, int]:
    """Seed the database with all seed data.

    Args:
        db: Database instance (must be connected and initialized).

    Returns:
        Dictionary with counts of inserted items per type.
    """
    counts = {
        "sdks": seed_sdks(db),
        # model_files rows are keyed to models by purl, so order matters here.
        "models": seed_models(db),
        "model_files": seed_model_files(db),
        "mcp_servers": seed_mcp_servers(db),
    }
    stamp_seed_version(db)
    db.commit()
    return counts


def stamp_seed_version(db: Database) -> int:
    """Record the seed's own version in sync_state, returning what was stamped.

    Without this a freshly seeded database claims kb_version 0 while holding the
    content of whatever version.json shipped with it. Two consequences, both bad:

    * `kb update` re-downloads every artifact on first run for data the client
      already has, currently ~33 MB.
    * Worse, if the remote is *older* than the bundled seed (normal right after a
      release, since the remote only moves when a seed sync lands), 0 < remote
      still reads as "update available" and the sync overwrites the newer bundled
      rows with the remote's staler ones, nulling columns the old artifact does
      not carry.

    Returns 0 and leaves sync_state alone when version.json is missing or
    unreadable, which keeps a hand-built database working.
    """
    version_file = SEED_DIR / "version.json"
    try:
        with open(version_file) as f:
            version = int(json.load(f).get("version", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        print(f"Warning: could not read seed version from {version_file}: {e}")
        return 0

    if version <= 0:
        return 0

    db.execute(
        "INSERT OR REPLACE INTO sync_state (key, value, updated_at) "
        "VALUES ('kb_version', ?, datetime('now'))",
        (str(version),),
    )
    return version


def create_seed_db(output_path: Path) -> None:
    """Create a seeded database file.

    Args:
        output_path: Path to write the database file.
    """
    with Database(output_path) as db:
        db.initialize()
        counts = seed_database(db)
        print(f"Seeded database at {output_path}:")
        for name, count in counts.items():
            print(f"  - {name}: {count}")


if __name__ == "__main__":
    # When run directly, create seed.db in the data directory
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    create_seed_db(data_dir / "seed.db")
