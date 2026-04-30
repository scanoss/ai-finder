#!/usr/bin/env python3
"""Update version.json with SHA256 checksums of seed files.

Run this script after modifying any seed JSON files to update their checksums.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SEED_DIR = Path(__file__).parent.parent / "packages/ai-finder/src/ai_finder_kb/seed"

SEED_FILES = [
    "sdks.json",
    "models.json",
    "mcp_servers.json",
]


def compute_checksum(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> None:
    """Update version.json with current checksums."""
    version_path = SEED_DIR / "version.json"

    # Read current version.json
    with open(version_path) as f:
        version_data = json.load(f)

    # Compute checksums
    checksums = {}
    for filename in SEED_FILES:
        filepath = SEED_DIR / filename
        if filepath.exists():
            checksums[filename] = compute_checksum(filepath)
            print(f"  {filename}: {checksums[filename][:16]}...")
        else:
            print(f"  {filename}: NOT FOUND")

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
