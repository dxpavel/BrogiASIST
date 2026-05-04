-- L1: Email Semantics v1 status backfill
-- Per docs/brogiasist-semantics-v1.md sekce 14: 5 stavů
--   NOVÝ / PŘEČTENÝ / ČEKAJÍCÍ / ZPRACOVANÝ / SMAZANÝ
-- Datum: 2026-05-04
--
-- Mapping legacy → nové:
--   'new' / 'classified'  → 'NOVÝ'
--   'reviewed' (is_spam=FALSE) → 'ZPRACOVANÝ'
--   'reviewed' (is_spam=TRUE)  → 'SMAZANÝ'
--   'ignored'             → 'SMAZANÝ'
--   is_spam=TRUE          → 'SMAZANÝ' (override pokud není reviewed/ignored)
--
-- ČEKAJÍCÍ status se zatím necpe — task_status='ČEKÁ-NA-ODPOVĚĎ' v DB
-- + dashboard ho odvozuje. Po této migraci kód píše rovnou nové hodnoty.

-- 1. spam emaily → SMAZANÝ
UPDATE email_messages SET status = 'SMAZANÝ'
WHERE is_spam = TRUE;

-- 2. legacy 'reviewed' (Pavel akčně rozhodl) → ZPRACOVANÝ
UPDATE email_messages SET status = 'ZPRACOVANÝ'
WHERE status = 'reviewed' AND is_spam = FALSE;

-- 3. legacy 'ignored' → SMAZANÝ
UPDATE email_messages SET status = 'SMAZANÝ'
WHERE status = 'ignored';

-- 4. legacy 'new' / 'classified' → NOVÝ
UPDATE email_messages SET status = 'NOVÝ'
WHERE status IN ('new', 'classified');

-- 5. cokoli ostatní (NULL, neznámé) → NOVÝ jako fallback
UPDATE email_messages SET status = 'NOVÝ'
WHERE status IS NULL OR status NOT IN ('NOVÝ', 'PŘEČTENÝ', 'ČEKAJÍCÍ', 'ZPRACOVANÝ', 'SMAZANÝ');
