"""AI Finder Knowledge Base library."""

from pathlib import Path
from typing import Any, Optional

from .database import Database
from .matcher import Matcher
from .models import AncestryEdge, MCPMatch, ModelMatch, SDKMatch

__version__ = "0.2.11"
__all__ = [
    "KnowledgeBase",
    "Database",
    "Matcher",
    "SDKMatch",
    "ModelMatch",
    "MCPMatch",
    "AncestryEdge",
    "get_seed_db_path",
]


def get_default_db_path() -> Path:
    """Get default KB database path."""
    return Path.home() / ".config" / "scanoss" / "kb.db"


def get_seed_db_path() -> Optional[Path]:
    """Get path to bundled seed database."""
    import sys

    # PyInstaller bundle: data is extracted to sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        pyinstaller_path = Path(sys._MEIPASS) / "ai_finder_kb" / "data" / "seed.db"
        if pyinstaller_path.exists():
            return pyinstaller_path

    # Standard Python: use importlib.resources
    try:
        import importlib.resources as resources

        data_dir = resources.files("ai_finder_kb") / "data"
        seed_path = data_dir / "seed.db"
        if hasattr(seed_path, "is_file") and seed_path.is_file():
            return Path(str(seed_path))
    except Exception:
        pass

    # Fallback: check relative to this file
    fallback = Path(__file__).parent / "data" / "seed.db"
    if fallback.exists():
        return fallback

    return None


class KnowledgeBase:
    """High-level facade for KB operations."""

    def __init__(self, db_path: Optional[Path] = None, use_seed: bool = True) -> None:
        """Initialize knowledge base.

        Args:
            db_path: Path to database file. Defaults to ~/.config/scanoss/kb.db
            use_seed: If True, initialize from bundled seed database.
        """
        self._db_path = db_path or get_default_db_path()
        self._use_seed = use_seed
        self._db: Optional[Database] = None
        self._matcher: Optional[Matcher] = None

        # Auto-connect
        self._connect()

    def _connect(self) -> None:
        """Connect to database and initialize."""
        self._db = Database(self._db_path)
        self._db.connect()

        # Initialize from seed if this is a fresh database
        if self._db.get_version() == 0 and self._use_seed:
            seed_path = get_seed_db_path()
            if seed_path and seed_path.exists():
                import shutil

                self._db.close()
                shutil.copy(seed_path, self._db_path)
                self._db.connect()
            else:
                self._db.initialize()

        self._matcher = Matcher(self._db)

    def __enter__(self) -> "KnowledgeBase":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close database connection."""
        if self._db:
            self._db.close()
            self._db = None
        self._matcher = None

    @property
    def db(self) -> Database:
        """Get database instance."""
        if self._db is None:
            raise RuntimeError("Database not connected")
        return self._db

    @property
    def matcher(self) -> Matcher:
        """Get matcher instance."""
        if self._matcher is None:
            raise RuntimeError("Matcher not initialized")
        return self._matcher
