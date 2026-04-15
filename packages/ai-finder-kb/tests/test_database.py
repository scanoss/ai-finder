"""Tests for KB database operations."""

from ai_finder_kb.database import SCHEMA_VERSION, Database


class TestDatabase:
    def test_create_and_initialize(self, temp_db_path) -> None:
        db = Database(temp_db_path)
        db.connect()
        db.initialize()

        # Check schema version exists
        cursor = db.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == SCHEMA_VERSION

        db.close()

    def test_context_manager(self, temp_db_path) -> None:
        with Database(temp_db_path) as db:
            db.initialize()
            cursor = db.execute("SELECT version FROM schema_version")
            assert cursor.fetchone() is not None

    def test_get_version_uninitialized(self, temp_db_path) -> None:
        db = Database(temp_db_path)
        db.connect()
        version = db.get_version()
        assert version == 0
        db.close()

    def test_get_version_initialized(self, temp_db_path) -> None:
        with Database(temp_db_path) as db:
            db.initialize()
            version = db.get_version()
            assert version == SCHEMA_VERSION

    def test_tables_created(self, temp_db_path) -> None:
        with Database(temp_db_path) as db:
            db.initialize()

            # Check all expected tables exist
            cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cursor.fetchall()}

            expected_tables = {
                "schema_version",
                "sdks",
                "models",
                "packages",
                "mcp_servers",
                "model_provenance",
                "inferred_ancestry",
                "sync_state",
            }
            assert expected_tables.issubset(tables)

    def test_commit(self, temp_db_path) -> None:
        with Database(temp_db_path) as db:
            db.initialize()
            db.execute(
                "INSERT INTO sdks (id, purl, patterns, category) VALUES (?, ?, ?, ?)",
                ("test-sdk", "pkg:test/sdk", '["test"]', "test"),
            )
            db.commit()

            # Verify the insert persisted
            cursor = db.execute("SELECT id FROM sdks WHERE id = ?", ("test-sdk",))
            assert cursor.fetchone() is not None

    def test_double_initialize_is_safe(self, temp_db_path) -> None:
        with Database(temp_db_path) as db:
            db.initialize()
            db.initialize()  # Should not raise
            assert db.get_version() == SCHEMA_VERSION

    def test_source_column_exists(self, temp_db_path) -> None:
        """Verify source column exists in tables for KB sync mechanism."""
        with Database(temp_db_path) as db:
            db.initialize()

            # Check source column in sdks
            cursor = db.execute("PRAGMA table_info(sdks)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "source" in columns

            # Check source column in models
            cursor = db.execute("PRAGMA table_info(models)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "source" in columns

            # Check source column in packages
            cursor = db.execute("PRAGMA table_info(packages)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "source" in columns

            # Check source column in mcp_servers
            cursor = db.execute("PRAGMA table_info(mcp_servers)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "source" in columns

    def test_sync_state_initialized(self, temp_db_path) -> None:
        """Verify sync_state entries are created for KB version tracking."""
        with Database(temp_db_path) as db:
            db.initialize()

            cursor = db.execute("SELECT key, value FROM sync_state WHERE key = ?", ("kb_version",))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "kb_version"
            assert row[1] == "0"
