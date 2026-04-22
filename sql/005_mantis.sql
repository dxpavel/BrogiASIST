-- BrogiASIST — MantisBT mirror tabulka
-- Migrace: 005_mantis.sql
-- Datum: 2026-04-23

CREATE TABLE IF NOT EXISTS mantis_issues (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(32)  NOT NULL DEFAULT 'mantis',
    source_id       VARCHAR(64)  NOT NULL UNIQUE,  -- MantisBT issue ID
    raw_payload     JSONB        NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(32)  NOT NULL DEFAULT 'new',
    processed_at    TIMESTAMPTZ,

    project_id      INTEGER,
    project_name    VARCHAR(256),
    summary         VARCHAR(1024),
    description     TEXT,
    issue_status    VARCHAR(64),
    priority        VARCHAR(64),
    severity        VARCHAR(64),
    reporter        VARCHAR(256),
    assigned_to     VARCHAR(256),
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mantis_status     ON mantis_issues (status);
CREATE INDEX IF NOT EXISTS idx_mantis_project    ON mantis_issues (project_id);
CREATE INDEX IF NOT EXISTS idx_mantis_updated    ON mantis_issues (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mantis_istatus    ON mantis_issues (issue_status);
