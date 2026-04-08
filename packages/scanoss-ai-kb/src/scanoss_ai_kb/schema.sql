-- SCANOSS AI Knowledge Base Schema v1

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Known SDKs and their import patterns
CREATE TABLE IF NOT EXISTS sdks (
    id TEXT PRIMARY KEY,
    purl TEXT,
    patterns TEXT NOT NULL,  -- JSON array of import patterns
    category TEXT,           -- llm-client, embedding, agent, framework
    license TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sdks_category ON sdks(category);

-- Known AI models
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purl TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    organization TEXT,
    version TEXT,
    format TEXT,
    architecture TEXT,
    parameter_count INTEGER,
    sha256 TEXT,
    tlsh TEXT,
    license TEXT,
    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_models_sha256 ON models(sha256);
CREATE INDEX IF NOT EXISTS idx_models_tlsh ON models(tlsh);
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);

-- Known MCP servers
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    purl TEXT,
    patterns TEXT NOT NULL,  -- JSON array of import/require patterns
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Model provenance (graph support)
CREATE TABLE IF NOT EXISTS model_provenance (
    model_id INTEGER PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    base_model_purl TEXT,
    fine_tuned INTEGER DEFAULT 0,
    merged INTEGER DEFAULT 0,
    adapter_type TEXT
);

-- Inferred ancestry edges (graph)
CREATE TABLE IF NOT EXISTS inferred_ancestry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_sha256 TEXT,
    source_purl TEXT,
    target_purl TEXT NOT NULL,
    relation_type TEXT NOT NULL,  -- fine-tuned | merged | possibly-derived
    confidence REAL NOT NULL,
    declared INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(source_sha256, target_purl, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_ancestry_source ON inferred_ancestry(source_sha256);
CREATE INDEX IF NOT EXISTS idx_ancestry_target ON inferred_ancestry(target_purl);

-- Sync state
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
