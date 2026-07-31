"""Tests for file-level model hash lookup.

The point of `model_files` is that a filename cannot identify a weight file: 57%
of real basenames are generic and 99% for sharded safetensors. These tests pin the
behaviour that makes the hash path trustworthy, including the cases where it must
decline rather than guess.
"""

import hashlib
import json

import pytest
from ai_finder_kb.database import Database
from ai_finder_kb.matcher import Matcher
from ai_finder_kb.seed import seed_model_files
from ai_finder_kb.sync import KBSync

SHARD_HEX = hashlib.sha256(b"shard-one").hexdigest()
OTHER_HEX = hashlib.sha256(b"shard-two").hexdigest()
ABSENT_HEX = hashlib.sha256(b"never-seeded").hexdigest()


@pytest.fixture
def db_with_model_files(temp_db_path):
    """A KB holding one model with two generically named shards."""
    with Database(temp_db_path) as db:
        db.initialize()
        db.execute(
            "INSERT INTO models (purl, name, organization, license, source) "
            "VALUES ('pkg:huggingface/qwen/Qwen3-8B', 'Qwen3-8B', 'qwen', 'Apache-2.0', 'seed')"
        )
        model_id = db.execute(
            "SELECT id FROM models WHERE purl = 'pkg:huggingface/qwen/Qwen3-8B'"
        ).fetchone()[0]
        for digest, path in (
            (SHARD_HEX, "model-00001-of-00002.safetensors"),
            (OTHER_HEX, "model-00002-of-00002.safetensors"),
        ):
            db.execute(
                "INSERT INTO model_files (h, model_id, path, size_bytes) VALUES (?, ?, ?, ?)",
                (bytes.fromhex(digest), model_id, path, 4096),
            )
        db.commit()
        yield db


class TestMatchModelByHash:
    def test_resolves_a_generically_named_shard(self, db_with_model_files):
        match = Matcher(db_with_model_files).match_model_by_hash(SHARD_HEX)
        assert match is not None
        assert match.purl == "pkg:huggingface/qwen/Qwen3-8B"
        assert match.license == "Apache-2.0"
        # Exact, unlike the 0.9 the filename matcher hardcodes for a guess.
        assert match.confidence == 1.0

    def test_accepts_raw_bytes_and_uppercase_hex(self, db_with_model_files):
        matcher = Matcher(db_with_model_files)
        assert matcher.match_model_by_hash(bytes.fromhex(SHARD_HEX)) is not None
        assert matcher.match_model_by_hash(SHARD_HEX.upper()) is not None
        assert matcher.match_model_by_hash(f"  {SHARD_HEX}  ") is not None

    def test_unknown_hash_misses(self, db_with_model_files):
        assert Matcher(db_with_model_files).match_model_by_hash(ABSENT_HEX) is None

    def test_malformed_digest_is_a_clean_miss(self, db_with_model_files):
        """A truncated or misalgorithmed digest must not become an empty query that
        silently matches nothing-in-particular."""
        matcher = Matcher(db_with_model_files)
        for bad in ("", "not-hex", SHARD_HEX[:32], "ab" * 20, b"short", b"", None):
            assert matcher.match_model_by_hash(bad) is None, bad

    def test_missing_table_is_a_miss_not_a_crash(self, temp_db_path):
        """A pre-v3 user KB has no model_files table; the caller falls back to
        filename matching rather than erroring."""
        with Database(temp_db_path) as db:
            db.initialize()
            db.execute("DROP TABLE model_files")
            db.commit()
            assert Matcher(db).match_model_by_hash(SHARD_HEX) is None

    def test_ambiguous_hash_is_deterministic_and_flagged(self, db_with_model_files):
        """Byte-identical weights published under unrelated purls are genuinely
        ambiguous. Pick the same one every time and say so via confidence."""
        db = db_with_model_files
        db.execute(
            "INSERT INTO models (purl, name, license, source) "
            "VALUES ('pkg:huggingface/aaa/copy', 'copy', 'MIT', 'seed')"
        )
        other_id = db.execute(
            "SELECT id FROM models WHERE purl = 'pkg:huggingface/aaa/copy'"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO model_files (h, model_id, path) VALUES (?, ?, ?)",
            (bytes.fromhex(SHARD_HEX), other_id, "model-00001-of-00002.safetensors"),
        )
        db.commit()

        first = Matcher(db).match_model_by_hash(SHARD_HEX)
        second = Matcher(db).match_model_by_hash(SHARD_HEX)
        assert first.purl == second.purl == "pkg:huggingface/aaa/copy"  # lowest purl
        assert first.confidence == 0.95

    def test_shards_of_one_model_do_not_double_count(self, db_with_model_files):
        """Two shards of the same model are one model, not an ambiguous match."""
        match = Matcher(db_with_model_files).match_model_by_hash(OTHER_HEX)
        assert match.confidence == 1.0


