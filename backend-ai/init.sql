-- SPDX-FileCopyrightText: 2026 AlitaBernachot
--
-- SPDX-License-Identifier: MIT

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    agent_name TEXT,
    data JSONB NOT NULL DEFAULT '{}',
    hash_prev TEXT NOT NULL,
    hash_current TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_session ON audit_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);

CREATE TABLE IF NOT EXISTS long_term_memory (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    fact_text TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ltm_session ON long_term_memory(session_id);
