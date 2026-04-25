CREATE TABLE IF NOT EXISTS imap_status (
    account         TEXT PRIMARY KEY,
    login_ok        BOOLEAN,
    login_checked_at TIMESTAMPTZ,
    idle_state      TEXT,          -- 'active', 'reconnecting', 'error', 'no_idle'
    idle_last_seen  TIMESTAMPTZ,
    idle_last_push  TIMESTAMPTZ,
    error_msg       TEXT
);
