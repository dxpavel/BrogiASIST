-- BUG-006 audit: flag pro emaily co v DB tvrdí folder='BrogiASIST/*'
-- ale na IMAP serveru neexistují (datový dluh z předbug-004 období).
-- Datum: 2026-05-04

ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS imap_lost BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_email_messages_imap_lost
  ON email_messages(imap_lost) WHERE imap_lost = TRUE;
