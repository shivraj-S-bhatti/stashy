-- Stashy Spatial Ingestion Fabric schema
-- Optimized for agentic frontier expansion and AI infra observability.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE url_queue (
    id             BIGSERIAL PRIMARY KEY,
    url            TEXT NOT NULL UNIQUE,
    status         TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'done', 'failed')),
    priority       INT NOT NULL DEFAULT 0,
    geo_score      REAL NOT NULL DEFAULT 0.0 CHECK (geo_score >= 0.0 AND geo_score <= 1.0),
    source         TEXT NOT NULL DEFAULT 'seed',
    depth          INT NOT NULL DEFAULT 0 CHECK (depth >= 0),
    parent_url_id  BIGINT REFERENCES url_queue(id) ON DELETE SET NULL,
    retries        INT NOT NULL DEFAULT 0,
    max_retries    INT NOT NULL DEFAULT 3,
    claimed_at     TIMESTAMPTZ,
    claimed_by     TEXT,
    last_scored_at TIMESTAMPTZ,
    processed_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    error          TEXT
);

CREATE INDEX idx_url_queue_pending_rank
    ON url_queue (status, (priority + ((geo_score * 100)::INT)) DESC, id)
    WHERE status = 'pending';

CREATE INDEX idx_url_queue_claimed
    ON url_queue (claimed_by, claimed_at)
    WHERE status = 'in_progress';

CREATE INDEX idx_url_queue_parent
    ON url_queue (parent_url_id);

CREATE INDEX idx_url_queue_source_depth
    ON url_queue (source, depth, created_at DESC);


CREATE TABLE raw_pages (
    id            BIGSERIAL PRIMARY KEY,
    url_id        BIGINT NOT NULL REFERENCES url_queue(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    html          TEXT,
    status_code   INT,
    content_type  TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url_id)
);

CREATE INDEX idx_raw_pages_url_id ON raw_pages (url_id);


CREATE TABLE extractions (
    id            BIGSERIAL PRIMARY KEY,
    url_id        BIGINT NOT NULL REFERENCES url_queue(id) ON DELETE CASCADE,
    page_id       BIGINT NOT NULL REFERENCES raw_pages(id) ON DELETE CASCADE,
    schema_name   TEXT,
    payload       JSONB NOT NULL,
    confidence    NUMERIC(5, 4),
    geo_score     REAL,
    signals       JSONB,
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url_id)
);

CREATE INDEX idx_extractions_url_id ON extractions (url_id);
CREATE INDEX idx_extractions_schema ON extractions (schema_name);
CREATE INDEX idx_extractions_payload_gin ON extractions USING GIN (payload);
CREATE INDEX idx_extractions_signals_gin ON extractions USING GIN (signals);
CREATE INDEX idx_extractions_geo_score ON extractions (geo_score);


CREATE TABLE worker_metrics (
    id                BIGSERIAL PRIMARY KEY,
    worker_id         TEXT NOT NULL,
    processed_count   INT NOT NULL,
    failed_count      INT NOT NULL,
    frontier_enqueued INT NOT NULL,
    avg_latency_ms    NUMERIC(10, 2),
    p95_latency_ms    NUMERIC(10, 2),
    queue_depth       INT,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_worker_metrics_worker_time ON worker_metrics (worker_id, recorded_at DESC);


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
        SELECT id
        FROM url_queue
        WHERE status = 'pending' AND retries < max_retries
        ORDER BY (priority + ((geo_score * 100)::INT)) DESC, retries ASC, id
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    ) AS sub
    WHERE u.id = sub.id
    RETURNING u.*;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION upsert_discovered_url(
    p_parent_url_id BIGINT,
    p_url TEXT,
    p_priority INT DEFAULT 0,
    p_geo_score REAL DEFAULT 0.0,
    p_source TEXT DEFAULT 'frontier',
    p_depth INT DEFAULT 0
)
RETURNS BOOLEAN AS $$
DECLARE
    inserted BOOLEAN;
BEGIN
    INSERT INTO url_queue (url, priority, geo_score, source, depth, parent_url_id)
    VALUES (
        p_url,
        p_priority,
        LEAST(1.0, GREATEST(0.0, p_geo_score)),
        p_source,
        GREATEST(0, p_depth),
        p_parent_url_id
    )
    ON CONFLICT (url) DO UPDATE
    SET priority = GREATEST(url_queue.priority, EXCLUDED.priority),
        geo_score = GREATEST(url_queue.geo_score, EXCLUDED.geo_score),
        parent_url_id = COALESCE(url_queue.parent_url_id, EXCLUDED.parent_url_id),
        depth = LEAST(url_queue.depth, EXCLUDED.depth),
        source = CASE
            WHEN url_queue.source = 'seed' THEN url_queue.source
            ELSE EXCLUDED.source
        END,
        status = CASE
            WHEN url_queue.status IN ('done', 'failed') THEN 'pending'
            ELSE url_queue.status
        END,
        retries = CASE
            WHEN url_queue.status IN ('done', 'failed') THEN 0
            ELSE url_queue.retries
        END,
        claimed_at = CASE
            WHEN url_queue.status IN ('done', 'failed') THEN NULL
            ELSE url_queue.claimed_at
        END,
        claimed_by = CASE
            WHEN url_queue.status IN ('done', 'failed') THEN NULL
            ELSE url_queue.claimed_by
        END,
        updated_at = now()
    RETURNING (xmax = 0) INTO inserted;

    RETURN inserted;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION record_worker_metrics(
    p_worker_id TEXT,
    p_processed_count INT,
    p_failed_count INT,
    p_frontier_enqueued INT,
    p_avg_latency_ms NUMERIC,
    p_p95_latency_ms NUMERIC,
    p_queue_depth INT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO worker_metrics (
        worker_id,
        processed_count,
        failed_count,
        frontier_enqueued,
        avg_latency_ms,
        p95_latency_ms,
        queue_depth
    )
    VALUES (
        p_worker_id,
        p_processed_count,
        p_failed_count,
        p_frontier_enqueued,
        p_avg_latency_ms,
        p_p95_latency_ms,
        p_queue_depth
    );
END;
$$ LANGUAGE plpgsql;
