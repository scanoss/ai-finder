"""Tests for scanner-side model hashing and hash-first enrichment.

The scan path is what actually produces SBOMs, so these cover the whole chain:
the scanner computing a digest, the enricher preferring it over the filename, and
all three SBOM writers carrying the resulting purl.
"""

import hashlib
import json
import struct

import pytest
from ai_finder_kb.database import Database
from ai_finder_scanner.enrichment.kb_enricher import KBEnricher
from ai_finder_scanner.models import Finding, FindingType, ModelInfo, ScanResult
from ai_finder_scanner.output import CycloneDXFormatter, SPDX3Formatter, SPDX23Formatter
from ai_finder_scanner.scanner import Scanner, compute_model_sha256

# The name from the acceptance criterion: nothing in it identifies the model.
SHARD_NAME = "model-00001-of-00026.safetensors"
PURL = "pkg:huggingface/qwen/Qwen3-8B"


def _safetensors_bytes(payload: bytes = b"\x00" * 512) -> bytes:
    """A minimal but genuinely parseable safetensors file."""
    header = json.dumps({"__metadata__": {"format": "pt"}}).encode()
    return struct.pack("<Q", len(header)) + header + payload


@pytest.fixture
def model_dir(tmp_path):
    """A directory holding one generically named shard."""
    d = tmp_path / "models"
    d.mkdir()
    (d / SHARD_NAME).write_bytes(_safetensors_bytes())
    return d


@pytest.fixture
def shard_digest(model_dir):
    return hashlib.sha256((model_dir / SHARD_NAME).read_bytes()).hexdigest()


@pytest.fixture
def kb_path(tmp_path, shard_digest):
    """A KB that knows the shard by hash only, never by name."""
    path = tmp_path / "kb.db"
    with Database(path) as db:
        db.initialize()
        db.execute(
            "INSERT INTO models (purl, name, organization, license, source_url, task, source) "
            "VALUES (?, 'Qwen3-8B', 'qwen', 'Apache-2.0', "
            "'https://huggingface.co/qwen/Qwen3-8B', 'text-generation', 'seed')",
            (PURL,),
        )
        model_id = db.execute("SELECT id FROM models WHERE purl = ?", (PURL,)).fetchone()[0]
        db.execute(
            "INSERT INTO model_files (h, model_id, path, size_bytes) VALUES (?, ?, ?, ?)",
            (bytes.fromhex(shard_digest), model_id, SHARD_NAME, 4096),
        )
        db.commit()
    return path


class TestComputeModelSha256:
    def test_matches_hashlib(self, model_dir, shard_digest):
        assert compute_model_sha256(model_dir / SHARD_NAME) == shard_digest

    def test_streams_a_file_larger_than_one_chunk(self, tmp_path):
        blob = bytes(range(256)) * 1024  # 256 KB, several 64 KB reads
        path = tmp_path / "big.bin"
        path.write_bytes(blob)
        assert compute_model_sha256(path) == hashlib.sha256(blob).hexdigest()

    def test_unreadable_file_returns_none(self, tmp_path):
        """An unreadable weight file should cost the hash, not the scan."""
        assert compute_model_sha256(tmp_path / "does-not-exist.safetensors") is None


class TestScannerHashing:
    def test_scan_populates_sha256_by_default(self, model_dir, shard_digest):
        result = Scanner(detect_licenses=False).scan(model_dir)
        models = [f for f in result.findings if f.type == FindingType.MODEL_FILE]
        assert len(models) == 1
        assert models[0].model_info.sha256 == shard_digest

    def test_no_model_hash_skips_it(self, model_dir):
        result = Scanner(detect_licenses=False, hash_model_files=False).scan(model_dir)
        models = [f for f in result.findings if f.type == FindingType.MODEL_FILE]
        assert len(models) == 1
        assert models[0].model_info.sha256 is None


