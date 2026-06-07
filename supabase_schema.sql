-- ============================================================
-- github-slm-reviewer  Supabase schema
-- Run once in the Supabase SQL editor to set up the database.
-- ============================================================

-- ----------------------------------------------------------------
-- pr_states: one row per unique (owner, repo, pr_number)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pr_states (
    pr_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner           TEXT        NOT NULL,
    repo            TEXT        NOT NULL,
    pr_number       INTEGER     NOT NULL,
    iteration       INTEGER     NOT NULL DEFAULT 0,
    open_issues     INTEGER     NOT NULL DEFAULT 0,
    resolved_issues INTEGER     NOT NULL DEFAULT 0,
    last_sha        TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pr_states_unique UNIQUE (owner, repo, pr_number)
);

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER pr_states_updated_at
    BEFORE UPDATE ON pr_states
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------
-- issues: one row per detected issue per PR
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS issues (
    issue_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_id       UUID        NOT NULL REFERENCES pr_states(pr_id) ON DELETE CASCADE,
    filename    TEXT        NOT NULL,
    line        INTEGER     NOT NULL,
    severity    TEXT        NOT NULL CHECK (severity    IN ('critical', 'warning', 'suggestion')),
    category    TEXT        NOT NULL CHECK (category    IN ('bug', 'security', 'performance', 'style', 'logic')),
    message     TEXT        NOT NULL,
    fix         TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'fixed', 'wont_fix')),
    first_sha   TEXT        NOT NULL,
    comment_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER issues_updated_at
    BEFORE UPDATE ON issues
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_issues_pr_id        ON issues (pr_id);
CREATE INDEX IF NOT EXISTS idx_issues_status       ON issues (status);
CREATE INDEX IF NOT EXISTS idx_issues_pr_id_status ON issues (pr_id, status);
