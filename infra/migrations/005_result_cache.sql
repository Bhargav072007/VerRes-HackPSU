-- 004 is reserved for A6 shares. Never change an already applied migration.
ALTER TABLE jobs ADD COLUMN cache_key text;
ALTER TABLE jobs ADD COLUMN pipeline_version text;
ALTER TABLE jobs ADD COLUMN demo_fixture boolean NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN replay_of uuid REFERENCES jobs(id) ON DELETE SET NULL;
CREATE INDEX jobs_result_cache ON jobs (cache_key, pipeline_version, updated_at DESC)
    WHERE status IN ('COMPLETE', 'NEEDS_REVIEW') AND NOT demo_fixture;

CREATE TABLE llm_usage (
    id uuid PRIMARY KEY,
    job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
    cost_usd numeric CHECK (cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_usage_day ON llm_usage (created_at);
