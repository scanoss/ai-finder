-- Migration v2: Add source column for KB sync mechanism
-- Allows distinguishing seed data (from remote updates) from crawled/user data

-- One transaction, for the same reason v004 wraps itself. executescript() runs
-- each statement in its own implicit transaction, so a crash partway through
-- left some of the four ALTERs applied with the version still 1 — and ALTER
-- TABLE ADD COLUMN has no IF NOT EXISTS form, so every subsequent open re-ran
-- the whole file and failed with "duplicate column name" forever. That window
-- was nearly unreachable while migrations only ran from the fresh-database
-- path; it became reachable when opening an existing KB started migrating it.
-- Wrapped, a crash rolls the whole step back and the re-run starts clean.
BEGIN;

-- Add source column to sdks table
ALTER TABLE sdks ADD COLUMN source TEXT DEFAULT 'seed';

-- Add source column to models table
ALTER TABLE models ADD COLUMN source TEXT DEFAULT 'crawled';

-- Add source column to mcp_servers table
ALTER TABLE mcp_servers ADD COLUMN source TEXT DEFAULT 'seed';

-- Add source column to packages table
ALTER TABLE packages ADD COLUMN source TEXT DEFAULT 'crawled';

-- Add sync_state entries for KB version tracking
INSERT OR IGNORE INTO sync_state (key, value) VALUES ('kb_version', '0');
INSERT OR IGNORE INTO sync_state (key, value) VALUES ('kb_last_sync', NULL);

-- Update schema version. OR IGNORE to match schema.sql and v004, so a re-run
-- after a rolled-back crash is a no-op rather than a UNIQUE violation.
INSERT OR IGNORE INTO schema_version (version) VALUES (2);

COMMIT;
