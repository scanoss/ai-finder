"""Tests for scripts/verify_seed_db.py.

The script is the only thing standing between "the release built a database" and
"the release built the right database", so its own pass/fail logic is worth
pinning. In particular a seed with no model_files.json must verify clean (the
code that reads file hashes ships before the hashes are published), without that
tolerance quietly disabling the checks that catch a genuinely broken database.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest
from ai_finder_kb.database import Database

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts/verify_seed_db.py"


def load_script() -> ModuleType:
    """Import verify_seed_db.py by path; scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("verify_seed_db", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def vsd() -> ModuleType:
    return load_script()


def make_db(path: Path, *, model_files: str = "none", kb_version: int = 1) -> Path:
    """Build a real schema database with one sdk, one model and one mcp server.

    model_files: "none" (empty table), "valid" (one joinable 32-byte digest),
    "orphan" (references a missing model), or "short" (digest is not 32 bytes).
    """
    with Database(path) as db:
        db.initialize()
        db.execute("INSERT INTO sdks (id, patterns) VALUES ('openai', '[\"openai\"]')")
        db.execute("INSERT INTO models (id, purl, name) VALUES (1, 'pkg:huggingface/acme/m', 'm')")
        db.execute("INSERT INTO mcp_servers (id, patterns) VALUES ('srv', '[\"srv\"]')")
        db.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('kb_version', ?)",
            (str(kb_version),),
        )
        db.commit()

    # model_files goes in on a plain connection: Database enables foreign keys,
    # and the orphan case has to get past them to simulate a bad build. A pragma
    # inside an open transaction is silently ignored, hence the separate handle.
    rows = {
        "valid": (b"\x01" * 32, 1, "model.safetensors"),
        "orphan": (b"\x02" * 32, 999, "x.bin"),
        "short": (b"\x03" * 16, 1, "x.bin"),
    }
    if model_files in rows:
        con = sqlite3.connect(str(path))
        try:
            con.execute(
                "INSERT INTO model_files (h, model_id, path) VALUES (?, ?, ?)",
                rows[model_files],
            )
            con.commit()
        finally:
            con.close()
    return path


def write_seed(seed_dir: Path, *, model_files: int | None, version: int = 1) -> None:
    """Write seed JSONs matching make_db's row counts."""
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "sdks.json").write_text(json.dumps([{"id": "openai"}]))
    (seed_dir / "models.json").write_text(json.dumps([{"purl": "pkg:huggingface/acme/m"}]))
    (seed_dir / "mcp_servers.json").write_text(json.dumps([{"id": "srv"}]))
    if model_files is not None:
        (seed_dir / "model_files.json").write_text(
            json.dumps([{"sha256": "01" * 32}] * model_files)
        )
    (seed_dir / "version.json").write_text(json.dumps({"version": version}))


def run_main(vsd: ModuleType, seed_dir: Path, db: Path, monkeypatch) -> int:
    """Run the script's main() against a seed dir, returning its exit code."""
    monkeypatch.setattr(vsd, "SEED_DIR", seed_dir)
    monkeypatch.setattr(sys, "argv", ["verify_seed_db.py", "--db", str(db)])
    try:
        vsd.main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


class TestNoModelFilesSeed:
    """A seed that publishes no file hashes is a valid rollout state."""

    def test_verifies_clean(self, vsd, tmp_path, monkeypatch):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=None)
        db = make_db(tmp_path / "seed.db")

        assert run_main(vsd, seed, db, monkeypatch) == 0

    def test_reports_the_skip_rather_than_passing_silently(
        self, vsd, tmp_path, monkeypatch, capsys
    ):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=None)
        db = make_db(tmp_path / "seed.db")

        run_main(vsd, seed, db, monkeypatch)

        assert "hash lookup is NOT verified" in capsys.readouterr().out


class TestModelFilesSeed:
    """Once hashes are published the assertions apply in full."""

    def test_empty_table_fails(self, vsd, tmp_path, monkeypatch):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=1)
        db = make_db(tmp_path / "seed.db")  # table empty

        assert run_main(vsd, seed, db, monkeypatch) == 1

    def test_populated_table_passes(self, vsd, tmp_path, monkeypatch):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=1)
        db = make_db(tmp_path / "seed.db", model_files="valid")

        assert run_main(vsd, seed, db, monkeypatch) == 0


class TestIntegrityChecksNotWeakened:
    """The tolerance must only skip the join assertion, nothing else."""

    @pytest.fixture
    def seed(self, vsd, tmp_path, monkeypatch) -> Path:
        """A seed dir the module reads version.json from, at kb_version 1."""
        seed = tmp_path / "seed"
        write_seed(seed, model_files=None, version=1)
        monkeypatch.setattr(vsd, "SEED_DIR", seed)
        return seed

    def test_join_assertion_skipped_only_when_not_expected(self, vsd, tmp_path, seed):
        db = make_db(tmp_path / "seed.db")  # no model_files rows

        assert vsd.integrity_checks(db, expect_model_files=False) == []
        problems = vsd.integrity_checks(db, expect_model_files=True)
        assert any("joins to a model purl" in p for p in problems)

    def test_orphans_still_reported_when_not_expected(self, vsd, tmp_path, seed):
        db = make_db(tmp_path / "seed.db", model_files="orphan")

        problems = vsd.integrity_checks(db, expect_model_files=False)
        assert any("reference a missing model" in p for p in problems)

    def test_short_digests_still_reported_when_not_expected(self, vsd, tmp_path, seed):
        db = make_db(tmp_path / "seed.db", model_files="short")

        problems = vsd.integrity_checks(db, expect_model_files=False)
        assert any("not 32 bytes" in p for p in problems)

    def test_kb_version_mismatch_still_reported_when_not_expected(self, vsd, tmp_path, monkeypatch):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=None, version=7)
        monkeypatch.setattr(vsd, "SEED_DIR", seed)
        db = make_db(tmp_path / "seed.db", kb_version=3)

        problems = vsd.integrity_checks(db, expect_model_files=False)
        assert any("kb_version is 3, expected 7" in p for p in problems)


class TestExpectCountsPath:
    """The wheel check compares against saved counts, not the JSONs."""

    def test_zero_model_files_in_saved_counts_is_tolerated(
        self, vsd, tmp_path, monkeypatch, capsys
    ):
        seed = tmp_path / "seed"
        write_seed(seed, model_files=None)
        db = make_db(tmp_path / "seed.db")
        counts = tmp_path / "counts.json"

        monkeypatch.setattr(vsd, "SEED_DIR", seed)
        monkeypatch.setattr(
            sys,
            "argv",
            ["verify_seed_db.py", "--db", str(db), "--write-counts", str(counts)],
        )
        vsd.main()

        assert json.loads(counts.read_text())["model_files"] == 0

        monkeypatch.setattr(
            sys,
            "argv",
            ["verify_seed_db.py", "--db", str(db), "--expect-counts", str(counts)],
        )
        vsd.main()  # must not raise
        assert "hash lookup is NOT verified" in capsys.readouterr().out
