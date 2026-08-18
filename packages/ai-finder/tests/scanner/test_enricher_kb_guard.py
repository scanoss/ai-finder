"""Opening the enricher must not rewrite a file that is not a knowledge base.

Migration-on-open makes __enter__ a writer. Without a guard, --kb-path aimed at
the wrong sqlite file turns a read-only mistake into a silent rewrite.
"""

import sqlite3

from ai_finder_scanner.enrichment.kb_enricher import KBEnricher


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_foreign_sqlite_file_is_left_alone(tmp_path):
    foreign = tmp_path / "notes.db"
    conn = sqlite3.connect(foreign)
    conn.execute("CREATE TABLE my_notes (id INTEGER, body TEXT)")
    conn.execute("INSERT INTO my_notes VALUES (1, 'unrelated user file')")
    conn.commit()
    conn.close()

    before = _tables(foreign)
    with KBEnricher(db_path=foreign, enable_live_fallback=False) as enricher:
        assert enricher.lookup_model("tinyllama.gguf") is None

    assert _tables(foreign) == before, "enricher must not create KB tables in a foreign database"
    with sqlite3.connect(foreign) as check:
        assert check.execute("SELECT body FROM my_notes").fetchone()[0] == "unrelated user file"


def test_non_sqlite_file_does_not_raise(tmp_path):
    junk = tmp_path / "not-a-database.bin"
    junk.write_bytes(b"\x00\x01\x02 definitely not sqlite")

    with KBEnricher(db_path=junk, enable_live_fallback=False) as enricher:
        assert enricher.lookup_model("tinyllama.gguf") is None
    assert junk.read_bytes().startswith(b"\x00\x01\x02")


def test_a_real_kb_still_migrates_on_open(tmp_path):
    """The guard must not disable migration for an actual KB.

    Builds a v3-shaped database directly rather than dropping a column from a
    current one: ALTER TABLE ... DROP COLUMN needs SQLite 3.35+, which is not
    guaranteed on every interpreter in the support matrix.
    """
    from ai_finder_kb.database import SCHEMA_VERSION

    kb = tmp_path / "kb.db"
    conn = sqlite3.connect(kb)
    conn.executescript(
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY,"
        " applied_at TEXT DEFAULT (datetime('now')));"
        "CREATE TABLE models (id INTEGER PRIMARY KEY, purl TEXT UNIQUE NOT NULL,"
        " name TEXT, source TEXT);"
        "CREATE TABLE sdks (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE mcp_servers (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE packages (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);"
        "CREATE TABLE model_files (h BLOB NOT NULL, model_id INTEGER NOT NULL,"
        " path TEXT, size_bytes INTEGER, UNIQUE(h, model_id, path));"
        "INSERT INTO schema_version (version) VALUES (3);"
    )
    conn.commit()
    conn.close()

    with KBEnricher(db_path=kb, enable_live_fallback=False):
        pass

    with sqlite3.connect(kb) as check:
        cols = {r[1] for r in check.execute("PRAGMA table_info(models)")}
        version = check.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert "repo_created_at" in cols, "a genuine pre-v4 KB must still be migrated"
    assert version == SCHEMA_VERSION
