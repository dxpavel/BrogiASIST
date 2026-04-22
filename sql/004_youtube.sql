-- BrogiASIST — YouTube mirror tabulka
-- Migrace: 004_youtube.sql
-- Datum: 2026-04-22

CREATE TABLE IF NOT EXISTS youtube_videos (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(32)  NOT NULL DEFAULT 'youtube',
    source_id       VARCHAR(64)  NOT NULL UNIQUE,  -- YouTube video ID
    raw_payload     JSONB        NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(32)  NOT NULL DEFAULT 'new',
    processed_at    TIMESTAMPTZ,

    channel_id      VARCHAR(64)  NOT NULL,
    channel_title   VARCHAR(512),
    title           VARCHAR(1024),
    url             VARCHAR(512),
    published_at    TIMESTAMPTZ,
    duration_sec    INTEGER,
    view_count      BIGINT,
    description     TEXT
);

CREATE INDEX IF NOT EXISTS idx_yt_status        ON youtube_videos (status);
CREATE INDEX IF NOT EXISTS idx_yt_published     ON youtube_videos (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_channel       ON youtube_videos (channel_id);
