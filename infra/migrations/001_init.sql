-- Contract payloads are JSONB; relational keys preserve receipt/job ownership.
CREATE TABLE jobs (
    id uuid PRIMARY KEY,
    status text NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETE', 'NEEDS_REVIEW', 'CHECK_INCOMPLETE')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE job_events (
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    seq bigint NOT NULL CHECK (seq > 0),
    type text NOT NULL CHECK (type IN ('stage', 'paper', 'existence', 'retraction', 'source',
        'support', 'claim_map', 'hidden_text', 'review', 'review_summary', 'done', 'error')),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, seq)
);
CREATE TABLE papers (
    job_id uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    id text NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE refs (
    job_id uuid NOT NULL REFERENCES papers(job_id) ON DELETE CASCADE,
    id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, id)
);
CREATE TABLE citations (
    job_id uuid NOT NULL,
    id text NOT NULL,
    reference_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, id),
    FOREIGN KEY (job_id, reference_id) REFERENCES refs(job_id, id) ON DELETE CASCADE
);
CREATE TABLE source_documents (
    job_id uuid NOT NULL,
    reference_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, reference_id),
    FOREIGN KEY (job_id, reference_id) REFERENCES refs(job_id, id) ON DELETE CASCADE
);
CREATE TABLE existence_results (
    job_id uuid NOT NULL,
    reference_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, reference_id),
    FOREIGN KEY (job_id, reference_id) REFERENCES refs(job_id, id) ON DELETE CASCADE
);
CREATE TABLE retraction_results (
    job_id uuid NOT NULL,
    reference_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, reference_id),
    FOREIGN KEY (job_id, reference_id) REFERENCES refs(job_id, id) ON DELETE CASCADE
);
CREATE TABLE support_results (
    job_id uuid NOT NULL,
    citation_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, citation_id),
    FOREIGN KEY (job_id, citation_id) REFERENCES citations(job_id, id) ON DELETE CASCADE
);
CREATE TABLE claim_nodes (
    job_id uuid NOT NULL REFERENCES papers(job_id) ON DELETE CASCADE,
    id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, id)
);
CREATE TABLE claim_edges (
    job_id uuid NOT NULL,
    source_id text NOT NULL,
    target_id text NOT NULL,
    relation text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, source_id, target_id, relation),
    FOREIGN KEY (job_id, source_id) REFERENCES claim_nodes(job_id, id) ON DELETE CASCADE,
    FOREIGN KEY (job_id, target_id) REFERENCES claim_nodes(job_id, id) ON DELETE CASCADE
);
CREATE TABLE hidden_text_findings (
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, id)
);
CREATE TABLE review_comments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    payload jsonb NOT NULL
);
CREATE TABLE human_corrections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    target_type text NOT NULL,
    target_id text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE model_runs (
    id uuid PRIMARY KEY,
    job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE provider_calls (
    id uuid PRIMARY KEY,
    job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
    provider text NOT NULL,
    status text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE http_cache (
    cache_key text PRIMARY KEY,
    payload jsonb NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE llm_cache (
    cache_key text PRIMARY KEY,
    model text NOT NULL,
    prompt_version text NOT NULL,
    payload jsonb NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE retraction_watch (
    doi text PRIMARY KEY,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
