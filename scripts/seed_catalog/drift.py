"""Hold the other hardcoded package lists to the catalogue.

Before this tool there were four lists of AI packages in the tree, maintained by
hand and free to disagree: ``seed/sdks.json``, ``crawlers/npm.py``,
``crawlers/pypi.py`` and the ``AI_*`` frozensets in ``manifests/``. A fifth list
that merely *intends* to agree with four that already do not is no improvement,
so the generator owns the catalogue and this module makes the others answer to
it in the same run. A comment asking the next person to keep them in sync is not
a mechanism; a failing check is.

The two directions are deliberately different, because the lists mean different
things:

* **A crawler list is a subset.** It names packages to fetch live metadata for,
  so it may be shorter than the catalogue, but a name in it that the catalogue
  has never heard of is drift — nobody decided that package was an AI SDK.
* **A manifest list is a superset.** It flags any dependency worth reporting,
  including AI-adjacent ones like ``pillow`` that are not SDKs. So it may hold
  extra names, but every catalogued SDK for that ecosystem must be in it, or the
  scanner is blind to a package the seed says we detect.

Lists are read with :mod:`ast`, never imported and never regexed: importing
would execute the package, and a regex over source silently stops matching the
day someone reformats the literal.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Manifest module -> the purl ecosystem its entries belong to. A module with no
# ecosystem here (cocoapods) has no purl type in the catalogue and is skipped
# rather than guessed at.
MANIFEST_ECOSYSTEMS = {
    "cargo.py": "cargo",
    "composer.py": "composer",
    "gemfile.py": "gem",
    "gomod.py": "golang",
    "gradle.py": "maven",
    "maven.py": "maven",
    "npm.py": "npm",
    "nuget.py": "nuget",
    "python.py": "pypi",
    "swiftpm.py": "swift",
}


@dataclass
class Divergence:
    """One list's disagreement with the catalogue."""

    source: str
    ecosystem: str
    unknown_to_catalogue: list[str] = field(default_factory=list)
    missing_from_list: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.unknown_to_catalogue and not self.missing_from_list


def _module_literal(path: Path, name: str | None = None) -> list[str]:
    """Every string in a module-level list or frozenset literal, read without importing.

    With ``name`` the named assignment is read. Without it the module must hold
    exactly one ``frozenset(...)`` assignment; two would make "the AI list"
    ambiguous and that ambiguity is worth failing on.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    found: dict[str, ast.AST] = {}
    for node in tree.body:
        # AnnAssign as well as Assign: `AI_PACKAGES: frozenset[str] = frozenset(...)`
        # is a different node type, and reading only Assign would report the
        # list as absent the day someone adds the annotation.
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not isinstance(target, ast.Name) or value is None:
            continue
        if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "frozenset":
            found[target.id] = value.args[0] if value.args else ast.Set(elts=[])
        elif isinstance(value, (ast.List, ast.Set, ast.Tuple)):
            found[target.id] = value

    if name is not None:
        if name not in found:
            raise ValueError(f"{path}: no module-level literal named {name}")
        node = found[name]
    else:
        literals = {k: v for k, v in found.items() if k.startswith("AI_")}
        if len(literals) != 1:
            raise ValueError(f"{path}: expected exactly one AI_* literal, found {sorted(literals)}")
        node = next(iter(literals.values()))

    return [e.value for e in getattr(node, "elts", []) if isinstance(e, ast.Constant)]


def normalise(ecosystem: str, token: str) -> str:
    """One comparable spelling for a package, whichever list it came from.

    Maven and Gradle write ``group:artifact`` where a purl writes
    ``group/artifact``; Go module paths and Swift repositories carry a host and
    owner that the in-code lists sometimes drop. Comparison is case-insensitive
    because NuGet and Maven are, and the two lists do not agree on casing.
    """
    token = token.strip().lower()
    if ecosystem == "maven":
        return token.replace(":", "/")
    if ecosystem in {"golang", "swift"}:
        return token.removeprefix("github.com/")
    return token


def catalogue_names(candidates, ecosystem: str) -> set[str]:
    """Normalised catalogue names for one ecosystem, SDKs only.

    MCP servers are excluded: the crawler and manifest lists are about library
    dependencies, and an MCP server is a running process, not an import.
    """
    from .catalog import SDK
    from .registries import split_purl

    out = set()
    for candidate in candidates:
        if candidate.kind != SDK:
            continue
        eco, name = split_purl(candidate.purl)
        if eco == ecosystem:
            out.add(normalise(ecosystem, name))
    return out


def check_crawlers(candidates, crawlers_dir: Path) -> list[Divergence]:
    """Crawler lists must name only packages the catalogue knows."""
    results = []
    for filename, ecosystem in (("npm.py", "npm"), ("pypi.py", "pypi")):
        path = crawlers_dir / filename
        if not path.exists():
            continue
        listed = {normalise(ecosystem, t) for t in _module_literal(path, "AI_PACKAGES")}
        known = catalogue_names(candidates, ecosystem)
        results.append(
            Divergence(
                source=f"crawlers/{filename}",
                ecosystem=ecosystem,
                unknown_to_catalogue=sorted(listed - known),
            )
        )
    return results


def check_manifests(candidates, manifests_dir: Path) -> list[Divergence]:
    """Manifest lists must contain every catalogued SDK for their ecosystem."""
    results = []
    for filename, ecosystem in sorted(MANIFEST_ECOSYSTEMS.items()):
        path = manifests_dir / filename
        if not path.exists():
            continue
        listed = {normalise(ecosystem, t) for t in _module_literal(path)}
        known = catalogue_names(candidates, ecosystem)
        results.append(
            Divergence(
                source=f"manifests/{filename}",
                ecosystem=ecosystem,
                missing_from_list=sorted(known - listed),
            )
        )
    return results


def report(divergences: list[Divergence]) -> list[str]:
    """Human-readable lines for every list that disagrees; empty when all agree."""
    lines: list[str] = []
    for divergence in divergences:
        if divergence.clean:
            continue
        lines.append(f"{divergence.source} ({divergence.ecosystem}):")
        for name in divergence.unknown_to_catalogue:
            lines.append(f"    not in the catalogue: {name}")
        for name in divergence.missing_from_list:
            lines.append(f"    catalogued but not listed here: {name}")
    return lines
