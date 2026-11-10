-- Durable private objects and chunked uploads for Netlify + Neon.
-- Additive and idempotent; existing tables/permissions are unchanged.
BEGIN;
CREATE TABLE IF NOT EXISTS tt_stored_objects (
    key VARCHAR(255) PRIMARY KEY,
    size BIGINT NOT NULL DEFAULT 0,
    sha256 VARCHAR(64) NOT NULL DEFAULT '',
    mime VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
    name VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tt_stored_chunks (
    object_key VARCHAR(255) NOT NULL REFERENCES tt_stored_objects(key) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    data BYTEA NOT NULL,
    PRIMARY KEY (object_key, index)
);
CREATE TABLE IF NOT EXISTS tt_upload_transfers (
    id VARCHAR(64) PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    filename VARCHAR(255) NOT NULL,
    size BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    chunk_count INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tt_upload_transfers_owner_id ON tt_upload_transfers(owner_id);
CREATE INDEX IF NOT EXISTS ix_tt_upload_transfers_expires_at ON tt_upload_transfers(expires_at);
CREATE TABLE IF NOT EXISTS tt_upload_chunks (
    id SERIAL PRIMARY KEY,
    transfer_id VARCHAR(64) NOT NULL REFERENCES tt_upload_transfers(id) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    data BYTEA NOT NULL,
    CONSTRAINT uq_upload_chunk_index UNIQUE (transfer_id, index)
);
CREATE INDEX IF NOT EXISTS ix_tt_upload_chunks_transfer_id ON tt_upload_chunks(transfer_id);
COMMIT;
