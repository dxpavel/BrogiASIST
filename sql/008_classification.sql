-- Email klasifikace + pravidla

ALTER TABLE email_messages
    ADD COLUMN IF NOT EXISTS firma        VARCHAR(64),
    ADD COLUMN IF NOT EXISTS typ          VARCHAR(64),
    ADD COLUMN IF NOT EXISTS task_status  VARCHAR(64),
    ADD COLUMN IF NOT EXISTS is_spam      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ai_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS human_reviewed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_email_spam  ON email_messages (is_spam);
CREATE INDEX IF NOT EXISTS idx_email_firma ON email_messages (firma);
CREATE INDEX IF NOT EXISTS idx_email_typ   ON email_messages (typ);

-- Naučená pravidla (spam / firma / typ)
CREATE TABLE IF NOT EXISTS classification_rules (
    id           SERIAL PRIMARY KEY,
    rule_type    VARCHAR(32) NOT NULL,  -- 'spam', 'firma', 'typ'
    match_field  VARCHAR(32) NOT NULL,  -- 'from_address', 'subject_contains', 'domain'
    match_value  VARCHAR(512) NOT NULL,
    result_value VARCHAR(64) NOT NULL,
    confidence   FLOAT NOT NULL DEFAULT 1.0,
    hit_count    INT NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_type, match_field, match_value)
);
