"""The rules that decide what reaches the seed, and the ones that keep it there.

Every test here pairs its assertion with the opposite case, because the
dangerous failures in this generator are all silent: a row quietly dropped on a
timeout, an unranked package quietly sorted as unpopular, a limit quietly
applied across ecosystems instead of within one. A test that only proves the
happy path cannot tell any of those apart from correct behaviour.
"""

from __future__ import annotations

import json

import pytest

from scripts.seed_catalog.catalog import (
    MCP_SERVER,
    SDK,
    Candidate,
    load_candidates,
    rank_key,
    select,
    to_seed_rows,
    verify,
)
from scripts.seed_catalog.registries import RegistryFacts, split_purl


def sdk(identifier: str, purl: str, priority: int = 100) -> Candidate:
    return Candidate(
        id=identifier,
        kind=SDK,
        purl=purl,
        patterns=(identifier,),
        category="llm-client",
        priority=priority,
    )


# -------------------------------------------------------------------------------------------
# purl shapes
# -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:pypi/langchain", ("pypi", "langchain")),
        ("pkg:npm/@anthropic-ai/sdk", ("npm", "@anthropic-ai/sdk")),
        ("pkg:maven/dev.langchain4j/langchain4j", ("maven", "dev.langchain4j/langchain4j")),
        ("pkg:golang/github.com/tmc/langchaingo", ("golang", "github.com/tmc/langchaingo")),
        ("pkg:pypi/langchain@0.1.0", ("pypi", "langchain")),
    ],
)
def test_split_purl_keeps_every_segment_after_the_ecosystem(purl, expected):
    assert split_purl(purl) == expected


def test_split_purl_rejects_a_purl_with_no_name():
    with pytest.raises(ValueError):
        split_purl("pkg:pypi")


# -------------------------------------------------------------------------------------------
# a failed lookup is not a missing package
# -------------------------------------------------------------------------------------------


def test_a_failed_lookup_keeps_the_row_and_its_committed_licence():
    entry = verify(
        sdk("openai", "pkg:pypi/openai"),
        RegistryFacts(error="TimeoutError: timed out"),
        previous={"id": "openai", "license": "Apache-2.0"},
    )
    assert not entry.gone, "a timeout must never read as a deleted package"
    assert entry.license == "Apache-2.0"
    assert any("not verified" in note for note in entry.notes)


def test_a_404_does_drop_the_row():
    """The negative control for the test above: a real absence must still drop."""
    entry = verify(
        sdk("ghost", "pkg:pypi/ghost"),
        RegistryFacts(exists=False),
        previous={"id": "ghost", "license": "MIT"},
    )
    assert entry.gone
    kept, _ = select([entry], limit=50)
    assert kept == []


def test_a_deprecated_package_is_kept_because_deployed_code_still_imports_it():
    entry = verify(
        sdk("server-slack", "pkg:npm/@modelcontextprotocol/server-slack"),
        RegistryFacts(
            deprecated=True,
            deprecation_reason="Package no longer supported",
            license="MIT",
            downloads=374_561,
        ),
        previous=None,
    )
    assert not entry.gone
    kept, _ = select([entry], limit=50)
    assert [e.candidate.id for e in kept] == ["server-slack"]
    assert any("deployed code" in note for note in entry.notes)


def test_a_licence_change_is_reported_and_the_registry_wins():
    entry = verify(
        sdk("thing", "pkg:pypi/thing"),
        RegistryFacts(license="Apache-2.0"),
        previous={"id": "thing", "license": "MIT"},
    )
    assert entry.license == "Apache-2.0"
    assert any(note.startswith("licence changed: MIT -> Apache-2.0") for note in entry.notes)


# -------------------------------------------------------------------------------------------
# ranking
# -------------------------------------------------------------------------------------------


def test_an_unranked_package_sorts_after_every_ranked_one_rather_than_as_zero():
    ranked = verify(sdk("ranked", "pkg:pypi/ranked"), RegistryFacts(downloads=1), None)
    unranked = verify(sdk("unranked", "pkg:pypi/unranked"), RegistryFacts(), None)
    assert rank_key(ranked) < rank_key(unranked)
    # And the point of it: one download must still outrank "not measured".
    assert ranked.rank_value == 1 and unranked.rank_value is None


def test_the_limit_applies_within_an_ecosystem_not_across_all_of_them():
    entries = [
        verify(sdk(f"py{i}", f"pkg:pypi/py{i}"), RegistryFacts(downloads=100 - i), None)
        for i in range(3)
    ] + [
        verify(sdk(f"js{i}", f"pkg:npm/js{i}"), RegistryFacts(downloads=100 - i), None)
        for i in range(3)
    ]
    kept, cut = select(entries, limit=2)
    kept_ids = sorted(e.candidate.id for e in kept)
    assert kept_ids == ["js0", "js1", "py0", "py1"], "two per ecosystem, not two overall"
    assert sorted(e.candidate.id for e in cut) == ["js2", "py2"]


