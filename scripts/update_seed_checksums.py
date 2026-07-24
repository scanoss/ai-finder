#!/usr/bin/env python3
"""Update version.json with SHA256 checksums of seed files.

Run this script after modifying any seed JSON files to update their checksums.
It also bumps `version`, which is what makes clients pick the change up: a stale
checksum/version makes every OTA client either fail the sync (checksum mismatch
-> rollback) or see "no update", so the new rows never ship.

With --verify it writes nothing and instead fails if version.json disagrees with
the seed files on disk. That is the drift gate: CI can prove the committed
checksums describe the committed JSONs without needing any secrets.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SEED_DIR = Path(__file__).parent.parent / "packages/ai-finder/src/ai_finder_kb/seed"

SEED_FILES = [
    "sdks.json",
    "models.json",
    "model_files.json",
    "mcp_servers.json",
]


def compute_checksum(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Chunked: model_files.json is ~25 MB and grows with the corpus.
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def current_checksums() -> dict:
    """Compute checksums for every seed file present on disk."""
    checksums = {}
    for filename in SEED_FILES:
        filepath = SEED_DIR / filename
        if filepath.exists():
            checksums[filename] = compute_checksum(filepath)
            print(f"  {filename}: {checksums[filename][:16]}...")
        else:
            print(f"  {filename}: NOT FOUND")
    return checksums


def verify(version_data: dict, checksums: dict) -> int:
    """Report whether version.json matches the seed files. Returns an exit code."""
    recorded = version_data.get("checksums") or {}
    problems = []

    for filename, digest in checksums.items():
        if filename not in recorded:
            problems.append(f"{filename}: present on disk but absent from version.json checksums")
        elif recorded[filename] != digest:
            problems.append(
                f"{filename}: version.json has {recorded[filename][:16]}..., "
                f"file is {digest[:16]}..."
            )
    for filename in recorded:
        if filename not in checksums:
            problems.append(f"{filename}: in version.json checksums but missing on disk")

    if problems:
        print("\nversion.json does not describe the seed files on disk:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nRun `python scripts/update_seed_checksums.py` (then "
            "`python scripts/create_seed_db.py`) and commit the seed JSONs together "
            "with version.json.",
            file=sys.stderr,
        )
        return 1

    print(f"\nversion.json is consistent (version {version_data.get('version')}).")
    return 0


def main() -> None:
    """Update or verify version.json checksums."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Do not write. Fail if version.json disagrees with the seed files.",
    )
    args = parser.parse_args()

    version_path = SEED_DIR / "version.json"

    # Read current version.json
    with open(version_path) as f:
        version_data = json.load(f)

    # Compute checksums
    checksums = current_checksums()

    if args.verify:
        sys.exit(verify(version_data, checksums))

    # Update version.json
    version_data["checksums"] = checksums
    version_data["version"] = version_data.get("version", 0) + 1
    version_data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Write updated version.json
    with open(version_path, "w") as f:
        json.dump(version_data, f, indent=2)
        f.write("\n")

    print(f"\nUpdated {version_path}")
    print(f"  Version: {version_data['version']}")
    print(f"  Updated: {version_data['updated_at']}")


if __name__ == "__main__":
    main()
