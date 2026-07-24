"""KB sync mechanism for remote seed data updates."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .database import Database

logger = logging.getLogger(__name__)

# Default remote URL for seed data (GitHub raw content)
DEFAULT_REMOTE_URL = (
    "https://raw.githubusercontent.com/scanoss/ai-finder/main/"
    "packages/ai-finder/src/ai_finder_kb/seed"
)


@dataclass
class SyncStatus:
    """Status of the KB sync state."""

    local_version: int
    remote_version: int | None
    last_sync: datetime | None
    update_available: bool
    error: str | None = None


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    previous_version: int
    new_version: int
    sdks_updated: int = 0
    models_updated: int = 0
    model_files_updated: int = 0
    mcp_servers_updated: int = 0
    error: str | None = None
    fetch_errors: list[str] = field(default_factory=list)  # Track which fetches failed


class KBSync:
    """Handles KB sync with remote seed data."""

    VERSION_FILE = "version.json"
    SDK_FILE = "sdks.json"
    MODELS_FILE = "models.json"
    MODEL_FILES_FILE = "model_files.json"
    MCP_SERVERS_FILE = "mcp_servers.json"

    def __init__(
        self,
        db: Database,
        remote_url: str = DEFAULT_REMOTE_URL,
        timeout: int = 30,
    ) -> None:
        """Initialize KB sync.

        Args:
            db: Database instance.
            remote_url: Base URL for remote seed data.
            timeout: Request timeout in seconds.
        """
        self.db = db
        self.remote_url = remote_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def get_local_version(self) -> int:
        """Get the current local KB version.

        Returns:
            Local KB version number.
        """
        result = self.db.execute("SELECT value FROM sync_state WHERE key = 'kb_version'").fetchone()
        return int(result[0]) if result else 0

    def get_last_sync(self) -> datetime | None:
        """Get the timestamp of the last sync.

        Returns:
            Last sync timestamp or None if never synced.
        """
        result = self.db.execute(
            "SELECT value FROM sync_state WHERE key = 'kb_last_sync'"
        ).fetchone()
        if result and result[0]:
            return datetime.fromisoformat(result[0])
        return None

    def _fetch_json(
        self, filename: str, expected_checksum: str | None = None
    ) -> tuple[dict | list | None, str | None]:
        """Fetch a JSON file from the remote URL.

        Args:
            filename: Name of the file to fetch.
            expected_checksum: Optional SHA256 checksum to verify integrity.

        Returns:
            Tuple of (data, error). If error is None, fetch succeeded.
            Data can be empty list/dict on success if server returned empty.
        """
        url = f"{self.remote_url}/{filename}"
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Verify checksum if provided
            if expected_checksum:
                actual_checksum = hashlib.sha256(response.content).hexdigest()
                if actual_checksum != expected_checksum:
                    error_msg = (
                        f"Checksum mismatch for {filename}: "
                        f"expected {expected_checksum[:16]}..., "
                        f"got {actual_checksum[:16]}..."
                    )
                    logger.warning(error_msg)
                    return None, error_msg

            return response.json(), None
        except requests.RequestException as e:
            error_msg = f"Failed to fetch {filename}: {e}"
            logger.warning(error_msg)
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON from {filename}: {e}"
            logger.warning(error_msg)
            return None, error_msg

    def check_for_updates(self) -> SyncStatus:
        """Check if updates are available.

        Returns:
            SyncStatus with version information.
        """
        local_version = self.get_local_version()
        last_sync = self.get_last_sync()

        # Fetch remote version
        version_data, error = self._fetch_json(self.VERSION_FILE)
        if error is not None or not isinstance(version_data, dict):
            return SyncStatus(
                local_version=local_version,
                remote_version=None,
                last_sync=last_sync,
                update_available=False,
                error=error or "Invalid version.json format",
            )

        # Validate version field
        try:
            remote_version = int(version_data.get("version", 0))
        except (TypeError, ValueError):
            return SyncStatus(
                local_version=local_version,
                remote_version=None,
                last_sync=last_sync,
                update_available=False,
                error="Invalid version format in remote version.json",
            )

        return SyncStatus(
            local_version=local_version,
            remote_version=remote_version,
            last_sync=last_sync,
            update_available=remote_version > local_version,
        )

    def sync(self, force: bool = False) -> SyncResult:
        """Sync the KB with remote seed data.

        Args:
            force: Force sync even if no update is available.

        Returns:
            SyncResult with operation details.
        """
        local_version = self.get_local_version()

        # Fetch version.json to get checksums and remote version
        version_data, version_error = self._fetch_json(self.VERSION_FILE)
        if version_error or not isinstance(version_data, dict):
            return SyncResult(
                success=False,
                previous_version=local_version,
                new_version=local_version,
                error=version_error or "Invalid version.json format",
            )

        # Validate version field
        try:
            remote_version = int(version_data.get("version", 0))
        except (TypeError, ValueError):
            return SyncResult(
                success=False,
                previous_version=local_version,
                new_version=local_version,
                error="Invalid version format in remote version.json",
            )

        # Check if update is needed
        if remote_version <= local_version and not force:
            return SyncResult(
                success=True,
                previous_version=local_version,
                new_version=local_version,
            )

        # Extract checksums (may be None for older version.json without checksums)
        checksums = version_data.get("checksums", {})

        # Fetch and apply seed data, tracking any errors
        fetch_errors: list[str] = []
        try:
            sdks_count, sdk_error = self._sync_sdks(checksums.get(self.SDK_FILE))
            if sdk_error:
                fetch_errors.append(sdk_error)

            models_count, model_error = self._sync_models(checksums.get(self.MODELS_FILE))
            if model_error:
                fetch_errors.append(model_error)

            # After _sync_models: model_files rows are keyed to models by purl.
            model_files_count, model_files_error = self._sync_model_files(
                checksums.get(self.MODEL_FILES_FILE)
            )
            if model_files_error:
                fetch_errors.append(model_files_error)

            mcp_count, mcp_error = self._sync_mcp_servers(checksums.get(self.MCP_SERVERS_FILE))
            if mcp_error:
                fetch_errors.append(mcp_error)

            # Only bump version if ALL operations succeeded (no fetch or insert errors)
            if fetch_errors:
                # Rollback any partial writes to maintain consistency
                self.db.conn.rollback()
                return SyncResult(
                    success=False,
                    previous_version=local_version,
                    new_version=local_version,
                    sdks_updated=0,  # Rolled back
                    models_updated=0,
                    model_files_updated=0,
                    mcp_servers_updated=0,
                    error=f"Sync failure: {'; '.join(fetch_errors)}",
                    fetch_errors=fetch_errors,
                )

            # Update sync state using INSERT OR REPLACE (upsert) for robustness
            now = datetime.now(timezone.utc).isoformat()
            self.db.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) "
                "VALUES ('kb_version', ?, ?)",
                (str(remote_version), now),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) "
                "VALUES ('kb_last_sync', ?, ?)",
                (now, now),
            )
            self.db.commit()

            return SyncResult(
                success=True,
                previous_version=local_version,
                new_version=remote_version,
                sdks_updated=sdks_count,
                models_updated=models_count,
                model_files_updated=model_files_count,
                mcp_servers_updated=mcp_count,
            )

        except Exception as e:
            # Rollback any partial writes on exception
            self.db.conn.rollback()
            logger.exception("Sync failed")
            return SyncResult(
                success=False,
                previous_version=local_version,
                new_version=local_version,
                error=str(e),
            )

    def _sync_sdks(self, checksum: str | None = None) -> tuple[int, str | None]:
        """Sync SDKs from remote.

        Args:
            checksum: Optional SHA256 checksum to verify file integrity.

        Returns:
            Tuple of (count, error). Error is None if all operations succeeded.
        """
        sdks, fetch_error = self._fetch_json(self.SDK_FILE, checksum)
        if fetch_error is not None:
            return 0, fetch_error

        if not sdks:
            return 0, None  # Empty list is valid, not an error

        count = 0
        insert_errors: list[str] = []
        for sdk in sdks:
            try:
                self.db.execute(
                    """
                    INSERT INTO sdks (id, purl, patterns, category, license, source)
                    VALUES (?, ?, ?, ?, ?, 'seed')
                    ON CONFLICT(id) DO UPDATE SET
                        purl = excluded.purl,
                        patterns = excluded.patterns,
                        category = excluded.category,
                        license = excluded.license
                    WHERE source = 'seed'
                    """,
                    (
                        sdk["id"],
                        sdk["purl"],
                        json.dumps(sdk["patterns"]),
                        sdk.get("category"),
                        sdk.get("license"),
                    ),
                )
                count += 1
            except Exception as e:
                error_msg = f"SDK {sdk.get('id')}: {e}"
                logger.warning(f"Failed to sync {error_msg}")
                insert_errors.append(error_msg)

        if insert_errors:
            return count, f"Failed to insert {len(insert_errors)} SDKs: {insert_errors[0]}"
        return count, None

    def _sync_models(self, checksum: str | None = None) -> tuple[int, str | None]:
        """Sync models from remote.

        Args:
            checksum: Optional SHA256 checksum to verify file integrity.

        Returns:
            Tuple of (count, error). Error is None if all operations succeeded.
        """
        models, fetch_error = self._fetch_json(self.MODELS_FILE, checksum)
        if fetch_error is not None:
            return 0, fetch_error

        if not models:
            return 0, None  # Empty list is valid, not an error

        count = 0
        insert_errors: list[str] = []
        for model in models:
            try:
                self.db.execute(
                    """
                    INSERT INTO models
                    (purl, name, organization, architecture, architecture_family,
                     parameter_count, license, format, quantization, task,
                     base_model_purl, source_url, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed')
                    ON CONFLICT(purl) DO UPDATE SET
                        name = excluded.name,
                        organization = excluded.organization,
                        architecture = excluded.architecture,
                        architecture_family = excluded.architecture_family,
                        parameter_count = excluded.parameter_count,
                        license = excluded.license,
                        format = excluded.format,
                        quantization = excluded.quantization,
                        task = excluded.task,
                        base_model_purl = excluded.base_model_purl,
                        source_url = excluded.source_url,
                        updated_at = datetime('now')
                    WHERE source = 'seed'
                    """,
                    (
                        model["purl"],
                        model["name"],
                        model.get("organization"),
                        model.get("architecture"),
                        model.get("architecture_family"),
                        model.get("parameter_count"),
                        model.get("license"),
                        model.get("format"),
                        model.get("quantization"),
                        model.get("task"),
                        model.get("base_model_purl"),
                        model.get("source_url"),
                    ),
                )
                count += 1
            except Exception as e:
                error_msg = f"model {model.get('name')}: {e}"
                logger.warning(f"Failed to sync {error_msg}")
                insert_errors.append(error_msg)

        if insert_errors:
            return count, f"Failed to insert {len(insert_errors)} models: {insert_errors[0]}"
        return count, None

    def _sync_model_files(self, checksum: str | None = None) -> tuple[int, str | None]:
        """Sync file-level model hashes from remote.

        Must run after `_sync_models`: rows are keyed to `models` by purl, and a
        row whose purl is not in the KB is skipped rather than treated as an error
        (the FK would reject it, and it could never resolve to a purl anyway).

        Args:
            checksum: Optional SHA256 checksum to verify file integrity.

        Returns:
            Tuple of (count, error). Error is None if all operations succeeded.
        """
        model_files, fetch_error = self._fetch_json(self.MODEL_FILES_FILE, checksum)
        if fetch_error is not None:
            return 0, fetch_error

        if not model_files:
            return 0, None  # Empty list is valid, not an error

        # One query instead of ~100k correlated lookups: the artifact carries ~20k
        # purls across ~100k rows.
        model_ids = {
            row["purl"]: row["id"]
            for row in self.db.execute("SELECT id, purl FROM models").fetchall()
        }

        # Replace wholesale rather than upserting. The remote artifact is
        # regenerated from the corpus every sync, so a row that has disappeared
        # from it (a signature withdrawn, or a purl demoted to a mirror) must stop
        # resolving here too — an upsert would leave it behind forever.
        self.db.execute(
            "DELETE FROM model_files WHERE model_id IN "
            "(SELECT id FROM models WHERE source = 'seed')"
        )

        count = 0
        skipped = 0
        insert_errors: list[str] = []
        for entry in model_files:
            model_id = model_ids.get(entry.get("purl"))
            if model_id is None:
                skipped += 1
                continue
            try:
                digest = bytes.fromhex(entry["sha256"])
            except (KeyError, ValueError, TypeError):
                skipped += 1
                continue
            if len(digest) != 32:
                skipped += 1
                continue
            try:
                self.db.execute(
                    """
                    INSERT OR REPLACE INTO model_files (h, model_id, path, size_bytes)
                    VALUES (?, ?, ?, ?)
                    """,
                    (digest, model_id, entry.get("path"), entry.get("size_bytes")),
                )
                count += 1
            except Exception as e:
                error_msg = f"model file {entry.get('path')}: {e}"
                logger.warning(f"Failed to sync {error_msg}")
                insert_errors.append(error_msg)

        if skipped:
            logger.debug("Skipped %d model_files rows (unknown purl or bad digest)", skipped)
        if insert_errors:
            return (
                count,
                f"Failed to insert {len(insert_errors)} model files: {insert_errors[0]}",
            )
        return count, None

    def _sync_mcp_servers(self, checksum: str | None = None) -> tuple[int, str | None]:
        """Sync MCP servers from remote.

        Args:
            checksum: Optional SHA256 checksum to verify file integrity.

        Returns:
            Tuple of (count, error). Error is None if all operations succeeded.
        """
        mcp_servers, fetch_error = self._fetch_json(self.MCP_SERVERS_FILE, checksum)
        if fetch_error is not None:
            return 0, fetch_error

        if not mcp_servers:
            return 0, None  # Empty list is valid, not an error

        count = 0
        insert_errors: list[str] = []
        for mcp in mcp_servers:
            try:
                self.db.execute(
                    """
                    INSERT INTO mcp_servers (id, purl, patterns, description, source)
                    VALUES (?, ?, ?, ?, 'seed')
                    ON CONFLICT(id) DO UPDATE SET
                        purl = excluded.purl,
                        patterns = excluded.patterns,
                        description = excluded.description
                    WHERE source = 'seed'
                    """,
                    (
                        mcp["id"],
                        mcp["purl"],
                        json.dumps(mcp["patterns"]),
                        mcp.get("description"),
                    ),
                )
                count += 1
            except Exception as e:
                error_msg = f"MCP server {mcp.get('id')}: {e}"
                logger.warning(f"Failed to sync {error_msg}")
                insert_errors.append(error_msg)

        if insert_errors:
            return count, f"Failed to insert {len(insert_errors)} MCP servers: {insert_errors[0]}"
        return count, None
