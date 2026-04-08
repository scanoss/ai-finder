"""Tests for KB database operations."""

from scanoss_ai_kb.database import Database


class TestDatabase:
    def test_create_and_initialize(self, temp_db_path) -> None:
        db = Database(temp_db_path)
        db.connect()
        db.initialize()

        # Check schema version exists
        cursor = db.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1

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
            assert version == 1

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
            assert db.get_version() == 1
