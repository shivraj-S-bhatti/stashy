-- Stashy: AI-Driven Universal Web Crawler — PostgreSQL schema
-- URL queue, raw pages, and extraction results for fault-tolerant distributed crawling

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- URL queue: pending, in_progress, done, failed
CREATE TABLE url_queue (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'done', 'failed')),
    priority    INT NOT NULL DEFAULT 0,
    retries     INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    claimed_at  TIMESTAMPTZ,
    claimed_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    error       TEXT
);

CREATE INDEX idx_url_queue_status_priority ON url_queue (status, priority DESC, id)
    WHERE status = 'pending';
CREATE INDEX idx_url_queue_claimed ON url_queue (claimed_by, claimed_at)
    WHERE status = 'in_progress';

-- Raw pages: HTML and metadata from fetch
CREATE TABLE raw_pages (
    id          BIGSERIAL PRIMARY KEY,
    url_id      BIGINT NOT NULL REFERENCES url_queue (id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    html        TEXT,
    status_code INT,
    content_type TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url_id)
);

CREATE INDEX idx_raw_pages_url_id ON raw_pages (url_id);

-- Extractions: LLM DOM pattern analysis results (structured JSON)
CREATE TABLE extractions (
    id          BIGSERIAL PRIMARY KEY,
    url_id      BIGINT NOT NULL REFERENCES url_queue (id) ON DELETE CASCADE,
    page_id     BIGINT NOT NULL REFERENCES raw_pages (id) ON DELETE CASCADE,
    schema_name TEXT,
    payload     JSONB NOT NULL,
    confidence  NUMERIC(5,4),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url_id)
);

CREATE INDEX idx_extractions_url_id ON extractions (url_id);
CREATE INDEX idx_extractions_schema ON extractions (schema_name);
CREATE INDEX idx_extractions_payload_gin ON extractions USING GIN (payload);

-- Crawl jobs (optional: batch / domain grouping)
CREATE TABLE crawl_jobs (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT,
    seed_urls   TEXT[] NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'paused', 'done', 'failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mark URL as done/failed and update timestamps
CREATE OR REPLACE FUNCTION update_url_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER url_queue_updated_at
    BEFORE UPDATE ON url_queue
    FOR EACH ROW EXECUTE PROCEDURE update_url_queue_updated_at();

-- Claim next N pending URLs (for workers)
CREATE OR REPLACE FUNCTION claim_pending_urls(
    worker_id TEXT,
    batch_size INT DEFAULT 10,
    max_retries INT DEFAULT 3
)
RETURNS SETOF url_queue AS $$
BEGIN
    RETURN QUERY
    UPDATE url_queue AS u
    SET status = 'in_progress', claimed_at = now(), claimed_by = worker_id
    FROM (
        SELECT id FROM url_queue
        WHERE status = 'pending' AND retries < max_retries
        ORDER BY priority DESC, id
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    ) AS sub
    WHERE u.id = sub.id
    RETURNING u.*;
END;
$$ LANGUAGE plpgsql;