class TestSeedModelFiles:
    def test_skips_rows_whose_purl_is_not_in_models(self, temp_db_path, tmp_path, monkeypatch):
        """A model_files row for an unknown purl would violate the FK, and could
        never resolve to a purl anyway."""
        import ai_finder_kb.seed as seed_module

        seed_dir = tmp_path / "seed"
        seed_dir.mkdir()
        (seed_dir / "model_files.json").write_text(
            json.dumps(
                [
                    {
                        "sha256": SHARD_HEX,
                        "purl": "pkg:huggingface/o/known",
                        "path": "a.safetensors",
                        "size_bytes": 1,
                    },
                    {
                        "sha256": OTHER_HEX,
                        "purl": "pkg:huggingface/o/absent",
                        "path": "b.safetensors",
                        "size_bytes": 2,
                    },
                    # Bad digests must be dropped, not inserted at the wrong width.
                    {
                        "sha256": "nothex",
                        "purl": "pkg:huggingface/o/known",
                        "path": "c.safetensors",
                    },
                    {
                        "sha256": SHARD_HEX[:32],
                        "purl": "pkg:huggingface/o/known",
                        "path": "d.safetensors",
                    },
                    {"purl": "pkg:huggingface/o/known", "path": "e.safetensors"},
                    # A null or numeric sha256 raises TypeError, not ValueError.
                    # model_files.json is machine-generated, so one bad row must
                    # skip rather than abort the entire seed build.
                    {
                        "sha256": None,
                        "purl": "pkg:huggingface/o/known",
                        "path": "f.safetensors",
                    },
                    {
                        "sha256": 12345,
                        "purl": "pkg:huggingface/o/known",
                        "path": "g.safetensors",
                    },
                ]
            )
        )
        monkeypatch.setattr(seed_module, "SEED_DIR", seed_dir)

        with Database(temp_db_path) as db:
            db.initialize()
            db.execute(
                "INSERT INTO models (purl, name, source) "
                "VALUES ('pkg:huggingface/o/known', 'known', 'seed')"
            )
            db.commit()

            assert seed_model_files(db) == 1
            db.commit()
            rows = db.execute("SELECT hex(h), path FROM model_files").fetchall()
            assert [(r[0].lower(), r[1]) for r in rows] == [(SHARD_HEX, "a.safetensors")]

    def test_absent_file_is_not_an_error(self, temp_db_path, tmp_path, monkeypatch):
        import ai_finder_kb.seed as seed_module

        monkeypatch.setattr(seed_module, "SEED_DIR", tmp_path / "empty")
        with Database(temp_db_path) as db:
            db.initialize()
            assert seed_model_files(db) == 0


class TestSyncModelFiles:
    def test_sync_replaces_rather_than_accumulates(self, db_with_model_files, monkeypatch):
        """The remote artifact is regenerated wholesale every sync, so a row that
        has disappeared from it (signature withdrawn, purl demoted to a mirror)
        must stop resolving here too."""
        db = db_with_model_files
        sync = KBSync(db)

        # Remote now knows only the first shard.
        monkeypatch.setattr(
            sync,
            "_fetch_json",
            lambda filename, checksum=None: (
                [
                    {
                        "sha256": SHARD_HEX,
                        "purl": "pkg:huggingface/qwen/Qwen3-8B",
                        "path": "model-00001-of-00002.safetensors",
                        "size_bytes": 4096,
                    }
                ],
                None,
            ),
        )
        count, error = sync._sync_model_files()
        db.commit()

        assert (count, error) == (1, None)
        assert Matcher(db).match_model_by_hash(SHARD_HEX) is not None
        # The withdrawn shard is gone, not left behind by an upsert.
        assert Matcher(db).match_model_by_hash(OTHER_HEX) is None

    def test_sync_reports_fetch_error(self, db_with_model_files, monkeypatch):
        sync = KBSync(db_with_model_files)
        monkeypatch.setattr(sync, "_fetch_json", lambda f, checksum=None: (None, "boom"))
        count, error = sync._sync_model_files()
        assert (count, error) == (0, "boom")
        # A failed fetch must not have wiped the existing rows.
        assert Matcher(db_with_model_files).match_model_by_hash(SHARD_HEX) is not None


