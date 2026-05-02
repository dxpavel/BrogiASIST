-- 012_mail_indexed.sql — sloupce pro Apple Mail index check
-- mail_indexed: TRUE = Mail.app email má, FALSE = nemá, NULL = nezkontrolováno
ALTER TABLE email_messages ADD COLUMN IF NOT EXISTS mail_indexed BOOLEAN DEFAULT NULL;
ALTER TABLE email_messages ADD COLUMN IF NOT EXISTS mail_indexed_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_email_mail_indexed
    ON email_messages(mail_indexed) WHERE mail_indexed IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_mail_indexed_checked_at
    ON email_messages(mail_indexed_checked_at);
</content>