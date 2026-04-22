-- BrogiASIST — základní schéma
-- Migrace: 001_init.sql
-- Datum: 2026-04-22

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Konfigurace systému
CREATE TABLE IF NOT EXISTS config (
    key         VARCHAR(128) PRIMARY KEY,
    value       TEXT         NOT NULL,
    module      VARCHAR(64),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Zdroje dat (mailboxy, RSS kanály, Mantis endpointy, ...)
CREATE TABLE IF NOT EXISTS sources (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(32)  NOT NULL,
    name        VARCHAR(256) NOT NULL,
    config      JSONB        NOT NULL DEFAULT '{}',
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Sdílený action log — každá akce všech modulů
CREATE TABLE IF NOT EXISTS actions (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(32)  NOT NULL,
    source_id       VARCHAR(512) NOT NULL,
    action_type     VARCHAR(64)  NOT NULL,
    action_payload  JSONB        NOT NULL DEFAULT '{}',
    status          VARCHAR(32)  NOT NULL DEFAULT 'pending',
    confirmed_by    VARCHAR(64),
    confirmed_at    TIMESTAMPTZ,
    executed_at     TIMESTAMPTZ,
    result          JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actions_source ON actions (source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions (status);

-- Session paměť
CREATE TABLE IF NOT EXISTS sessions (
    id              VARCHAR(64)  PRIMARY KEY,
    status          VARCHAR(32)  NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

-- Přílohy
CREATE TABLE IF NOT EXISTS attachments (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type      VARCHAR(32)  NOT NULL,
    source_record_id UUID         NOT NULL,
    filename         VARCHAR(512) NOT NULL,
    storage_path     VARCHAR(1024) NOT NULL,
    mime_type        VARCHAR(128),
    size_bytes       INTEGER,
    ingested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attachments_record ON attachments (source_type, source_record_id);

-- Výchozí konfigurace
INSERT INTO config (key, value, module) VALUES
    ('email.retention_days',     '730',        'email'),
    ('rss.retention_days',       '30',         'rss'),
    ('mantis.escalation_days',   '7',          'mantis'),
    ('youtube.retention_days',   '90',         'youtube'),
    ('dedup.email.strategy',     'message_id', 'email'),
    ('dedup.rss.strategy',       'url_hash',   'rss')
ON CONFLICT (key) DO NOTHING;
