-- Blocker D1: schema rozšíření pro Email Semantics v1
-- Per docs/brogiasist-semantics-v1.md sekce 6.
--
-- Přidává:
-- 1. RFC 5322 threading sloupce (message_id, in_reply_to, thread_id)
-- 2. Email ↔ OmniFocus link (of_task_id, of_linked_at)
-- 3. is_personal flag (z decision_rules sender_personal pravidla)
-- 4. pending_actions queue (degraded mode pro Apple Bridge offline)
--
-- POZNÁMKA: existující 25 emailů zůstává nedotčených — Pavel rozhodl
-- "nemigrujeme obsah, je to vývoj a zatím mi nic nechybí". Nové sloupce
-- jsou nullable / default, takže staré řádky zůstanou platné.

-- ===== email_messages — threading + OF link + flags =====

ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS message_id   VARCHAR(998),  -- RFC 5322 §3.6.4 max length
  ADD COLUMN IF NOT EXISTS in_reply_to  VARCHAR(998),
  ADD COLUMN IF NOT EXISTS thread_id    UUID,
  ADD COLUMN IF NOT EXISTS of_task_id   VARCHAR(128),
  ADD COLUMN IF NOT EXISTS of_linked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS is_personal  BOOLEAN NOT NULL DEFAULT FALSE;

-- thread_id unikátní per thread — root message má thread_id = vlastní id
-- Indexy:
CREATE INDEX IF NOT EXISTS idx_email_messages_message_id
  ON email_messages(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_messages_thread_id
  ON email_messages(thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_messages_of_task_id
  ON email_messages(of_task_id) WHERE of_task_id IS NOT NULL;

-- ===== pending_actions — fronta akcí pro degraded mode =====
-- Apple Bridge může být dočasně offline (Mac Studio sleep, Apple update,
-- crash). Místo ztráty in-flight akcí (2of, 2cal, 2note, 2rem) je zapíšeme
-- do fronty. Po obnovení Bridge je worker zpracuje throttle 2s/akce.
--
-- Per spec sekce 9.

CREATE TABLE IF NOT EXISTS pending_actions (
  id          SERIAL PRIMARY KEY,
  email_id    UUID NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
  action      VARCHAR(16) NOT NULL,   -- 2of, 2cal, 2note, 2rem
  action_data JSONB DEFAULT '{}'::jsonb,  -- payload pro Apple Bridge call
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ,
  last_error  TEXT,
  status      VARCHAR(16) NOT NULL DEFAULT 'pending'
              -- 'pending' / 'processing' / 'done' / 'failed'
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_status_created
  ON pending_actions(status, created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_pending_actions_email
  ON pending_actions(email_id);

-- ===== Komentáře =====

COMMENT ON COLUMN email_messages.message_id IS
  'RFC 5322 Message-ID header — pro threading + dedup';
COMMENT ON COLUMN email_messages.in_reply_to IS
  'RFC 5322 In-Reply-To header — odkaz na rodičovský message_id v threadu';
COMMENT ON COLUMN email_messages.thread_id IS
  'UUID rootu threadu (= id prvního emailu v něm). Nový email bez parent dostane thread_id = self.id';
COMMENT ON COLUMN email_messages.of_task_id IS
  'OmniFocus task ID po klepnutí na 2of (přes Apple Bridge POST /omnifocus/add_task)';
COMMENT ON COLUMN email_messages.is_personal IS
  'Sender ve skupině KAMARADI/MEDVEDI/RODINA/MOTO/TRAVEL/FOCENI — z decision_rules sender_personal';

COMMENT ON TABLE pending_actions IS
  'Fronta in-flight akcí pro Apple Bridge degraded mode. Worker zpracuje throttle 2s.';
