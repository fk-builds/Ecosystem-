-- FK AI Builder — PostgreSQL (Supabase-compatible) schema
-- Loaded automatically by docker-compose init, or run manually in Supabase SQL editor.

CREATE TABLE IF NOT EXISTS canvases (
    id          TEXT PRIMARY KEY,
    version     BIGINT NOT NULL DEFAULT 1,
    state       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS canvas_versions (
    canvas_id   TEXT NOT NULL REFERENCES canvases(id) ON DELETE CASCADE,
    version     BIGINT NOT NULL,
    state       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (canvas_id, version)
);

CREATE INDEX IF NOT EXISTS idx_canvas_versions_canvas ON canvas_versions (canvas_id, created_at DESC);

-- Optional: agent memory / chat history
CREATE TABLE IF NOT EXISTS agent_messages (
    id          BIGSERIAL PRIMARY KEY,
    canvas_id   TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_messages_canvas ON agent_messages (canvas_id, created_at);
