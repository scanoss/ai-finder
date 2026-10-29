#!/usr/bin/env python3
"""Refresh the seed catalogue from the package registries.

    python -m scripts.seed_catalog.refresh                 # look up and report, write nothing
    python -m scripts.seed_catalog.refresh --write         # also rewrite the seed JSONs
    python -m scripts.seed_catalog.refresh --offline       # validate and check drift, no network
    python -m scripts.seed_catalog.refresh --check         # CI: fail on anything material

What ``--check`` fails on, and what it deliberately does not: a package the
registry has dropped, a licence that changed under us, a candidate pool that no
longer validates, and any of the other package lists disagreeing with the
catalogue. It does **not** fail on rank movement. Download counts move every
day, so a check that failed on reordering would be red most mornings and would
be switched off within a week, taking the useful half with it.

After ``--write``, ``scripts/update_seed_checksums.py`` has to run: it bumps the
seed version and records the new checksums, and without it every client either
rejects the download or never notices there is one. The release pipeline already
fails if that step is skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # running the file directly rather than as a module
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.seed_catalog"

from .catalog import (  # noqa: E402
    MCP_SERVER,
    SDK,
    Verified,
    load_candidates,
    previous_rows,
    select,
    to_seed_rows,
    verify,
)
from .drift import check_crawlers, check_manifests  # noqa: E402
from .drift import report as drift_report
from .registries import POPULARITY_SIGNAL, Fetcher, RegistryFacts, lookup, stars  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG = REPO_ROOT / "packages/ai-finder/src"
SEED_DIR = PKG / "ai_finder_kb/seed"
CRAWLERS_DIR = PKG / "ai_finder_kb/crawlers"
MANIFESTS_DIR = PKG / "ai_finder_scanner/manifests"

# Ecosystems whose registry publishes no popularity signal, where a GitHub star
# count is the only way to order them at all. Asked for only here, so a package
# that already has real downloads never spends a request on stars.
STAR_RANKED = {"maven", "golang", "swift", "github"}


def collect(candidates, fetch, seed_dir: Path, verbose: bool = False) -> list[Verified]:
    """Look up every candidate and pair it with its committed row."""
    previous = previous_rows(seed_dir)
    entries: list[Verified] = []
    for candidate in candidates:
        try:
            facts = lookup(candidate.purl, fetch)
        except ValueError as exc:  # a malformed purl that validation let through
            facts = RegistryFacts(error=str(exc))

        star_count = None
        if facts.usable and facts.exists and facts.downloads is None:
            repo = facts.repository
            if repo and candidate.ecosystem in STAR_RANKED:
                star_count = stars(repo, fetch)

        previous_row = previous.get(f"{candidate.kind}:{candidate.id}")
        entry = verify(candidate, facts, previous_row, star_count)
        entries.append(entry)
        if verbose:
            state = "gone" if entry.gone else ("unverified" if not facts.usable else "ok")
            print(f"  {candidate.purl:55} {state}")
    return entries


def summarise(entries: list[Verified], kept: list[Verified], cut: list[Verified]) -> dict:
    """The machine-readable report, and the source of every line printed below."""
    kept_ids = {id(e) for e in kept}
    return {
        "counts": {
            "candidates": len(entries),
            "kept": len(kept),
            "below_the_limit": len(cut),
            "gone": sum(1 for e in entries if e.gone),
            "unverified": sum(1 for e in entries if not e.facts.usable),
        },
        "popularity_signal": {
            ecosystem: POPULARITY_SIGNAL[ecosystem]
            for ecosystem in sorted({e.candidate.ecosystem for e in entries})
        },
        "gone": [e.candidate.purl for e in entries if e.gone],
        "unverified": [
            {"purl": e.candidate.purl, "reason": e.facts.error}
            for e in entries
            if not e.facts.usable
        ],
        "licence_changes": [
            {"purl": e.candidate.purl, "note": note}
            for e in entries
            for note in e.notes
            if note.startswith("licence changed")
        ],
        "deprecated": [
            {"purl": e.candidate.purl, "note": note}
            for e in entries
            for note in e.notes
            if "deployed code" in note
        ],
        "below_the_limit": [
            {"purl": e.candidate.purl, "rank_basis": e.rank_basis, "rank_value": e.rank_value}
            for e in cut
        ],
        # Keyed by kind and ecosystem, because the limit applies to each pair:
        # "pypi 55" against a limit of 50 reads as a breach when it is 50 SDKs
        # plus 5 MCP servers.
        "kept_by_group": _group_counts(
            f"{e.candidate.kind}/{e.candidate.ecosystem}" for e in entries if id(e) in kept_ids
        ),
    }


def _group_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def print_report(summary: dict, divergences: list, limit: int) -> None:
    counts = summary["counts"]
    print(
        f"\ncandidates {counts['candidates']}, kept {counts['kept']} "
        f"(limit {limit} per kind and ecosystem)"
    )
    print("  kept: " + ", ".join(f"{k} {v}" for k, v in summary["kept_by_group"].items()))
    print("\nranked on:")
    for ecosystem, signal in summary["popularity_signal"].items():
        print(f"  {ecosystem:10} {signal}")

    for heading, key in (
        ("dropped: the registry no longer has these", "gone"),
        ("not verified; the committed row stands", "unverified"),
        ("licence changed since the committed row", "licence_changes"),
        ("deprecated upstream, kept for detection", "deprecated"),
        ("below the per-ecosystem limit, not written", "below_the_limit"),
    ):
        rows = summary[key]
        if not rows:
            continue
        print(f"\n{heading} ({len(rows)}):")
        for row in rows:
            print(f"  {row if isinstance(row, str) else json.dumps(row)}")

    lines = drift_report(divergences)
    print("\nother package lists:")
    if lines:
        for line in lines:
            print(f"  {line}")
    else:
        print("  every list agrees with the catalogue")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--write", action="store_true", help="Rewrite the seed JSONs from the result."
    )
    parser.add_argument(
        "--offline", action="store_true", help="Validate and check drift only; no network."
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on anything material.")
    parser.add_argument("--report", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds between registry calls.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    candidates, limit = load_candidates()
    divergences = check_crawlers(candidates, CRAWLERS_DIR)
    divergences += check_manifests(candidates, MANIFESTS_DIR)

    if args.offline:
        lines = drift_report(divergences)
        print(f"{len(candidates)} candidates validate.")
        if lines:
            print("\n".join(f"  {line}" for line in lines))
        else:
            print("Every list agrees with the catalogue.")
        sys.exit(1 if (lines and args.check) else 0)

    fetch = Fetcher(delay=args.delay)
    entries = collect(candidates, fetch, args.seed_dir, verbose=args.verbose)
    kept, cut = select(entries, limit)
    summary = summarise(entries, kept, cut)
    print_report(summary, divergences, limit)

    if args.report:
        args.report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(f"\nreport written to {args.report}")

    if args.write:
        for filename, kind in (("sdks.json", SDK), ("mcp_servers.json", MCP_SERVER)):
            path = args.seed_dir / filename
            rows = to_seed_rows(kept, kind)
            path.write_text(json.dumps(rows, indent=2) + "\n")
            print(f"wrote {len(rows)} rows to {path}")
        print("\nREQUIRED NEXT STEP: python scripts/update_seed_checksums.py")
        print("Without it the seed version and checksums do not describe these files,")
        print("and every client either rejects the sync or never sees it.")

    if args.check:
        material = (
            summary["gone"] or summary["licence_changes"] or [d for d in divergences if not d.clean]
        )
        if material:
            print("\nFAILED: see the sections above.", file=sys.stderr)
            sys.exit(1)
        print("\nOK: nothing material changed. Rank movement alone is not a failure.")


if __name__ == "__main__":
    main()
