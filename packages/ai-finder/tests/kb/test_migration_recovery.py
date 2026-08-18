"""Migration crash windows and the shape detection that replaces guessing.

Each test here fails without its fix, and each covers a path the rest of the
suite never reaches: a database left mid-migration, or a file that is not a KB
at all.
"""

import sqlite3
from pathlib import Path

import pytest
from ai_finder_kb.database import SCHEMA_VERSION, Database


def _schema_sql() -> str:
    import ai_finder_kb

    return (Path(ai_finder_kb.__file__).parent / "schema.sql").read_text()


def _version(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        except sqlite3.Error:
            return 0
    return row[0] if row and row[0] is not None else 0


def _columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_fresh_initialize_is_atomic(tmp_path):
    """A crash partway through schema.sql must leave nothing behind.

    Without the transaction wrapper, executescript() autocommits each DDL, so
    an interrupted fresh init left tables with no version stamp — a shape
    indistinguishable from a legacy install, which then replayed ALTER-based
    migrations against columns schema.sql had already created.
    """
    db_path = tmp_path / "kb.db"
    statements = _schema_sql()
    assert statements.count("BEGIN;") == 1, "schema.sql must run as one transaction"

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.Error):
        # Truncate mid-file, then append nothing: the open BEGIN never commits.
        conn.executescript(statements[: statements.index("CREATE TABLE IF NOT EXISTS models")])
        conn.execute("ROLLBACK")
        raise sqlite3.OperationalError("simulated crash")
    conn.close()

    assert _version(db_path) == 0
    # The next open must still produce a complete, stamped schema.
    with Database(db_path) as db:
        db.initialize()
    assert _version(db_path) == SCHEMA_VERSION
    assert "repo_created_at" in _columns(db_path, "models")


def test_v002_rolls_back_as_one_step(tmp_path):
    """A crash inside v002 must not leave columns applied at the old version.

    ALTER TABLE ADD COLUMN has no IF NOT EXISTS form, so a partially applied
    v002 used to fail with "duplicate column name" on every later open — a
    permanently unopenable KB.
    """
    import ai_finder_kb

    v002 = (
        Path(ai_finder_kb.__file__).parent / "migrations" / "v002_add_source_column.sql"
    ).read_text()
    assert "BEGIN;" in v002 and "COMMIT;" in v002
    assert "INSERT OR IGNORE INTO schema_version" in v002

    db_path = tmp_path / "kb.db"
    conn = sqlite3.connect(db_path)
    # A v1-shaped database: the tables v002 alters, no source columns, stamp 1.
    conn.executescript(
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY,"
        " applied_at TEXT DEFAULT (datetime('now')));"
        "CREATE TABLE models (id INTEGER PRIMARY KEY, purl TEXT UNIQUE NOT NULL, name TEXT);"
        "CREATE TABLE sdks (id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE mcp_servers (id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE packages (id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);"
        "INSERT INTO schema_version (version) VALUES (1);"
    )
    conn.commit()
    # Simulate the crash: run v002 up to its second ALTER, then abort.
    conn.executescript("BEGIN; ALTER TABLE sdks ADD COLUMN source TEXT DEFAULT 'seed'; ROLLBACK;")
    conn.close()

    assert _version(db_path) == 1
    assert "source" not in _columns(db_path, "sdks"), "the rolled-back ALTER must not persist"

    # The retry succeeds rather than dying on a duplicate column.
    with Database(db_path) as db:
        db.initialize()
    assert _version(db_path) == SCHEMA_VERSION
    assert "source" in _columns(db_path, "sdks")
    assert "repo_created_at" in _columns(db_path, "models")


@pytest.mark.parametrize(
    ("shape", "expected"),
    [("v2", 2), ("v3", 3), ("v4", 4)],
)
def test_unstamped_database_is_detected_not_assumed(tmp_path, shape, expected):
    """An unstamped database is stamped at the version its own shape shows.

    Assuming the oldest shape replays migrations whose columns already exist,
    which fails permanently. Detection reads newest-trace-first.
    """
    db_path = tmp_path / f"kb-{shape}.db"
    conn = sqlite3.connect(db_path)
    models_cols = "id INTEGER PRIMARY KEY, purl TEXT UNIQUE NOT NULL, name TEXT, source TEXT"
    if shape == "v4":
        models_cols += ", repo_created_at TEXT"
    conn.executescript(
        f"CREATE TABLE models ({models_cols});"
        "CREATE TABLE sdks (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE mcp_servers (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE packages (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
        "CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);"
    )
    if shape in ("v3", "v4"):
        conn.executescript(
            "CREATE TABLE model_files (h BLOB NOT NULL, model_id INTEGER NOT NULL,"
            " path TEXT, size_bytes INTEGER, UNIQUE(h, model_id, path));"
        )
    conn.commit()
    conn.close()

    assert _version(db_path) == 0
    with Database(db_path) as db:
        assert db._detect_version() == expected
        db.initialize()  # must not raise "duplicate column name"

    assert _version(db_path) == SCHEMA_VERSION
    assert "repo_created_at" in _columns(db_path, "models")
