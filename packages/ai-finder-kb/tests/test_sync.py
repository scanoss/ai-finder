"""Tests for KB sync mechanism."""

import json
from unittest.mock import MagicMock, patch

import requests
from ai_finder_kb import KBSync, SyncResult, SyncStatus
from ai_finder_kb.database import Database


class TestKBSync:
    """Tests for KBSync class."""

    def test_get_local_version_initial(self, temp_db_path) -> None:
        """Test getting local version on fresh DB."""
        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            assert sync.get_local_version() == 0

    def test_get_last_sync_initial(self, temp_db_path) -> None:
        """Test getting last sync on fresh DB."""
        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            assert sync.get_last_sync() is None

    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_for_updates_no_remote(self, mock_session_class, temp_db_path) -> None:
        """Test check_for_updates when remote is unavailable."""
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("Network error")
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            status = sync.check_for_updates()

            assert status.local_version == 0
            assert status.remote_version is None
            assert status.update_available is False
            assert status.error is not None

    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_for_updates_available(self, mock_session_class, temp_db_path) -> None:
        """Test check_for_updates when update is available."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 1}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            status = sync.check_for_updates()

            assert status.local_version == 0
            assert status.remote_version == 1
            assert status.update_available is True
            assert status.error is None

    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_for_updates_no_update(self, mock_session_class, temp_db_path) -> None:
        """Test check_for_updates when already up to date."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 0}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            status = sync.check_for_updates()

            assert status.local_version == 0
            assert status.remote_version == 0
            assert status.update_available is False
            assert status.error is None

    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_no_update_available(self, mock_session_class, temp_db_path) -> None:
        """Test sync when no update is available."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": 0}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            result = sync.sync()

            assert result.success is True
            assert result.previous_version == 0
            assert result.new_version == 0
            assert result.error is None  # No error - just no update available

    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_with_sdks(self, mock_session_class, temp_db_path) -> None:
        """Test sync with SDK data."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 1}
        version_response.raise_for_status = MagicMock()

        sdks_response = MagicMock()
        sdks_response.json.return_value = [
            {
                "id": "test-sdk",
                "purl": "pkg:pypi/test-sdk",
                "patterns": ["test_sdk"],
                "category": "llm-client",
                "license": "MIT",
            }
        ]
        sdks_response.raise_for_status = MagicMock()

        models_response = MagicMock()
        models_response.json.return_value = []
        models_response.raise_for_status = MagicMock()

        mcp_response = MagicMock()
        mcp_response.json.return_value = []
        mcp_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                return models_response
            elif "mcp_servers.json" in url:
                return mcp_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            result = sync.sync()

            assert result.success is True
            assert result.previous_version == 0
            assert result.new_version == 1
            assert result.sdks_updated == 1
            assert result.models_updated == 0
            assert result.mcp_servers_updated == 0

            # Verify SDK was inserted
            row = db.execute(
                "SELECT id, purl, source FROM sdks WHERE id = 'test-sdk'"
            ).fetchone()
            assert row is not None
            assert row[0] == "test-sdk"
            assert row[1] == "pkg:pypi/test-sdk"
            assert row[2] == "seed"

    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_preserves_crawled_data(self, mock_session_class, temp_db_path) -> None:
        """Test that sync preserves crawled data."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 1}
        version_response.raise_for_status = MagicMock()

        sdks_response = MagicMock()
        sdks_response.json.return_value = [
            {
                "id": "test-sdk",
                "purl": "pkg:pypi/test-sdk-new",
                "patterns": ["test_sdk_new"],
                "category": "llm-client",
                "license": "MIT",
            }
        ]
        sdks_response.raise_for_status = MagicMock()

        models_response = MagicMock()
        models_response.json.return_value = []
        models_response.raise_for_status = MagicMock()

        mcp_response = MagicMock()
        mcp_response.json.return_value = []
        mcp_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                return models_response
            elif "mcp_servers.json" in url:
                return mcp_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()

            # Insert a crawled SDK with same ID
            db.execute(
                "INSERT INTO sdks (id, purl, patterns, category, license, source) "
                "VALUES ('test-sdk', 'pkg:pypi/test-sdk-crawled', "
                "'[\"crawled\"]', 'llm-client', 'MIT', 'crawled')"
            )
            db.commit()

            sync = KBSync(db)
            result = sync.sync()

            assert result.success is True

            # Verify crawled SDK was NOT updated
            row = db.execute(
                "SELECT purl, source FROM sdks WHERE id = 'test-sdk'"
            ).fetchone()
            assert row is not None
            assert row[0] == "pkg:pypi/test-sdk-crawled"  # Unchanged
            assert row[1] == "crawled"

    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_force(self, mock_session_class, temp_db_path) -> None:
        """Test sync with force=True."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 0}
        version_response.raise_for_status = MagicMock()

        sdks_response = MagicMock()
        sdks_response.json.return_value = [
            {
                "id": "test-sdk",
                "purl": "pkg:pypi/test-sdk",
                "patterns": ["test_sdk"],
                "category": "llm-client",
                "license": "MIT",
            }
        ]
        sdks_response.raise_for_status = MagicMock()

        models_response = MagicMock()
        models_response.json.return_value = []
        models_response.raise_for_status = MagicMock()

        mcp_response = MagicMock()
        mcp_response.json.return_value = []
        mcp_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                return models_response
            elif "mcp_servers.json" in url:
                return mcp_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)

            # Without force, should succeed but with no changes
            result = sync.sync(force=False)
            assert result.success is True
            assert result.error is None
            assert result.new_version == result.previous_version

            # With force, should sync anyway
            result = sync.sync(force=True)
            assert result.success is True
            assert result.sdks_updated == 1


    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_partial_fetch_failure(self, mock_session_class, temp_db_path) -> None:
        """Test that partial fetch failure does NOT bump version."""
        version_response = MagicMock()
        version_response.json.return_value = {"version": 1}
        version_response.raise_for_status = MagicMock()

        sdks_response = MagicMock()
        sdks_response.json.return_value = [
            {
                "id": "test-sdk",
                "purl": "pkg:pypi/test-sdk",
                "patterns": ["test_sdk"],
                "category": "llm-client",
                "license": "MIT",
            }
        ]
        sdks_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                # Simulate network failure for models
                raise requests.RequestException("Network error fetching models")
            elif "mcp_servers.json" in url:
                raise requests.RequestException("Network error fetching mcp_servers")
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            result = sync.sync()

            # Should fail due to partial fetch failure
            assert result.success is False
            assert "Sync failure" in result.error
            assert len(result.fetch_errors) == 2  # models and mcp_servers failed
            # All counts are 0 because we rolled back
            assert result.sdks_updated == 0
            assert result.models_updated == 0
            assert result.mcp_servers_updated == 0

            # Version should NOT have been bumped
            assert sync.get_local_version() == 0

    @patch("ai_finder_kb.sync.requests.Session")
    def test_check_for_updates_invalid_version(self, mock_session_class, temp_db_path) -> None:
        """Test check_for_updates with invalid version format."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "not-a-number"}
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            status = sync.check_for_updates()

            assert status.remote_version is None
            assert status.update_available is False
            assert "Invalid version format" in status.error


    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_checksum_verification_success(self, mock_session_class, temp_db_path) -> None:
        """Test sync succeeds when checksums match."""
        import hashlib

        sdk_data = [{
            "id": "test-sdk",
            "purl": "pkg:pypi/test",
            "patterns": ["test"],
            "category": "llm-client",
            "license": "MIT",
        }]
        sdk_json = json.dumps(sdk_data).encode()
        sdk_checksum = hashlib.sha256(sdk_json).hexdigest()

        version_response = MagicMock()
        version_response.json.return_value = {
            "version": 1,
            "checksums": {
                "sdks.json": sdk_checksum,
                "models.json": hashlib.sha256(b"[]").hexdigest(),
                "mcp_servers.json": hashlib.sha256(b"[]").hexdigest(),
            }
        }
        version_response.raise_for_status = MagicMock()

        sdks_response = MagicMock()
        sdks_response.json.return_value = sdk_data
        sdks_response.content = sdk_json
        sdks_response.raise_for_status = MagicMock()

        models_response = MagicMock()
        models_response.json.return_value = []
        models_response.content = b"[]"
        models_response.raise_for_status = MagicMock()

        mcp_response = MagicMock()
        mcp_response.json.return_value = []
        mcp_response.content = b"[]"
        mcp_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                return models_response
            elif "mcp_servers.json" in url:
                return mcp_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            result = sync.sync()

            assert result.success is True
            assert result.sdks_updated == 1

    @patch("ai_finder_kb.sync.requests.Session")
    def test_sync_checksum_verification_failure(self, mock_session_class, temp_db_path) -> None:
        """Test sync fails when checksums don't match."""
        version_response = MagicMock()
        version_response.json.return_value = {
            "version": 1,
            "checksums": {
                "sdks.json": "wrong_checksum_value",
                "models.json": "wrong_checksum_value",
                "mcp_servers.json": "wrong_checksum_value",
            }
        }
        version_response.raise_for_status = MagicMock()

        # All files return data that won't match the wrong checksums
        sdks_response = MagicMock()
        sdks_response.json.return_value = [{"id": "test", "purl": "pkg:test/test", "patterns": []}]
        sdks_response.content = b'[{"id": "test", "purl": "pkg:test/test", "patterns": []}]'
        sdks_response.raise_for_status = MagicMock()

        models_response = MagicMock()
        models_response.json.return_value = []
        models_response.content = b"[]"
        models_response.raise_for_status = MagicMock()

        mcp_response = MagicMock()
        mcp_response.json.return_value = []
        mcp_response.content = b"[]"
        mcp_response.raise_for_status = MagicMock()

        def mock_get(url, timeout=None):
            if "version.json" in url:
                return version_response
            elif "sdks.json" in url:
                return sdks_response
            elif "models.json" in url:
                return models_response
            elif "mcp_servers.json" in url:
                return mcp_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        with Database(temp_db_path) as db:
            db.initialize()
            sync = KBSync(db)
            result = sync.sync()

            assert result.success is False
            assert "Checksum mismatch" in result.error
            assert result.sdks_updated == 0


class TestSyncStatus:
    """Tests for SyncStatus dataclass."""

    def test_create_sync_status(self) -> None:
        status = SyncStatus(
            local_version=1,
            remote_version=2,
            last_sync=None,
            update_available=True,
        )
        assert status.local_version == 1
        assert status.remote_version == 2
        assert status.update_available is True
        assert status.error is None


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_create_sync_result(self) -> None:
        result = SyncResult(
            success=True,
            previous_version=1,
            new_version=2,
            sdks_updated=10,
            models_updated=5,
            mcp_servers_updated=3,
        )
        assert result.success is True
        assert result.previous_version == 1
        assert result.new_version == 2
        assert result.sdks_updated == 10
        assert result.models_updated == 5
        assert result.mcp_servers_updated == 3
        assert result.error is None
