-- Migration v4: HF repo registration date on models, for the oldest-candidate
-- pick on multi-model file hashes.
--
-- A file hash claimed by several models cannot be resolved by content alone
-- (a base model and its quantization legitimately share untouched shards).
-- The seed path's policy is to assert the EARLIEST-REGISTERED repo — the
-- presumed original that was later forked or re-uploaded — and disclose the
-- alternates; exact identification through transformation is the
-- fingerprinting surface, not this one.
--
-- Named repo_created_at, NOT created_at: models.created_at already exists as
-- the row-insertion audit stamp, and reusing the name would silently compare
-- registration dates against insertion times. Values are the seed's canonical
-- whole-second UTC form ('YYYY-MM-DDTHH:MM:SSZ') or NULL; the exporter
-- enforces that shape so lexicographic ORDER BY is chronological ORDER BY.

-- One transaction, deliberately. executescript() runs each statement in its
-- own implicit transaction, so without this a crash between the ALTER and the
-- version stamp leaves the column present with the version still 3 — and the
-- next open re-runs the ALTER, which has no IF NOT EXISTS form, and fails
-- with "duplicate column name" forever (review finding). Wrapped, a crash
-- rolls both back and the re-run starts clean. A concurrent second opener
-- blocks (or errors) on the write lock and finds version 4 on its next open;
-- transient, never corrupting.
BEGIN;

ALTER TABLE models ADD COLUMN repo_created_at TEXT;

-- OR IGNORE to match schema.sql's stamp of the same row.
INSERT OR IGNORE INTO schema_version (version) VALUES (4);

COMMIT;
