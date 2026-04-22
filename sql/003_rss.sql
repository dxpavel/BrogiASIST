-- BrogiASIST — RSS mirror tabulka
-- Migrace: 003_rss.sql
-- Datum: 2026-04-22

CREATE TABLE IF NOT EXISTS rss_articles (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(32)  NOT NULL DEFAULT 'rss',
    source_id       VARCHAR(512) NOT NULL UNIQUE,  -- The Old Reader item ID
    raw_payload     JSONB        NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(32)  NOT NULL DEFAULT 'new',
    processed_at    TIMESTAMPTZ,

    feed_id         VARCHAR(256),
    feed_title      VARCHAR(512),
    title           VARCHAR(1024),
    url             VARCHAR(2048),
    author          VARCHAR(256),
    published_at    TIMESTAMPTZ,
    is_read         BOOLEAN      NOT NULL DEFAULT FALSE,
    is_starred      BOOLEAN      NOT NULL DEFAULT FALSE,
    summary         TEXT
);

CREATE INDEX IF NOT EXISTS idx_rss_status       ON rss_articles (status);
CREATE INDEX IF NOT EXISTS idx_rss_published    ON rss_articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_feed         ON rss_articles (feed_id);
CREATE INDEX IF NOT EXISTS idx_rss_read         ON rss_articles (is_read);
