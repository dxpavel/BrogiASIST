-- M1 final: TG text-input reply state machine
-- Pavel klikne 2reply → bot uloží pending state → Pavel pošle TG text →
-- bot zavolá send_reply(body=text) + clear state.
-- Datum: 2026-05-04

CREATE TABLE IF NOT EXISTS tg_pending_replies (
    chat_id      BIGINT       NOT NULL,
    email_id     UUID         NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
    started_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ttl_minutes  INTEGER      NOT NULL DEFAULT 30,
    PRIMARY KEY (chat_id)
    -- Per chat jen jeden pending reply naráz. Druhé kliknutí 2reply
    -- nahradí předchozí (Pavel rozhodl změnit cíl).
);

-- Cleanup TTL old pendings (manuálně nebo přes scheduler job v budoucnu)
-- DELETE FROM tg_pending_replies
-- WHERE started_at < NOW() - (ttl_minutes || ' minutes')::interval;
