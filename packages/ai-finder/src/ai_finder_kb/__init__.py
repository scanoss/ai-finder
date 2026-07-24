"""AI Finder Knowledge Base library."""

import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Optional

from .database import Database
from .matcher import Matcher
from .models import AncestryEdge, MCPMatch, ModelMatch, SDKMatch
from .sync import KBSync, SyncResult, SyncStatus

__version__ = "0.3.9"
__all__ = [
    "KnowledgeBase",
    "Database",
    "Matcher",
    "SDKMatch",
    "ModelMatch",
    "MCPMatch",
    "AncestryEdge",
    "KBSync",
    "SyncStatus",
    "SyncResult",
    "get_seed_db_path",
    "build_seed_db",
]


def get_default_db_path() -> Path:
    """Get default KB database path."""
    return Path.home() / ".config" / "scanoss" / "kb.db"


def get_seed_db_path() -> Optional[Path]:
    """Get path to bundled seed database."""
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


def build_seed_db() -> Optional[Path]:
    """Build the bundled seed database from the seed JSONs.

    seed.db is generated rather than committed, and release.yml builds it into the
    wheel. A source checkout has the seed JSONs but no seed.db, so build it on
    demand. Returns the path, or None if the package directory is not writable
    (a read-only install), in which case the caller seeds the user database
    directly from the JSONs instead.
    """
    from .seed import create_seed_db

    data_dir = Path(__file__).parent / "data"
    target = data_dir / "seed.db"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        # Build to a temp file in the same directory and rename, so two processes
        # racing on a fresh checkout cannot leave a half-written seed.db behind.
        tmp = data_dir / f"seed.db.{os.getpid()}.tmp"
        try:
            create_seed_db(tmp)
            os.replace(tmp, target)
        finally:
            with suppress(OSError):
                tmp.unlink()
    except OSError:
        return None
    return target if target.exists() else None


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
            if seed_path is None:
                # Source checkout, or a wheel built without the generated seed.db.
                seed_path = build_seed_db()
            if seed_path and seed_path.exists():
                import shutil

                self._db.close()
                shutil.copy(seed_path, self._db_path)
                self._db.connect()
            else:
                # Read-only install with no seed.db: seed this database directly
                # from the seed JSONs, which always ship in the wheel.
                from .seed import seed_database

                self._db.initialize()
                seed_database(self._db)

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

    def check_for_updates(self, remote_url: Optional[str] = None) -> SyncStatus:
        """Check if KB updates are available.

        Args:
            remote_url: Optional custom remote URL for seed data.

        Returns:
            SyncStatus with version information.
        """
        sync = KBSync(self.db, remote_url) if remote_url else KBSync(self.db)
        return sync.check_for_updates()

    def sync(self, remote_url: Optional[str] = None, force: bool = False) -> SyncResult:
        """Sync the KB with remote seed data.

        Args:
            remote_url: Optional custom remote URL for seed data.
            force: Force sync even if no update is available.

        Returns:
            SyncResult with operation details.
        """
        sync = KBSync(self.db, remote_url) if remote_url else KBSync(self.db)
        return sync.sync(force=force)
