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
    source TEXT DEFAULT 'seed',  -- seed, crawled, user
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sdks_category ON sdks(category);

-- Known AI models (from HuggingFace, etc.)
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purl TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    organization TEXT,
    version TEXT,
    format TEXT,
    architecture TEXT,
    architecture_family TEXT,
    parameter_count INTEGER,
    quantization TEXT,
    sha256 TEXT,
    tlsh TEXT,
    license TEXT,
    source_url TEXT,
    task TEXT,                    -- HuggingFace pipeline_tag (text-generation, etc.)
    base_model_purl TEXT,         -- Fine-tuned from
    datasets TEXT,                -- JSON array of dataset names
    source TEXT DEFAULT 'crawled',  -- seed, crawled, user
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Known packages (PyPI, npm, etc.)
CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purl TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ecosystem TEXT NOT NULL,      -- pypi, npm, cargo, golang, maven
    version TEXT,
    license TEXT,
    summary TEXT,
    homepage TEXT,
    author TEXT,
    is_ai_package INTEGER DEFAULT 1,
    ai_category TEXT,             -- sdk, framework, library, tool
    source TEXT DEFAULT 'crawled',  -- seed, crawled, user
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_packages_ecosystem ON packages(ecosystem);
CREATE INDEX IF NOT EXISTS idx_packages_name ON packages(name);

CREATE INDEX IF NOT EXISTS idx_models_sha256 ON models(sha256);
CREATE INDEX IF NOT EXISTS idx_models_tlsh ON models(tlsh);
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);

-- Known MCP servers
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    purl TEXT,
    patterns TEXT NOT NULL,  -- JSON array of import/require patterns
    description TEXT,
    source TEXT DEFAULT 'seed',  -- seed, crawled, user
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
INSERT OR IGNORE INTO schema_version (version) VALUES (2);

-- Initialize KB sync state
INSERT OR IGNORE INTO sync_state (key, value) VALUES ('kb_version', '0');
INSERT OR IGNORE INTO sync_state (key, value) VALUES ('kb_last_sync', NULL);
