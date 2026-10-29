"""The check that stops a fifth package list joining four that already disagree.

Each test states the clean case alongside the dirty one. A drift check that
only ever reports problems is indistinguishable from one that reports
everything, and a drift check that never reports is indistinguishable from one
that is not running — which is how the four lists got out of step in the first
place.
"""

from __future__ import annotations

import pytest

from scripts.seed_catalog.catalog import SDK, Candidate
from scripts.seed_catalog.drift import (
    MANIFEST_ECOSYSTEMS,
    _module_literal,
    catalogue_names,
    check_crawlers,
    check_manifests,
    normalise,
    report,
)


def sdk(identifier: str, purl: str) -> Candidate:
    return Candidate(
        id=identifier, kind=SDK, purl=purl, patterns=(identifier,), category="llm-client"
    )


@pytest.fixture
def pool():
    return [sdk("openai", "pkg:pypi/openai"), sdk("anthropic", "pkg:pypi/anthropic")]


def write_crawler(directory, filename, names):
    directory.mkdir(parents=True, exist_ok=True)
    body = "AI_PACKAGES = [\n" + "".join(f'    "{n}",\n' for n in names) + "]\n"
    (directory / filename).write_text(body)


def write_manifest(directory, filename, names, constant="AI_PACKAGES"):
    directory.mkdir(parents=True, exist_ok=True)
    members = "".join(f'        "{n}",\n' for n in names)
    body = f"{constant} = frozenset(\n    {{\n{members}    }}\n)\n"
    (directory / filename).write_text(body)


# -------------------------------------------------------------------------------------------
# crawler lists: a subset of the catalogue
# -------------------------------------------------------------------------------------------


def test_a_crawler_naming_a_package_the_catalogue_never_heard_of_is_drift(tmp_path, pool):
    write_crawler(tmp_path, "pypi.py", ["openai", "some-random-package"])
    (divergence,) = check_crawlers(pool, tmp_path)
    assert divergence.unknown_to_catalogue == ["some-random-package"]
    assert not divergence.clean


def test_a_crawler_shorter_than_the_catalogue_is_clean(tmp_path, pool):
    """The negative control: a crawler list is allowed to be a subset."""
    write_crawler(tmp_path, "pypi.py", ["openai"])
    (divergence,) = check_crawlers(pool, tmp_path)
    assert divergence.clean
    assert report([divergence]) == []


# -------------------------------------------------------------------------------------------
# manifest lists: a superset of the catalogue
# -------------------------------------------------------------------------------------------


def test_a_manifest_missing_a_catalogued_sdk_is_drift(tmp_path, pool):
    write_manifest(tmp_path, "python.py", ["openai", "pillow"])
    divergences = [d for d in check_manifests(pool, tmp_path) if d.source.endswith("python.py")]
    assert divergences[0].missing_from_list == ["anthropic"]


def test_a_manifest_carrying_extra_ai_adjacent_names_is_clean(tmp_path, pool):
    """The negative control: extras like pillow are the manifest's job, not drift."""
    write_manifest(tmp_path, "python.py", ["openai", "anthropic", "pillow", "opencv-python"])
    divergences = [d for d in check_manifests(pool, tmp_path) if d.source.endswith("python.py")]
    assert divergences[0].clean


def test_mcp_servers_are_not_required_in_the_dependency_lists():
    """An MCP server is a process, not an import, so it is out of this comparison."""
    pool = [
        Candidate(
            id="mcp-git",
            kind="mcp_server",
            purl="pkg:pypi/mcp-server-git",
            patterns=("mcp-server-git",),
            description="x",
        )
    ]
    assert catalogue_names(pool, "pypi") == set()


# -------------------------------------------------------------------------------------------
# reading the literals
# -------------------------------------------------------------------------------------------


def test_a_module_with_two_ai_literals_is_refused_rather_than_guessed(tmp_path):
    (tmp_path / "ambiguous.py").write_text(
        'AI_PACKAGES = frozenset({"a"})\nAI_EXTRAS = frozenset({"b"})\n'
    )
    with pytest.raises(ValueError, match="exactly one"):
        _module_literal(tmp_path / "ambiguous.py")


def test_the_literal_is_read_without_importing_the_module(tmp_path):
    """A module that would explode on import must still be readable."""
    (tmp_path / "boom.py").write_text(
        'raise SystemExit("do not import me")\nAI_PACKAGES = frozenset({"openai"})\n'
    )
    assert _module_literal(tmp_path / "boom.py") == ["openai"]


@pytest.mark.parametrize(
    ("ecosystem", "token", "expected"),
    [
        ("maven", "dev.langchain4j:langchain4j", "dev.langchain4j/langchain4j"),
        ("maven", "dev.langchain4j/langchain4j", "dev.langchain4j/langchain4j"),
        ("golang", "github.com/tmc/langchaingo", "tmc/langchaingo"),
        ("swift", "github.com/anthropics/anthropic-swift", "anthropics/anthropic-swift"),
        ("nuget", "Microsoft.SemanticKernel", "microsoft.semantickernel"),
        ("pypi", "  OpenAI  ", "openai"),
    ],
)
def test_names_normalise_to_one_spelling_across_the_lists(ecosystem, token, expected):
    assert normalise(ecosystem, token) == expected


# -------------------------------------------------------------------------------------------
# against the real tree
# -------------------------------------------------------------------------------------------


def test_every_mapped_manifest_module_exists_in_the_package():
    from scripts.seed_catalog.refresh import MANIFESTS_DIR

    missing = [name for name in MANIFEST_ECOSYSTEMS if not (MANIFESTS_DIR / name).exists()]
    assert missing == [], f"the drift map names modules that are not there: {missing}"


def test_every_real_manifest_literal_parses():
    """Proves the reader works on the tree as it is, not only on fixtures."""
    from scripts.seed_catalog.refresh import MANIFESTS_DIR

    for name in MANIFEST_ECOSYSTEMS:
        path = MANIFESTS_DIR / name
        if path.exists():
            assert _module_literal(path), f"{name} parsed to an empty list"


def test_an_annotated_assignment_is_still_read(tmp_path):
    """`AI_PACKAGES: frozenset[str] = frozenset(...)` is an AnnAssign, not an Assign."""
    (tmp_path / "annotated.py").write_text(
        'AI_PACKAGES: frozenset[str] = frozenset({"openai", "anthropic"})\n'
    )
    assert sorted(_module_literal(tmp_path / "annotated.py")) == ["anthropic", "openai"]
