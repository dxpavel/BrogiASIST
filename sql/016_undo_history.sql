-- M2: 2undo (TTL 1h) — vratitelnost poslední akce
-- Per docs/brogiasist-semantics-v1.md sekce 3 + handoff M2
-- Datum: 2026-05-04

-- last_action — poslední akce kterou Pavel kliknul (nebo auto)
-- last_action_at — kdy se akce stala (TTL 1h check)
-- last_action_payload — data potřebná pro reverzi:
--   {prev_folder, prev_status, prev_task_status, prev_is_spam, sender_for_rule_delete, ...}
-- rem_event_id, cal_event_id — pro REM/CAL inverze (analogicky k of_task_id z H2)

ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS last_action          VARCHAR(16),
  ADD COLUMN IF NOT EXISTS last_action_at       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_action_payload  JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS rem_event_id         VARCHAR(128),
  ADD COLUMN IF NOT EXISTS cal_event_id         VARCHAR(128);

-- Partial index pro rychlé vyhledávání emailů s nedávnou akcí (TTL window)
CREATE INDEX IF NOT EXISTS idx_email_messages_last_action_at
  ON email_messages (last_action_at)
  WHERE last_action_at IS NOT NULL;