def test_the_most_downloaded_entry_wins_its_ecosystem():
    low = verify(sdk("low", "pkg:pypi/low"), RegistryFacts(downloads=5), None)
    high = verify(sdk("high", "pkg:pypi/high"), RegistryFacts(downloads=5000), None)
    kept, _ = select([low, high], limit=1)
    assert [e.candidate.id for e in kept] == ["high"]


# -------------------------------------------------------------------------------------------
# the emitted rows
# -------------------------------------------------------------------------------------------


def test_sdk_rows_match_the_shape_seed_py_reads():
    entry = verify(sdk("openai", "pkg:pypi/openai"), RegistryFacts(license="Apache-2.0"), None)
    (row,) = to_seed_rows([entry], SDK)
    assert row == {
        "id": "openai",
        "purl": "pkg:pypi/openai",
        "patterns": ["openai"],
        "category": "llm-client",
        "license": "Apache-2.0",
    }


def test_mcp_rows_carry_a_description_and_no_licence_field():
    candidate = Candidate(
        id="mcp-git",
        kind=MCP_SERVER,
        purl="pkg:pypi/mcp-server-git",
        patterns=("mcp-server-git",),
        description="MCP server for Git",
    )
    entry = verify(candidate, RegistryFacts(license="MIT"), None)
    (row,) = to_seed_rows([entry], MCP_SERVER)
    assert set(row) == {"id", "purl", "patterns", "description"}
    assert row["description"] == "MCP server for Git"


def test_rows_are_ordered_by_id_so_a_rank_change_does_not_reshuffle_the_file():
    entries = [
        verify(sdk("zeta", "pkg:pypi/zeta"), RegistryFacts(downloads=9999), None),
        verify(sdk("alpha", "pkg:pypi/alpha"), RegistryFacts(downloads=1), None),
    ]
    assert [row["id"] for row in to_seed_rows(entries, SDK)] == ["alpha", "zeta"]


# -------------------------------------------------------------------------------------------
# the committed pool
# -------------------------------------------------------------------------------------------


def test_the_committed_candidate_pool_validates():
    candidates, limit = load_candidates()
    # The limit ranks; it must not cut a curated row. Every package that verifies
    # is a package a customer may depend on, and a cap at 50 dropped real ones
    # (mcp-agent, guardrails-ai) from detection to make room.
    groups: dict[tuple[str, str], int] = {}
    for c in candidates:
        groups[(c.kind, c.ecosystem)] = groups.get((c.kind, c.ecosystem), 0) + 1
    assert limit >= max(groups.values())
    assert len(candidates) > 150
    assert {c.kind for c in candidates} == {SDK, MCP_SERVER}


def test_the_committed_pool_has_no_duplicate_ids_within_a_kind():
    candidates, _ = load_candidates()
    keys = [f"{c.kind}:{c.id}" for c in candidates]
    assert len(keys) == len(set(keys))


def test_a_pool_entry_with_an_unknown_category_is_refused(tmp_path):
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "x",
                        "kind": "sdk",
                        "purl": "pkg:pypi/x",
                        "patterns": ["x"],
                        "category": "not-a-category",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="category"):
        load_candidates(path)


def test_a_pool_entry_with_no_patterns_is_refused(tmp_path):
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "x",
                        "kind": "sdk",
                        "purl": "pkg:pypi/x",
                        "patterns": [],
                        "category": "llm-client",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="pattern"):
        load_candidates(path)


def test_a_percent_encoded_npm_scope_is_refused(tmp_path):
    """Two of the committed seed's seven scoped npm purls used %40 and five used @.

    One package with two spellings is two packages to anything matching on the
    purl string, so the pool refuses the ambiguity rather than papering over it.
    """
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "qdrant",
                        "kind": "sdk",
                        "purl": "pkg:npm/%40qdrant/js-client-rest",
                        "patterns": ["@qdrant/js-client-rest"],
                        "category": "vector-database",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="%40"):
        load_candidates(path)


def test_the_committed_pool_spells_every_npm_scope_the_same_way():
    candidates, _ = load_candidates()
    assert [c.purl for c in candidates if "%40" in c.purl] == []


def test_two_ids_for_one_package_are_refused(tmp_path):
    """The seed carried four Maven artifacts twice, under a Java and a Kotlin id.

    Same purl, same patterns: the database keys on id, so both rows survived and
    one package matched twice.
    """
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "tensorflow-java",
                        "kind": "sdk",
                        "purl": "pkg:maven/org.tensorflow/tensorflow",
                        "patterns": ["org.tensorflow"],
                        "category": "ml-framework",
                    },
                    {
                        "id": "tensorflow-kotlin",
                        "kind": "sdk",
                        "purl": "pkg:maven/org.tensorflow/tensorflow",
                        "patterns": ["org.tensorflow"],
                        "category": "ml-framework",
                    },
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="duplicate purl"):
        load_candidates(path)


