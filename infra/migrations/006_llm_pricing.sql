ALTER TABLE llm_usage ADD COLUMN estimated boolean NOT NULL DEFAULT false;
ALTER TABLE llm_usage ADD COLUMN legacy_unknown boolean NOT NULL DEFAULT false;
-- Token usage was not retained: preserve these receipts without inventing spend.
UPDATE llm_usage SET legacy_unknown = true WHERE cost_usd IS NULL;
