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
                (purl, name, organization, architecture, parameter_count, license, source)
                VALUES (?, ?, ?, ?, ?, ?, 'seed')
                """,
                (
                    model["purl"],
                    model["name"],
                    model.get("organization"),
                    model.get("architecture"),
                    model.get("parameter_count"),
                    model.get("license"),
                ),
            )
            count += 1
        except Exception as e:
            print(f"Warning: Failed to insert model {model['name']}: {e}")

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
        "models": seed_models(db),
        "mcp_servers": seed_mcp_servers(db),
    }
    db.commit()
    return counts


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
