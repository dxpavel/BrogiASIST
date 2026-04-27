-- 015_decision_flags.sql
-- H3: Persist decision_engine flagů do email_messages
-- (is_personal už existuje z 014_email_semantics_v1.sql)
--
-- Důvod: classify_emails má decision dict z evaluate_email() ale flagy
-- zahodí. Po H3 se persistují → notify_emails je číst může (visual
-- indikátory) + budoucí silent auto-apply gating.

ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS force_tg_notify       boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS no_auto_action        boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS no_auto_konstruktivni boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS matched_rules         text[],
  ADD COLUMN IF NOT EXISTS matched_groups        text[];

CREATE INDEX IF NOT EXISTS idx_email_personal
  ON email_messages(is_personal) WHERE is_personal = TRUE;

CREATE INDEX IF NOT EXISTS idx_email_force_tg
  ON email_messages(force_tg_notify) WHERE force_tg_notify = TRUE;

COMMENT ON COLUMN email_messages.force_tg_notify       IS 'VIP rule flag — vždy posílat TG notifikaci (placeholder, dnes no-op).';
COMMENT ON COLUMN email_messages.no_auto_action        IS 'Skip auto-spam-trash i při high confidence — Pavel rozhodne ručně.';
COMMENT ON COLUMN email_messages.no_auto_konstruktivni IS 'Gating pro budoucí silent auto-apply konstruktivních akcí (2of/2cal/2note/2rem).';
COMMENT ON COLUMN email_messages.matched_rules         IS 'Audit: které decision_rules pravidlo(a) matchla.';
COMMENT ON COLUMN email_messages.matched_groups        IS 'Apple Contacts skupiny odesílatele (z group rules).';
