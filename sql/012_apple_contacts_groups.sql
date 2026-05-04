-- Blocker B: skupiny kontaktů z Apple Contacts jako orthogonal signál
-- pro klasifikaci emailů (per docs/brogiasist-semantics-v1.md sekce 4).
-- Skupina se nastaví per email odesílatele a ovlivňuje:
--   - VIP → vždy TG, žádná auto-action
--   - osobní (KAMARADI/MEDVEDI/RODINA/MOTO/TRAVEL/FOCENI) → flag is_personal
--   - firma (DXP/MBANK/JOBS/...) → flag firma=<skupina>
--   - dodavatel/eshop/finance → auto-action povolena
--   - BLOCKED → BrogiASIST ignoruje (osobní seznam Pavla mimo systém)

ALTER TABLE apple_contacts
  ADD COLUMN IF NOT EXISTS groups JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_apple_contacts_groups
  ON apple_contacts USING gin(groups);
