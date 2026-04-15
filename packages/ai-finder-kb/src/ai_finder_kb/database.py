"""SQLite database operations for AI Finder KB."""

import sqlite3
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 2


class Database:
    """SQLite database wrapper for KB operations."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def connect(self) -> None:
        """Open database connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get active connection, connecting if needed."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL statement."""
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        """Commit current transaction."""
        self.conn.commit()

    def initialize(self) -> None:
        """Initialize database schema and run pending migrations."""
        current_version = self.get_version()

        # Fresh database - apply initial schema
        if current_version == 0:
            schema_path = Path(__file__).parent / "schema.sql"
            schema_sql = schema_path.read_text()
            self.conn.executescript(schema_sql)
            self.commit()
            # Re-read version after applying schema (schema.sql sets current version)
            current_version = self.get_version()

        # Run pending migrations (only if database is behind SCHEMA_VERSION)
        if current_version < SCHEMA_VERSION:
            self._run_migrations(current_version)

    def _run_migrations(self, current_version: int) -> None:
        """Run all pending migrations from current version to SCHEMA_VERSION.

        Args:
            current_version: Current schema version in database.
        """
        migrations_dir = Path(__file__).parent / "migrations"

        for version in range(current_version + 1, SCHEMA_VERSION + 1):
            # Find the migration file for this version
            matching = list(migrations_dir.glob(f"v{version:03d}_*.sql"))

            if not matching:
                raise RuntimeError(f"Migration file not found for version {version}")

            migration_path = matching[0]
            migration_sql = migration_path.read_text()

            try:
                self.conn.executescript(migration_sql)
                self.commit()
            except sqlite3.Error as e:
                raise RuntimeError(f"Migration v{version} failed: {e}") from e

    def get_version(self) -> int:
        """Get current schema version.

        Returns:
            Schema version number, 0 if not initialized.
        """
        try:
            cursor = self.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0
