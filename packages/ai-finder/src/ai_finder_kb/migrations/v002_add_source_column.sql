-- Migration v2: Add source column for KB sync mechanism
-- Allows distinguishing seed data (from remote updates) from crawled/user data

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

-- Update schema version
INSERT INTO schema_version (version) VALUES (2);
