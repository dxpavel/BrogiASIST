-- BrogiASIST — Email mirror tabulka
-- Migrace: 002_email.sql
-- Datum: 2026-04-22

CREATE TABLE IF NOT EXISTS email_messages (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(32)  NOT NULL DEFAULT 'email',
    source_id       VARCHAR(512) NOT NULL UNIQUE,  -- Message-ID hlavičky
    raw_payload     JSONB        NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(32)  NOT NULL DEFAULT 'new',
    processed_at    TIMESTAMPTZ,

    -- Denormalizované sloupce pro rychlé dotazy
    mailbox         VARCHAR(256) NOT NULL,          -- brogi@dxpsolutions.cz apod.
    from_address    VARCHAR(512),
    to_addresses    TEXT[],
    subject         VARCHAR(1024),
    sent_at         TIMESTAMPTZ,
    has_attachments BOOLEAN      NOT NULL DEFAULT FALSE,
    folder          VARCHAR(256) NOT NULL DEFAULT 'INBOX',
    imap_uid        BIGINT
);

CREATE INDEX IF NOT EXISTS idx_email_status     ON email_messages (status);
CREATE INDEX IF NOT EXISTS idx_email_mailbox    ON email_messages (mailbox);
CREATE INDEX IF NOT EXISTS idx_email_sent_at    ON email_messages (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_from       ON email_messages (from_address);
