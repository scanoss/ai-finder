"""SQLite database operations for SCANOSS AI KB."""

import sqlite3
from pathlib import Path
from typing import Any, Optional, Tuple

SCHEMA_VERSION = 1


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

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL statement."""
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        """Commit current transaction."""
        self.conn.commit()

    def initialize(self) -> None:
        """Initialize database schema."""
        current_version = self.get_version()

        if current_version == 0:
            schema_path = Path(__file__).parent / "schema.sql"
            schema_sql = schema_path.read_text()
            self.conn.executescript(schema_sql)
            self.commit()

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
