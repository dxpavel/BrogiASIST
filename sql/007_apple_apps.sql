-- Apple Notes
CREATE TABLE IF NOT EXISTS apple_notes (
    id          SERIAL PRIMARY KEY,
    source_type VARCHAR DEFAULT 'apple_notes',
    source_id   VARCHAR NOT NULL UNIQUE,
    name        VARCHAR,
    body        TEXT,
    modified_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    status      VARCHAR DEFAULT 'new'
);

-- Apple Reminders
CREATE TABLE IF NOT EXISTS apple_reminders (
    id          SERIAL PRIMARY KEY,
    source_type VARCHAR DEFAULT 'apple_reminders',
    source_id   VARCHAR NOT NULL UNIQUE,
    name        VARCHAR NOT NULL,
    list_name   VARCHAR,
    body        TEXT,
    flagged     BOOLEAN DEFAULT FALSE,
    completed   BOOLEAN DEFAULT FALSE,
    due_at      TIMESTAMPTZ,
    remind_at   TIMESTAMPTZ,
    modified_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    status      VARCHAR DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON apple_reminders(due_at) WHERE due_at IS NOT NULL;

-- Apple Contacts
CREATE TABLE IF NOT EXISTS apple_contacts (
    id          SERIAL PRIMARY KEY,
    source_type VARCHAR DEFAULT 'apple_contacts',
    source_id   VARCHAR NOT NULL UNIQUE,
    first_name  VARCHAR,
    last_name   VARCHAR,
    organization VARCHAR,
    emails      JSONB DEFAULT '[]',
    phones      JSONB DEFAULT '[]',
    modified_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contacts_name ON apple_contacts(last_name, first_name);

-- Calendar Events
CREATE TABLE IF NOT EXISTS calendar_events (
    id          SERIAL PRIMARY KEY,
    source_type VARCHAR DEFAULT 'calendar',
    source_id   VARCHAR NOT NULL UNIQUE,
    summary     VARCHAR,
    calendar    VARCHAR,
    start_at    TIMESTAMPTZ,
    end_at      TIMESTAMPTZ,
    all_day     BOOLEAN DEFAULT FALSE,
    location    VARCHAR,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    status      VARCHAR DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_at);
