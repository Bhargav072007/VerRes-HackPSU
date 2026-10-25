CREATE TABLE shares (
    token text PRIMARY KEY CHECK (token ~ '^[A-Za-z0-9_-]{22}$'),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    view_count bigint NOT NULL DEFAULT 0 CHECK (view_count >= 0)
);
CREATE INDEX shares_job ON shares (job_id);

-- Separate admission receipts keep uploader IPs out of share/report payloads.
CREATE TABLE share_creations (
    token text PRIMARY KEY REFERENCES shares(token) ON DELETE CASCADE,
    ip_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX share_creations_ip_created ON share_creations (ip_hash, created_at);
