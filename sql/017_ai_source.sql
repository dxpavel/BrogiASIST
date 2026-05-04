-- M5 session 2: ai_source tracking pro Llama → Claude cascade
-- Per docs/feature-specs/FEATURE-AI-CASCADE-v1.md sekce 5.1
-- Datum: 2026-05-04
--
-- Hodnoty:
--   'llama'                 — Llama klasifikoval s confidence >= threshold
--   'llama_low_confidence'  — Llama confidence < threshold, čekal by Claude (session 2 placeholder)
--   'claude'                — Claude verify cascade (session 3, nasazeno později)
--   'rule'                  — decision_rules end (header_list, header_encrypted, ...)
--   'chroma'                — chroma_match apply_remembered

ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS ai_source VARCHAR(32) DEFAULT 'llama';

-- Partial index pro rychlý audit "kolik emailů by chtělo Claude"
CREATE INDEX IF NOT EXISTS idx_email_messages_ai_source_low_conf
  ON email_messages (ai_source)
  WHERE ai_source = 'llama_low_confidence';
