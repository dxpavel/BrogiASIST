CREATE TABLE IF NOT EXISTS omnifocus_tasks (
    id              SERIAL PRIMARY KEY,
    source_type     VARCHAR DEFAULT 'omnifocus',
    source_id       VARCHAR NOT NULL UNIQUE,       -- OmniFocus task ID
    name            VARCHAR NOT NULL,
    project         VARCHAR,
    status          VARCHAR,                        -- available, next, blocked, due_soon, overdue, completed, dropped
    flagged         BOOLEAN DEFAULT FALSE,
    due_at          TIMESTAMPTZ,
    defer_at        TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    modified_at     TIMESTAMPTZ,
    tags            JSONB DEFAULT '[]',
    note            TEXT,
    in_inbox        BOOLEAN DEFAULT FALSE,
    raw_payload     JSONB,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,
    status_proc     VARCHAR DEFAULT 'new'          -- new / analyzed / ignored
);

CREATE INDEX IF NOT EXISTS idx_omnifocus_tasks_status ON omnifocus_tasks(status);
CREATE INDEX IF NOT EXISTS idx_omnifocus_tasks_due ON omnifocus_tasks(due_at) WHERE due_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_omnifocus_tasks_flagged ON omnifocus_tasks(flagged) WHERE flagged = TRUE;
