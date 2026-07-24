-- Migration v3: file-level SHA-256 lookup for model weight files
--
-- Identification by filename cannot work for most real inputs: 57% of weight-file
-- basenames are generic (pytorch_model.bin, model.safetensors) and 99% for sharded
-- safetensors, so no substring of model-00003-of-00026.safetensors will ever match
-- a models.name. A content hash is the only thing that does.
--
-- models.sha256 is the wrong shape for this (a model averages 4.5 weight files),
-- so this is a child table. models.sha256 and models.tlsh stay unpopulated.

CREATE TABLE IF NOT EXISTS model_files (
    h BLOB NOT NULL,              -- 32-byte sha256 of the file contents
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    path TEXT,                    -- repo-relative path
    size_bytes INTEGER,
    UNIQUE(h, model_id, path)
);

-- Not UNIQUE on h alone: ~1% of hashes are byte-identical weights published under
-- unrelated purls, and a model's shards legitimately share the table.
CREATE INDEX IF NOT EXISTS idx_model_files_h ON model_files(h);
CREATE INDEX IF NOT EXISTS idx_model_files_model_id ON model_files(model_id);

-- Update schema version
INSERT INTO schema_version (version) VALUES (3);
