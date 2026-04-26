-- BrogiASIST — Claude sender verdicts cache
-- Vytvořeno: 2026-04-26
-- Tabulka pro cachování výsledků Claude Haiku spam verifikace (jeden záznam na odesílatele)

CREATE TABLE IF NOT EXISTS claude_sender_verdicts (
    email TEXT PRIMARY KEY,
    is_spam BOOLEAN NOT NULL,
    reason TEXT,
    verified_at TIMESTAMP DEFAULT NOW()
);