class TestRemoteWithoutModelFiles:
    """A client newer than the remote is the normal state right after a release.

    The remote only gains model_files.json when a seed sync lands there, so for a
    while every `kb update` talks to a remote that does not publish it. Requesting
    it anyway returns 404, which sync treats as a fatal fetch error and rolls the
    whole sync back, so `kb update` would fail outright for everyone. version.json
    is the remote's own manifest of what it publishes, so it decides.
    """

    def _remote(self, monkeypatch, sync, checksums):
        """Stub a remote whose version.json advertises exactly `checksums`."""
        requested: list[str] = []

        def fake_fetch(filename, checksum=None):
            requested.append(filename)
            if filename == sync.VERSION_FILE:
                return {"version": 9, "checksums": checksums}, None
            if filename == sync.MODEL_FILES_FILE:
                # What raw.githubusercontent actually does for an absent file.
                return None, f"Failed to fetch {filename}: 404 Client Error: Not Found"
            return [], None

        monkeypatch.setattr(sync, "_fetch_json", fake_fetch)
        return requested

    def test_unadvertised_artifact_is_not_requested(self, db_with_model_files, monkeypatch):
        sync = KBSync(db_with_model_files)
        requested = self._remote(monkeypatch, sync, {"sdks.json": "x", "models.json": "y"})

        result = sync.sync()

        assert result.success is True, result.error
        assert result.new_version == 9
        assert "model_files.json" not in requested
        assert result.model_files_updated == 0

    def test_existing_hashes_survive_an_older_remote(self, db_with_model_files, monkeypatch):
        """Syncing against a remote with no hashes must not wipe the ones we have."""
        sync = KBSync(db_with_model_files)
        self._remote(monkeypatch, sync, {"sdks.json": "x"})

        assert sync.sync().success is True
        assert Matcher(db_with_model_files).match_model_by_hash(SHARD_HEX) is not None

    def test_advertised_but_missing_is_still_an_error(self, db_with_model_files, monkeypatch):
        """If version.json claims the artifact, a 404 is a genuine inconsistency
        and must fail loudly rather than be silently tolerated."""
        sync = KBSync(db_with_model_files)
        requested = self._remote(
            monkeypatch, sync, {"sdks.json": "x", "model_files.json": "deadbeef"}
        )

        result = sync.sync()

        assert result.success is False
        assert "model_files.json" in requested
        assert any("model_files" in e for e in result.fetch_errors)


class TestSeedVersionStamping:
    """A freshly seeded database must claim the version of the seed it holds."""

    def _seed_dir(self, tmp_path, monkeypatch, version):
        import ai_finder_kb.seed as seed_module

        d = tmp_path / "seed"
        d.mkdir()
        (d / "version.json").write_text(json.dumps({"version": version, "checksums": {}}))
        monkeypatch.setattr(seed_module, "SEED_DIR", d)
        return d

    def test_stamps_the_bundled_version(self, temp_db_path, tmp_path, monkeypatch):
        from ai_finder_kb.seed import seed_database

        self._seed_dir(tmp_path, monkeypatch, 6)
        with Database(temp_db_path) as db:
            db.initialize()
            seed_database(db)
            row = db.execute("SELECT value FROM sync_state WHERE key='kb_version'").fetchone()
            assert row[0] == "6"

    def test_prevents_a_downgrade_from_an_older_remote(self, temp_db_path, tmp_path, monkeypatch):
        """The real point of stamping. A seed at 6 against a remote at 5 must read
        as up to date, not as an update that overwrites newer bundled rows with
        staler ones and nulls columns the old artifact does not carry."""
        from ai_finder_kb.seed import seed_database

        self._seed_dir(tmp_path, monkeypatch, 6)
        with Database(temp_db_path) as db:
            db.initialize()
            seed_database(db)
            sync = KBSync(db)
            monkeypatch.setattr(
                sync, "_fetch_json", lambda f, checksum=None: ({"version": 5}, None)
            )
            status = sync.check_for_updates()
            assert status.local_version == 6
            assert status.update_available is False

    def test_missing_version_file_is_not_fatal(self, temp_db_path, tmp_path, monkeypatch):
        import ai_finder_kb.seed as seed_module
        from ai_finder_kb.seed import stamp_seed_version

        monkeypatch.setattr(seed_module, "SEED_DIR", tmp_path / "absent")
        with Database(temp_db_path) as db:
            db.initialize()
            assert stamp_seed_version(db) == 0