def test_the_committed_pool_has_no_duplicate_purls():
    candidates, _ = load_candidates()
    keys = [f"{c.kind}:{c.purl}" for c in candidates]
    assert len(keys) == len(set(keys))


def test_a_non_spdx_registry_answer_does_not_overwrite_a_committed_spdx_id():
    """npm really publishes "SEE LICENSE IN LICENSE"; the seed must not take it."""
    entry = verify(
        sdk("weaviate", "pkg:npm/weaviate-ts-client"),
        RegistryFacts(license="SEE LICENSE IN LICENSE"),
        previous={"id": "weaviate", "license": "BSD-3-Clause"},
    )
    assert entry.license == "BSD-3-Clause"
    assert any("non-SPDX" in note for note in entry.notes)


def test_a_real_spdx_change_is_still_taken():
    """The negative control: the rule above must not freeze every licence."""
    entry = verify(
        sdk("anthropic", "pkg:pypi/anthropic"),
        RegistryFacts(license="Apache-2.0"),
        previous={"id": "anthropic", "license": "MIT"},
    )
    assert entry.license == "Apache-2.0"
    assert any("licence changed: MIT -> Apache-2.0" in note for note in entry.notes)


def test_cargos_slash_form_is_read_as_an_spdx_or():
    entry = verify(
        sdk("tch", "pkg:cargo/tch"),
        RegistryFacts(license="MIT/Apache-2.0"),
        previous={"id": "tch", "license": "Apache-2.0"},
    )
    assert entry.license == "MIT OR Apache-2.0"


def test_a_non_spdx_answer_is_still_used_when_nothing_better_is_committed():
    entry = verify(sdk("thing", "pkg:cargo/thing"), RegistryFacts(license="Apache 2.0"), None)
    assert entry.license == "Apache 2.0"


def test_a_full_ecosystem_does_not_cut_a_committed_package_whose_lookup_failed():
    """The rule "an unverifiable package keeps its committed row" must hold at the limit.

    An unranked entry sorts after every ranked one, so without this the first
    timeout in a full ecosystem drops a package that has shipped for months.
    """
    ranked = [
        verify(sdk(f"py{i}", f"pkg:pypi/py{i}"), RegistryFacts(downloads=100 - i), None)
        for i in range(2)
    ]
    stranded = verify(
        sdk("committed", "pkg:pypi/committed"),
        RegistryFacts(error="TimeoutError"),
        previous={"id": "committed", "license": "MIT"},
    )
    kept, cut = select([*ranked, stranded], limit=2)
    assert "committed" in [e.candidate.id for e in kept]
    assert "committed" not in [e.candidate.id for e in cut]
    assert sorted(e.candidate.id for e in kept) == ["committed", "py0", "py1"]


def test_a_new_candidate_whose_lookup_failed_is_still_subject_to_the_limit():
    """The negative control: only an already-shipped row holds its place.

    A brand new candidate that could not be checked has no committed row to
    protect, so letting it bypass the limit would make the limit optional.
    """
    ranked = [
        verify(sdk(f"py{i}", f"pkg:pypi/py{i}"), RegistryFacts(downloads=100 - i), None)
        for i in range(2)
    ]
    newcomer = verify(sdk("newcomer", "pkg:pypi/newcomer"), RegistryFacts(error="Timeout"), None)
    kept, cut = select([*ranked, newcomer], limit=2)
    assert [e.candidate.id for e in cut] == ["newcomer"]


def test_an_ambiguous_multi_licence_never_reaches_the_seed():
    """A registry naming two licences without an operator states no obligation.

    The committed identifier stands and the report says why; writing either
    operator would publish a legal claim the registry never made.
    """
    from scripts.seed_catalog.registries import AMBIGUOUS_LICENSE

    entry = verify(
        sdk("thing", "pkg:gem/thing"),
        RegistryFacts(license=AMBIGUOUS_LICENSE + "MIT, Apache-2.0"),
        previous={"id": "thing", "license": "MIT"},
    )
    assert entry.license == "MIT"
    assert any("relationship not stated" in note for note in entry.notes)


def test_an_ambiguous_licence_with_nothing_committed_stays_empty():
    from scripts.seed_catalog.registries import AMBIGUOUS_LICENSE

    entry = verify(
        sdk("thing", "pkg:gem/thing"),
        RegistryFacts(license=AMBIGUOUS_LICENSE + "MIT, Apache-2.0"),
        previous=None,
    )
    assert entry.license is None
    assert any("relationship not stated" in note for note in entry.notes)
