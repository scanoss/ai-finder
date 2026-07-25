#!/usr/bin/env python3
"""Verify a built seed.db actually contains what the seed JSONs describe.

The JSONs are the source of record in git; seed.db is the artifact shipped in the
wheel. They are never committed together, so nothing but this check stands between
"the release built a database" and "the release built the *right* database". A
wheel carrying an empty or truncated seed.db installs and runs perfectly happily,
it just silently fails to identify anything.

So counts are derived from the JSONs rather than hardcoded, and compared against
the database. Hardcoded expectations would drift the moment the corpus grows.

Usage:
    python scripts/verify_seed_db.py                      # verify the built seed.db
    python scripts/verify_seed_db.py --db PATH            # verify a specific database
    python scripts/verify_seed_db.py --expect-counts F    # compare against a saved manifest
    python scripts/verify_seed_db.py --write-counts F     # record counts for a later run

`--write-counts` then `--expect-counts` lets the release pipeline prove the
database inside the *installed wheel* matches the one built from the JSONs, at a
point where the JSONs are no longer around to compare against.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PKG = REPO_ROOT / "packages/ai-finder/src/ai_finder_kb"
SEED_DIR = PKG / "seed"
DEFAULT_DB = PKG / "data/seed.db"

# Smallest share of model_files.json rows that may be missing from the database
# before it counts as truncation rather than the expected handful of dropped rows.
MIN_MODEL_FILES_RATIO = 0.99

# seed JSON -> table it populates.
SEED_TABLES = {
    "sdks.json": "sdks",
    "models.json": "models",
    "model_files.json": "model_files",
    "mcp_servers.json": "mcp_servers",
}


def json_counts() -> dict[str, int]:
    """Row count per table according to the seed JSONs."""
    counts: dict[str, int] = {}
    for filename, table in SEED_TABLES.items():
        path = SEED_DIR / filename
        if not path.exists():
            continue
        counts[table] = len(json.loads(path.read_text()))
    return counts


def db_counts(db_path: Path) -> dict[str, int]:
    """Row count per table according to the database."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in SEED_TABLES.values()
        }
    finally:
        con.close()


def integrity_checks(db_path: Path) -> list[str]:
    """Structural problems that a row count alone would not catch."""
    problems: list[str] = []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        orphans = con.execute(
            "SELECT COUNT(*) FROM model_files f "
            "LEFT JOIN models m ON m.id = f.model_id WHERE m.id IS NULL"
        ).fetchone()[0]
        if orphans:
            problems.append(f"{orphans} model_files rows reference a missing model")

        bad = con.execute("SELECT COUNT(*) FROM model_files WHERE length(h) != 32").fetchone()[0]
        if bad:
            problems.append(f"{bad} model_files rows have a digest that is not 32 bytes")

        # The whole point of the table: a hash lookup has to resolve to a purl.
        row = con.execute(
            "SELECT m.purl FROM model_files f JOIN models m ON m.id = f.model_id LIMIT 1"
        ).fetchone()
        if not row or not row[0]:
            problems.append("no model_files row joins to a model purl")

        # kb_version must match the seed it was built from, or a fresh install
        # either re-downloads everything or downgrades itself from an older remote.
        version_file = SEED_DIR / "version.json"
        if version_file.exists():
            expected = int(json.loads(version_file.read_text()).get("version", 0))
            got = con.execute("SELECT value FROM sync_state WHERE key='kb_version'").fetchone()
            got_version = int(got[0]) if got and got[0] is not None else 0
            if got_version != expected:
                problems.append(
                    f"kb_version is {got_version}, expected {expected} from version.json"
                )
    finally:
        con.close()
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database to verify.")
    parser.add_argument(
        "--expect-counts",
        type=Path,
        default=None,
        help="Compare against counts previously saved with --write-counts, instead "
        "of against the seed JSONs. Use when the JSONs are not available, e.g. "
        "verifying the database inside an installed wheel.",
    )
    parser.add_argument(
        "--write-counts",
        type=Path,
        default=None,
        help="Write the verified counts to this file for a later --expect-counts run.",
    )
    args = parser.parse_args()

    if not args.db.exists():
        sys.exit(f"error: database not found: {args.db}")

    if args.expect_counts:
        if not args.expect_counts.exists():
            sys.exit(f"error: counts file not found: {args.expect_counts}")
        expected = json.loads(args.expect_counts.read_text())
        source = str(args.expect_counts)
    else:
        expected = json_counts()
        if not expected:
            sys.exit(f"error: no seed JSONs found under {SEED_DIR}")
        source = "seed JSONs"

    actual = db_counts(args.db)

    print(f"Verifying {args.db}")
    print(f"  expected from: {source}")
    problems: list[str] = []
    for table, want in sorted(expected.items()):
        got = actual.get(table, 0)
        if got == want:
            print(f"  {table:14} {got}")
            continue
        # Only model_files may legitimately come in under its JSON count, because
        # seed_model_files drops rows whose purl is not in models. That is rare
        # (currently zero), so allow a small shortfall and nothing more: a bare
        # "less than" would wave through a database truncated to a handful of rows.
        if table == "model_files" and want * MIN_MODEL_FILES_RATIO <= got < want:
            print(f"  {table:14} {got} of {want} (rows with unknown purls dropped)")
            continue
        problems.append(f"{table}: database has {got}, expected {want}")

    if not actual.get("models"):
        problems.append("models table is empty")
    if not actual.get("model_files"):
        problems.append("model_files table is empty, so no hash lookup can ever hit")

    problems.extend(integrity_checks(args.db))

    if problems:
        print("\nFAILED", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)

    print("  integrity      ok")

    if args.write_counts:
        args.write_counts.parent.mkdir(parents=True, exist_ok=True)
        args.write_counts.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        print(f"\nWrote counts to {args.write_counts}")

    print("\nOK")


if __name__ == "__main__":
    main()