class TestMigrationIdempotency:
    """Re-running the v3 migration must not fail.

    Every statement in v003_add_model_files.sql is IF NOT EXISTS except the
    schema_version stamp, which was a bare INSERT. Applying the file twice hit the
    primary key on schema_version.version and surfaced as `Migration v3 failed`,
    even though the migration had in fact already succeeded. schema.sql stamps the
    same row with OR IGNORE.
    """

    def test_applying_v003_twice_is_safe(self, temp_db_path):
        from pathlib import Path

        import ai_finder_kb

        migration = (
            Path(ai_finder_kb.__file__).parent / "migrations/v003_add_model_files.sql"
        ).read_text()

        with Database(temp_db_path) as db:
            db.initialize()
            # initialize() already stamped version 3 via schema.sql; applying the
            # migration on top is the case a re-run produces.
            db.conn.executescript(migration)
            db.conn.executescript(migration)
            db.commit()
            versions = [r[0] for r in db.execute("SELECT version FROM schema_version").fetchall()]
            assert versions.count(3) == 1


class TestRepoCreatedAtMigration:
    """v004: the repo_created_at column and the v3 -> v4 upgrade path."""

    def test_fresh_database_has_the_column_at_version_4(self, temp_db_path):
        with Database(temp_db_path) as db:
            db.initialize()
            cols = [r[1] for r in db.execute("PRAGMA table_info(models)").fetchall()]
            assert "repo_created_at" in cols
            assert db.get_version() == 4
            # The registration date and the row-audit stamp are distinct columns:
            # same name upstream, different meaning here, and conflating them
            # would compare registration dates against insertion times.
            assert "created_at" in cols

    def test_a_v3_database_is_migrated_on_open(self, temp_db_path):
        """Simulate an existing pre-v4 install: no column, version stamped 3.

        The stamp must be REPLACED, not just deleted: a fresh schema.sql stamps
        only 4, so bare deletion empties the table, get_version() reads 0, and
        initialize() re-runs schema.sql — whose CREATE TABLE IF NOT EXISTS
        skips the existing models table and stamps 4 with the column still
        missing. That is not the shape any real v3 install has."""
        with Database(temp_db_path) as db:
            db.initialize()
            db.conn.executescript(
                "ALTER TABLE models DROP COLUMN repo_created_at;"
                "DELETE FROM schema_version WHERE version = 4;"
                "INSERT OR IGNORE INTO schema_version (version) VALUES (3);"
            )
            db.commit()
            assert db.get_version() == 3

        with Database(temp_db_path) as db:
            db.initialize()  # must apply v004
            cols = [r[1] for r in db.execute("PRAGMA table_info(models)").fetchall()]
            assert "repo_created_at" in cols
            assert db.get_version() == 4

    def test_seed_models_maps_created_at_to_repo_created_at(self, temp_db_path, monkeypatch):
        """models.json speaks the corpus vocabulary (created_at = HF repo
        registration date); the column is repo_created_at. The mapping is the
        one line that ties them together."""
        import ai_finder_kb.seed as seed_mod

        rows = {
            "models.json": [
                {
                    "purl": "pkg:huggingface/acme/m",
                    "name": "m",
                    "created_at": "2023-05-01T00:00:00Z",
                },
                {"purl": "pkg:huggingface/acme/undated", "name": "undated"},
            ]
        }
        monkeypatch.setattr(seed_mod, "load_seed_data", lambda f: rows.get(f, []))
        with Database(temp_db_path) as db:
            db.initialize()
            assert seed_mod.seed_models(db) == 2
            got = dict(
                db.execute("SELECT purl, repo_created_at FROM models ORDER BY purl").fetchall()
            )
            assert got["pkg:huggingface/acme/m"] == "2023-05-01T00:00:00Z"
            assert got["pkg:huggingface/acme/undated"] is None


def _downgrade_to_v3(db_path):
    """Turn a freshly initialized DB into the shape of a real v3 install."""
    with Database(db_path) as db:
        db.initialize()
        db.conn.executescript(
            "ALTER TABLE models DROP COLUMN repo_created_at;"
            "DELETE FROM schema_version WHERE version = 4;"
            "INSERT OR IGNORE INTO schema_version (version) VALUES (3);"
        )
        db.commit()


