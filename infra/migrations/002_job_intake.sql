ALTER TABLE jobs ADD COLUMN input jsonb NOT NULL DEFAULT '{}';
ALTER TABLE jobs ADD COLUMN client_ip text NOT NULL DEFAULT '';
CREATE INDEX jobs_ip_created ON jobs (client_ip, created_at);
CREATE INDEX jobs_running ON jobs (status) WHERE status = 'RUNNING';
