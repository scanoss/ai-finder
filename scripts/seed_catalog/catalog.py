"""The curated candidate pool, and the seed rows it produces once verified.

The pool is the source of record: a human adds or removes a candidate, and every
run checks that candidate against its registry and re-ranks it. Nothing is
discovered automatically, because these rows decide what appears in a customer's
AI bill of materials and a registry search for "ai" returns a great deal that is
not an AI SDK.

Three rules the ranking depends on, each one a decision rather than an accident:

* **A dead package is dropped, a deprecated one is kept.** Deprecation is a
  statement about what people *should* depend on; detection is about what they
  *do* depend on, and deprecated packages are exactly the ones still sitting in
  old manifests. Only a package the registry no longer has at all leaves.
* **An unverifiable package keeps its committed row.** A lookup that failed is
  not evidence about the package, so the previous licence and position stand and
  the report names it. The alternative silently shrinks detection whenever a
  registry has a bad morning.
* **Rank is per ecosystem and the signal is named.** Downloads are not
  comparable across registries and some publish none, so each ecosystem is
  ranked only against itself and the report states what it ranked on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registries import (
    AMBIGUOUS_LICENSE,
    POPULARITY_SIGNAL,
    RegistryFacts,
    is_spdx_like,
    normalise_license,
    split_purl,
)

HERE = Path(__file__).parent
CANDIDATES_PATH = HERE / "candidates.json"

SDK = "sdk"
MCP_SERVER = "mcp_server"
KINDS = (SDK, MCP_SERVER)

# The vocabulary already in seed/sdks.json. A new value is a deliberate addition,
# not a typo, so the loader refuses anything outside it.
SDK_CATEGORIES = frozenset(
    {
        "agent-framework",
        "ai-safety",
        "llm-client",
        "mcp",
        "ml-framework",
        "ml-runtime",
        "observability",
        "speech-audio",
        "vector-database",
    }
)

DEFAULT_PER_ECOSYSTEM_LIMIT = 50


@dataclass(frozen=True)
class Candidate:
    """One curated entry, before any registry has been asked about it."""

    id: str
    kind: str
    purl: str
    patterns: tuple[str, ...]
    category: str | None = None
    description: str | None = None
    priority: int = 100

    @property
    def ecosystem(self) -> str:
        return split_purl(self.purl)[0]


@dataclass
class Verified:
    """A candidate plus what its registry said, and how it was ranked."""

    candidate: Candidate
    facts: RegistryFacts
    license: str | None = None
    rank_value: int | None = None
    rank_basis: str = "curated order"
    notes: list[str] = field(default_factory=list)
    was_committed: bool = False

    @property
    def gone(self) -> bool:
        """The registry answered and does not have this package."""
        return self.facts.usable and not self.facts.exists

    @property
    def holds_its_place(self) -> bool:
        """An already-shipped row whose lookup failed, which the limit may not cut.

        Without this the rule "an unverifiable package keeps its committed row"
        holds only until an ecosystem fills its quota. An unranked entry sorts
        after every ranked one, so the first timeout at a full limit would drop
        a package that has been shipping for months — the exact silent
        shrinkage the error/absence distinction exists to prevent.
        """
        return self.was_committed and not self.facts.usable


def load_candidates(path: Path = CANDIDATES_PATH) -> tuple[list[Candidate], int]:
    """Read and validate the pool, returning the candidates and the per-ecosystem limit."""
    document = json.loads(path.read_text())
    limit = int(document.get("per_ecosystem_limit", DEFAULT_PER_ECOSYSTEM_LIMIT))
    candidates: list[Candidate] = []
    seen: set[str] = set()

    for index, raw in enumerate(document.get("entries", [])):
        where = f"entry {index} ({raw.get('id', 'no id')!r})"
        kind = raw.get("kind")
        if kind not in KINDS:
            raise ValueError(f"{where}: kind must be one of {KINDS}, got {kind!r}")
        identifier = raw.get("id")
        if not identifier:
            raise ValueError(f"{where}: missing id")
        key = f"{kind}:{identifier}"
        if key in seen:
            raise ValueError(f"{where}: duplicate id for kind {kind}")
        seen.add(key)

        # Two ids pointing at one package rank it twice and write it twice. The
        # committed seed already carried ai.onnxruntime/onnxruntime under two
        # ids, and the duplicate only surfaced because it was reported missing
        # twice in the same run.
        purl_key = f"{kind}:{raw.get('purl')}"
        if purl_key in seen:
            raise ValueError(f"{where}: duplicate purl {raw.get('purl')!r} for kind {kind}")
        seen.add(purl_key)

        purl = raw.get("purl") or ""
        ecosystem, _ = split_purl(purl)  # raises on a malformed purl
        if ecosystem not in POPULARITY_SIGNAL:
            raise ValueError(f"{where}: unknown ecosystem {ecosystem!r}")
        # The committed seed spelled two of its seven scoped npm purls with %40
        # and the other five with @, so the same package had two identities and
        # anything matching on the purl string saw two packages. One spelling,
        # enforced, rather than normalised quietly where nobody would see it.
        if "%40" in purl:
            raise ValueError(
                f"{where}: write the npm scope as '@', not '%40' ({purl}); "
                "mixed spellings make one package look like two"
            )

        patterns = tuple(raw.get("patterns") or ())
        if not patterns:
            raise ValueError(f"{where}: at least one pattern is required")
        if any(not isinstance(p, str) or not p.strip() for p in patterns):
            raise ValueError(f"{where}: patterns must be non-empty strings")

        category = raw.get("category")
        if kind == SDK:
            if category not in SDK_CATEGORIES:
                raise ValueError(
                    f"{where}: category {category!r} is not in {sorted(SDK_CATEGORIES)}"
                )
        elif category is not None:
            raise ValueError(f"{where}: category applies to SDKs only")

        candidates.append(
            Candidate(
                id=identifier,
                kind=kind,
                purl=purl,
                patterns=patterns,
                category=category,
                description=raw.get("description"),
                priority=int(raw.get("priority", 100)),
            )
        )

    return candidates, limit


def previous_rows(seed_dir: Path) -> dict[str, dict[str, Any]]:
    """The committed seed rows by ``kind:id``, used as the fallback for a failed lookup."""
    out: dict[str, dict[str, Any]] = {}
    for filename, kind in (("sdks.json", SDK), ("mcp_servers.json", MCP_SERVER)):
        path = seed_dir / filename
        if not path.exists():
            continue
        for row in json.loads(path.read_text()):
            out[f"{kind}:{row['id']}"] = row
    return out


def rank_key(entry: Verified) -> tuple[int, int, int, str]:
    """Sort key within one ecosystem: a measured signal first, then curated order.

    Entries with no signal are not interleaved with entries that have one — they
    sort after all of them. A missing count is not a count of zero, and ordering
    them together would read as "less popular than" when it means "not measured".
    """
    has_signal = 0 if entry.rank_value is not None else 1
    return (has_signal, -(entry.rank_value or 0), entry.candidate.priority, entry.candidate.id)


def select(entries: list[Verified], limit: int) -> tuple[list[Verified], list[Verified]]:
    """Split verified entries into those that make the per-ecosystem cut and those that do not."""
    kept: list[Verified] = []
    cut: list[Verified] = []
    by_group: dict[tuple[str, str], list[Verified]] = {}
    for entry in entries:
        if entry.gone:
            continue
        by_group.setdefault((entry.candidate.kind, entry.candidate.ecosystem), []).append(entry)

    for group in by_group.values():
        group.sort(key=rank_key)
        held = [e for e in group if e.holds_its_place]
        rankable = [e for e in group if not e.holds_its_place]
        kept.extend(held)
        kept.extend(rankable[:limit])
        cut.extend(rankable[limit:])
    return kept, cut


def to_seed_rows(entries: list[Verified], kind: str) -> list[dict[str, Any]]:
    """The seed JSON rows for one kind, in the shape ``seed.py`` already reads.

    Sorted by id rather than by rank: the file is a set of rows the database
    loads, and a stable order keeps the diff between two runs readable instead of
    reshuffling 150 lines whenever a download count moves.
    """
    rows: list[dict[str, Any]] = []
    for entry in sorted(
        (e for e in entries if e.candidate.kind == kind), key=lambda e: e.candidate.id
    ):
        candidate = entry.candidate
        row: dict[str, Any] = {
            "id": candidate.id,
            "purl": candidate.purl,
            "patterns": list(candidate.patterns),
        }
        if kind == SDK:
            row["category"] = candidate.category
            row["license"] = entry.license
        else:
            row["description"] = candidate.description
        rows.append(row)
    return rows


def verify(
    candidate: Candidate,
    facts: RegistryFacts,
    previous: dict[str, Any] | None,
    star_count: int | None = None,
) -> Verified:
    """Combine a candidate with its registry answer into a ranked, annotated row."""
    entry = Verified(candidate=candidate, facts=facts, was_committed=previous is not None)
    previous_license = (previous or {}).get("license")

    if not facts.usable:
        entry.notes.append(f"not verified ({facts.error}); keeping the committed row")
        entry.license = previous_license
    elif not facts.exists:
        entry.notes.append("the registry no longer has this package")
        entry.license = previous_license
    else:
        published = normalise_license(facts.license)
        if published and published.startswith(AMBIGUOUS_LICENSE):
            # Keep whatever is committed and say so. Writing either operator
            # would publish an obligation the registry never stated.
            entry.license = previous_license
            entry.notes.append(f"{published}; keeping {previous_license or 'no licence'}")
            published = None
        # A registry answer only replaces a committed SPDX id when it is itself
        # an identifier. Registries publish "SEE LICENSE IN LICENSE", "Apache
        # 2.0" and "non-standard" in this field, and writing any of those over
        # "Apache-2.0" would make the seed worse on every run while looking like
        # an update.
        if published and not is_spdx_like(published) and is_spdx_like(previous_license):
            entry.license = previous_license
            entry.notes.append(
                f"registry publishes a non-SPDX licence ({published}); keeping {previous_license}"
            )
        else:
            entry.license = published or previous_license
            if published and previous_license and published != previous_license:
                entry.notes.append(f"licence changed: {previous_license} -> {published}")
        if entry.license is None:
            entry.notes.append("no licence published and none committed")
        if facts.deprecated:
            reason = facts.deprecation_reason or "deprecated"
            entry.notes.append(f"{reason}; kept, because deprecated code is still deployed code")

    if facts.downloads is not None:
        entry.rank_value = facts.downloads
        entry.rank_basis = POPULARITY_SIGNAL.get(candidate.ecosystem, "registry signal")
    elif star_count is not None:
        entry.rank_value = star_count
        entry.rank_basis = "GitHub stars"

    return entry
