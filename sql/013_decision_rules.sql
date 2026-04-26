-- Blocker C: decision_rules engine
-- Konfigurovatelný rozhodovací stroj pro klasifikaci emailů.
-- Pravidla jsou v DB (lze upravit přes WebUI bez deploye).
-- Engine je v services/ingest/decision_engine.py — čte enabled pravidla,
-- aplikuje je v pořadí priority ASC, končí na první pravidle s action_type='end'.
--
-- Per docs/brogiasist-semantics-v1.md sekce 5 a 6.

CREATE TABLE IF NOT EXISTS decision_rules (
  id              SERIAL PRIMARY KEY,
  priority        INTEGER NOT NULL,
  rule_name       VARCHAR(64) UNIQUE NOT NULL,
  condition_type  VARCHAR(32) NOT NULL,
                  -- 'header': raw_payload.headers[<name>] {exists|equals|contains}
                  -- 'group': sender ve skupině z apple_contacts.groups
                  -- 'chroma': cosine match v ChromaDB email_actions
                  -- 'sender': exact from_address match
                  -- 'ai_fallback': default (vždy match, nikdy končí pipeline)
  condition_value JSONB NOT NULL,
  action_type     VARCHAR(32) NOT NULL,
                  -- 'end': end pipeline + apply (typ/action/flags)
                  -- 'flag': set flags + continue
                  -- 'apply_remembered': aplikovat akci z chroma + end
                  -- 'run_llama': run AI klasifikace (nikdy končí pipeline)
  action_value    JSONB NOT NULL,
  enabled         BOOLEAN NOT NULL DEFAULT TRUE,
  description     TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_rules_priority
  ON decision_rules(priority) WHERE enabled = TRUE;

-- 9 default pravidel
INSERT INTO decision_rules (priority, rule_name, condition_type, condition_value, action_type, action_value, description) VALUES
  (5,  'self_sent',
   'header', '{"header":"X-Brogi-Auto","operator":"exists"}'::jsonb,
   'end',    '{"reason":"bot_reply","skip":true}'::jsonb,
   'Bot vlastní reply (X-Brogi-Auto header) — přeskočit klasifikaci'),

  (10, 'header_list',
   'header', '{"header":"List-Id","operator":"exists"}'::jsonb,
   'end',    '{"typ":"LIST","action":"2hotovo","status":"ZPRACOVANY"}'::jsonb,
   'Mailing list (RFC 2369 List-Id) → TYP=LIST, auto 2hotovo'),

  (20, 'header_encrypted',
   'header', '{"header":"Content-Type","operator":"contains","value":"multipart/encrypted"}'::jsonb,
   'end',    '{"typ":"ENCRYPTED"}'::jsonb,
   'S/MIME nebo PGP — bot ignoruje, Pavel rozhodne ručně'),

  (30, 'header_oof',
   'header', '{"header":"Auto-Submitted","operator":"equals","value":"auto-replied"}'::jsonb,
   'end',    '{"typ":"INFO"}'::jsonb,
   'Out-of-office auto-reply → TYP=INFO, žádná akce'),

  (40, 'header_bounce',
   'header', '{"header":"Auto-Submitted","operator":"equals","value":"auto-generated"}'::jsonb,
   'end',    '{"typ":"ERROR"}'::jsonb,
   'Bounce / DSN (delivery status notification) → TYP=ERROR'),

  (50, 'group_vip',
   'group',  '{"groups":["VIP ⏰"]}'::jsonb,
   'flag',   '{"force_tg_notify":true,"no_auto_action":true}'::jsonb,
   'Sender ve skupině VIP — vždy TG, NIKDY auto-action'),

  (60, 'chroma_match',
   'chroma', '{"threshold":0.15}'::jsonb,
   'apply_remembered', '{}'::jsonb,
   'Pokud cosine < 0.15 v Chroma email_actions → aplikuj zapamatovanou akci'),

  (70, 'sender_personal',
   'group',  '{"groups":["KAMARADI  🥂","MEDVEDI 🧸","RODINA 🛠","MOTO 🏍","TRAVEL 🗺","FOCENI 📸"]}'::jsonb,
   'flag',   '{"is_personal":true,"no_auto_konstruktivni":true}'::jsonb,
   'Osobní kontakt — flag is_personal, žádná auto-konstruktivní akce'),

  (80, 'ai_fallback',
   'ai_fallback', '{}'::jsonb,
   'run_llama',   '{}'::jsonb,
   'Default — pokud žádné pravidlo výše nematchnulo, spustit Llama klasifikaci')
ON CONFLICT (rule_name) DO NOTHING;
