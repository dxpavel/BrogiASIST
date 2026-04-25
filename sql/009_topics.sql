-- 009_topics.sql — Hierarchický systém zájmů/témat pro lokální AI

CREATE TABLE topics (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,
    parent_id   INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    priority    VARCHAR(16) DEFAULT 'medium'
                    CHECK (priority IN ('high', 'medium', 'low')),
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topic_signals (
    id          SERIAL PRIMARY KEY,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    signal_type VARCHAR(32) NOT NULL
                    CHECK (signal_type IN ('positive','negative','brand','system','compatible')),
    value       VARCHAR(256) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topic_intersections (
    id          SERIAL PRIMARY KEY,
    topic_a_id  INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    topic_b_id  INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relevance   TEXT,
    score       FLOAT DEFAULT 1.0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON topic_signals(topic_id);
CREATE INDEX ON topic_intersections(topic_a_id);
CREATE INDEX ON topic_intersections(topic_b_id);
