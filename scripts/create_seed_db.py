#!/usr/bin/env python3
"""Create seed database with essential AI SDK patterns."""

import sys
from pathlib import Path

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/ai-finder-kb/src"))

from ai_finder_kb.database import Database
from ai_finder_kb.seed import seed_database

SEED_DB_PATH = Path(__file__).parent.parent / "packages/ai-finder-kb/src/ai_finder_kb/data/seed.db"


def main() -> None:
    """Create seed database."""
    print(f"Creating seed database at {SEED_DB_PATH}")

    # Remove existing seed.db if it exists
    if SEED_DB_PATH.exists():
        SEED_DB_PATH.unlink()

    with Database(SEED_DB_PATH) as db:
        db.initialize()
        counts = seed_database(db)

        print("Seed database created successfully!")
        for name, count in counts.items():
            print(f"  - {name}: {count}")


if __name__ == "__main__":
    main()
