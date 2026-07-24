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
