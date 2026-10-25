# Recorded demos

Real recordings belong at `paper1.jsonl`, `paper2.jsonl`, and `paper3.jsonl`.
They are intentionally absent until an operator records real completed jobs with
`scripts/record_fixture.py`. No synthetic receipts are substituted when missing.
Each JSONL envelope includes `input_sha256` to bind it to the uploaded demo PDF.

The existing `fixtures/events/paper1.jsonl` and web fixtures are independent test
artifacts and must not be copied here as real recordings.