class TestMigrationReachesEveryOpenPath:
    """The v004 review found migrations were unreachable from real usage:
    KnowledgeBase copied the seed and reconnected without initialize(), an
    existing user kb.db only hit the runner on the empty-DB branch, and scan/
    identify open KBEnricher directly, which never touched ai_finder_kb at
    all. Each open path gets its own regression test, because each was broken
    separately."""

    def test_knowledge_base_migrates_an_existing_v3_kb(self, temp_db_path):
        from ai_finder_kb import KnowledgeBase

        _downgrade_to_v3(temp_db_path)
        kb = KnowledgeBase(db_path=temp_db_path, use_seed=False)
        try:
            assert kb.db.get_version() == 4
            cols = [r[1] for r in kb.db.execute("PRAGMA table_info(models)").fetchall()]
            assert "repo_created_at" in cols
        finally:
            kb.close()

    def test_enricher_migrates_the_kb_it_opens(self, temp_db_path):
        """scan and identify never construct KnowledgeBase; the enricher is
        the only chance their database gets. A v3 KB with a hash row must
        come back resolvable, not silently degrade to filename matching."""
        import hashlib

        from ai_finder_scanner.enrichment.kb_enricher import KBEnricher

        _downgrade_to_v3(temp_db_path)
        digest = hashlib.sha256(b"weights").hexdigest()
        with Database(temp_db_path) as db:
            db.execute(
                "INSERT INTO models (purl, name, source) VALUES (?, 'm', 'seed')",
                ("pkg:huggingface/acme/m",),
            )
            model_id = db.execute(
                "SELECT id FROM models WHERE purl = ?", ("pkg:huggingface/acme/m",)
            ).fetchone()[0]
            db.execute(
                "INSERT INTO model_files (h, model_id, path, size_bytes) VALUES (?, ?, ?, ?)",
                (bytes.fromhex(digest), model_id, "model.safetensors", 4096),
            )
            db.commit()

        with KBEnricher(db_path=temp_db_path, enable_live_fallback=False) as enricher:
            result = enricher.lookup_model_by_hash(digest)
        assert result is not None and result.purl == "pkg:huggingface/acme/m"
        with Database(temp_db_path) as db:
            assert db.get_version() == 4

    def test_a_table_bearing_unstamped_db_is_not_falsely_stamped(self, temp_db_path):
        """Version 0 with tables is a legacy database, not a fresh one.
        Running schema.sql over it skips every existing table (IF NOT EXISTS)
        and then stamps the current version for a schema that was never
        brought forward. It must be treated as v1 and walked through the
        ALTER-based migrations instead."""
        import sqlite3 as sq

        # A faithful minimal v1 shape: the tables the v2..v4 migrations touch,
        # WITHOUT the columns they add, and no schema_version table at all.
        conn = sq.connect(temp_db_path)
        conn.executescript(
            "CREATE TABLE sdks (id TEXT PRIMARY KEY, purl TEXT, patterns TEXT NOT NULL,"
            " category TEXT, license TEXT, created_at TEXT);"
            "CREATE TABLE models (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " purl TEXT UNIQUE NOT NULL, name TEXT NOT NULL, organization TEXT,"
            " version TEXT, format TEXT, architecture TEXT, architecture_family TEXT,"
            " parameter_count INTEGER, quantization TEXT, sha256 TEXT, tlsh TEXT,"
            " license TEXT, source_url TEXT, task TEXT, base_model_purl TEXT,"
            " datasets TEXT, created_at TEXT, updated_at TEXT);"
            "CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, purl TEXT,"
            " patterns TEXT NOT NULL, description TEXT, created_at TEXT);"
            "CREATE TABLE packages (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " purl TEXT UNIQUE NOT NULL, name TEXT NOT NULL, ecosystem TEXT NOT NULL,"
            " version TEXT, license TEXT, summary TEXT, homepage TEXT, author TEXT,"
            " is_ai_package INTEGER DEFAULT 1, ai_category TEXT, created_at TEXT,"
            " updated_at TEXT);"
            "CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);"
            "INSERT INTO models (purl, name) VALUES ('pkg:huggingface/old/m', 'm');"
        )
        conn.commit()
        conn.close()

        with Database(temp_db_path) as db:
            db.initialize()
            cols = [r[1] for r in db.execute("PRAGMA table_info(models)").fetchall()]
            assert "repo_created_at" in cols, "legacy DB must be walked forward, not stamped"
            assert "source" in cols  # v002's column arrived too
            assert db.get_version() == 4
            # And the pre-existing data survived the walk.
            row = db.execute("SELECT name FROM models WHERE purl = 'pkg:huggingface/old/m'")
            assert row.fetchone()[0] == "m"
