-- Current receipts are keyed independently of the append-only SSE journal.
-- External paper/source row IDs are not required to form a valid relational graph.
CREATE TABLE job_results (
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    type text NOT NULL,
    row_id text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (job_id, type, row_id)
);
