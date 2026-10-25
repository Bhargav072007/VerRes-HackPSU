# Citation outcomes and source coverage

The public Pydantic contracts and support-label enum are unchanged. A background
or method citation retains a conservative `NEEDS_REVIEW` support label because
it has not established a supported scientific claim. Its `needs_review_reason`
uses the exact constants in `outcomes.py`. The report renders these as
**Background citation** or **Method reference** and excludes them from the
unresolved-claim count. Separate reference/retraction problems remain visible.

The evidence reviewer receives `NOT_APPLICABLE` internally for these citation
functions. This is not a new public verdict. The reviewer must still flag actual
identity or retraction issues. The raw API and JSON exports retain their original
contract labels; their reasons distinguish informational citations.

PDFs with figures or incomplete page extraction can supply identity-checked prose.
`Source.whole_source=False` prevents `NOT_SUPPORTED` even after adjudication.
Quotes can still establish support, partial support, or an explicit contradiction;
existing evidence and second-model gates remain in force.

The frozen public schema has no partial-text enum. For compatibility, body text
uses `FULL_TEXT`, qualified by a `Partial PDF text coverage:` reason and the
`Extracted text (partial coverage)` passage section. Verification recognizes both
markers and the report labels this **Extracted PDF text · partial coverage**.
API consumers must not interpret `FULL_TEXT` alone as proof of complete coverage.
Scanned/rasterized documents containing only headers remain unusable without OCR.

Model names now load from `.env` through Settings as well as process environment.
No model or API key is automatically selected. Severe findings still require an
explicitly configured eligible adjudicator. Invalid classifier output gets one
recovery attempt; HTTP retries and spending guards remain owned by the gateway.
Pipeline version 0.3.0 prevents new submissions from replaying old result caches.