class TestEnricherHashFirst:
    def test_hash_resolves_what_the_filename_cannot(self, kb_path, shard_digest):
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            # Filename alone: the KB holds no row whose name resembles the shard.
            assert enricher.lookup_model(SHARD_NAME) is None
            # With the hash: exact.
            hit = enricher.lookup_model(SHARD_NAME, sha256=shard_digest)
            assert hit is not None
            assert hit.purl == PURL
            assert hit.license == "Apache-2.0"

    def test_hash_hit_skips_the_live_api(self, kb_path, shard_digest, monkeypatch):
        with KBEnricher(db_path=kb_path, enable_live_fallback=True) as enricher:

            def explode(*args, **kwargs):
                raise AssertionError("live API must not be consulted on a hash hit")

            monkeypatch.setattr(enricher, "_fetch_model_live", explode)
            assert enricher.lookup_model(SHARD_NAME, sha256=shard_digest).purl == PURL

    def test_hash_miss_falls_through_to_filename(self, kb_path):
        """A hash that is not in the KB must not short-circuit the other paths."""
        absent = hashlib.sha256(b"absent").hexdigest()
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            assert enricher.lookup_model("Qwen3-8B.safetensors", sha256=absent).purl == PURL

    def test_hash_result_is_cached_separately_from_the_filename(self, kb_path, shard_digest):
        """The hash and the filename are different keys for the same file; a hash
        hit must not be served later as a filename result or vice versa."""
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            assert enricher.lookup_model(SHARD_NAME, sha256=shard_digest).purl == PURL
            # Same file, no hash offered this time: must not reuse the hash hit.
            assert enricher.lookup_model(SHARD_NAME) is None

    def test_no_db_is_a_clean_miss(self, shard_digest):
        with KBEnricher(db_path=None, enable_live_fallback=False) as enricher:
            assert enricher.lookup_model_by_hash(shard_digest) is None


class TestSbomCarriesHashDerivedPurl:
    """Every writer must surface the resolved purl, or the hash bought nothing."""

    @pytest.fixture
    def findings(self, shard_digest):
        return ScanResult(
            root_path=".",
            findings=[
                Finding(
                    type=FindingType.MODEL_FILE,
                    file_path=f"models/{SHARD_NAME}",
                    confidence=1.0,
                    model_info=ModelInfo(format="safetensors", sha256=shard_digest),
                )
            ],
        )

    def test_cyclonedx(self, findings, kb_path, shard_digest):
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            doc = CycloneDXFormatter().format(findings, enricher=enricher)
        component = next(c for c in json.loads(doc)["components"] if c["name"] == SHARD_NAME)
        assert component["purl"] == PURL
        assert component["hashes"] == [{"alg": "SHA-256", "content": shard_digest}]
        assert component["licenses"] == [{"license": {"id": "Apache-2.0"}}]

    def test_spdx23(self, findings, kb_path, shard_digest):
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            doc = SPDX23Formatter().format(findings, enricher=enricher)
        package = next(p for p in json.loads(doc)["packages"] if p["name"] == SHARD_NAME)
        assert package["checksums"] == [{"algorithm": "SHA256", "checksumValue": shard_digest}]
        assert package["licenseConcluded"] == "Apache-2.0"
        purls = [
            r["referenceLocator"] for r in package["externalRefs"] if r["referenceType"] == "purl"
        ]
        assert purls == [PURL]

    def test_spdx3(self, findings, kb_path, shard_digest):
        with KBEnricher(db_path=kb_path, enable_live_fallback=False) as enricher:
            doc = SPDX3Formatter().format(findings, enricher=enricher)
        element = next(
            e
            for e in json.loads(doc)["@graph"]
            if e.get("type") == "ai_AIPackage" and SHARD_NAME in e.get("name", "")
        )
        assert element["software_packageUrl"] == PURL
        assert element["software_declaredLicense"] == "Apache-2.0"
        assert element["verifiedUsing"] == [
            {"type": "Hash", "algorithm": "sha256", "hashValue": shard_digest}
        ]
