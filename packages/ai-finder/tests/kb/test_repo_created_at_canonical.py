"""The lexicographic-is-chronological invariant, enforced at ingest.

repo_created_at is ordered as a string, which is only chronological while every
value shares one format. These pin that non-canonical values become NULL rather
than values that sort wrong and silently invert which repo gets asserted.
"""

import pytest
from ai_finder_kb.seed import canonical_repo_created_at


@pytest.mark.parametrize(
    "value",
    [
        "2024-06-01T00:00:00Z",
        "1970-01-01T00:00:00Z",
    ],
)
def test_canonical_values_pass_through(value):
    assert canonical_repo_created_at(value) == value


def test_utc_offset_spelling_is_normalised():
    """+00:00 is the same instant as Z and differs only in spelling."""
    assert canonical_repo_created_at("2024-06-01T00:00:00+00:00") == "2024-06-01T00:00:00Z"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "2024-06-01T00:00:00-05:00",  # sorts before an earlier UTC stamp
        "2024-06-01T00:00:00.123456Z",  # sub-second, sorts after the whole second
        "2024-06-01 00:00:00",  # space separator sorts before 'T'
        "2024-06-01",  # date only
        1717200000,  # epoch int: compares as a short string, beats every date
        20240601,
        "not a date",
    ],
)
def test_non_canonical_values_become_null(value):
    """NULL is the safe direction: it sorts last and never wins the pick."""
    assert canonical_repo_created_at(value) is None


def test_a_malformed_date_cannot_outrank_a_real_one(tmp_path):
    """End to end: the bad value must not win the earliest-registered pick."""
    import sqlite3

    from ai_finder_kb.database import Database

    db_path = tmp_path / "kb.db"
    with Database(db_path) as db:
        db.initialize()

    rows = [
        ("pkg:huggingface/real/model", "2020-01-01T00:00:00Z"),
        # An epoch integer sorts before every ISO string, so unnormalised it
        # would be asserted as the earliest registration.
        ("pkg:huggingface/bogus/model", canonical_repo_created_at(1717200000)),
    ]
    conn = sqlite3.connect(db_path)
    for purl, created in rows:
        conn.execute(
            "INSERT INTO models (purl, name, repo_created_at) VALUES (?, ?, ?)",
            (purl, purl.rsplit("/", 1)[-1], created),
        )
    conn.commit()
    picked = conn.execute(
        "SELECT purl FROM models ORDER BY (repo_created_at IS NULL), repo_created_at, purl"
    ).fetchone()[0]
    conn.close()

    assert picked == "pkg:huggingface/real/model"
