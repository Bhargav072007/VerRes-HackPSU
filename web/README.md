# VerRes frontend

Run `npm ci`, then `npm run dev` from `web/`. Requires Node.js 20.9+.
Set `NEXT_PUBLIC_API_URL` before building to override `http://localhost:8000`.

`npm run types` generates `lib/api-types.ts` from the checked-in `openapi.json`.
PDF requests use multipart `file`; identifiers use JSON `arxiv_id` or `doi`.
The app makes real API requests. Samples submit the bundled PDFs through the same multipart intake as an upload.

`/check/[id]` restores the snapshot event journal before opening native SSE.
After an initial disconnect and two failed reconnects it polls every 2 seconds.
Set `NEXT_PUBLIC_MOCK=1` **before building** to replay
`public/fixtures/events/paper1.jsonl` at 100ms per event through the same reducer.
Reload resumes the mock clock saved per review ID in session storage; a new ID
starts a fresh run. Mock references and findings are explicitly synthetic.
Counters count checked citation occurrences, not-found/retracted references,
partially supported claims, and distinct references needing review.
Optional result `provenance.cached_at` renders a cache timestamp; absent metadata
renders `live`. This extension still needs a backend contract change.
`/report/[id]` reads the typed GET snapshot and polls while queued/running.
Mock reports replay the canonical fixture to completion immediately.
The reader filters paper sentences and sources together; `j`/`k` moves between
flags and Enter selects evidence. D4 can pass `onOpenEvidence(citationId)` to
`ReportReader`; the standalone route emits `verres:open-evidence` with
`detail.citationId` until the evidence panel is connected.
Non-review support verdicts require quotes matching the reference's source passages.
Use `LIVE_API=1 npm run test:browser` with a running dev API. If its job quota
is exhausted, add `LIVE_JOB_ID=<existing-id>` to exercise real SSE replay and
snapshot recovery using an existing dev job.

Checks: `npm run lint`, `npm test`, `npm run build`, then `npm run test:browser`.
Browser checks use installed Chrome and the production build; port 3000 must be free.
Run `NEXT_PUBLIC_MOCK=1 npm run build` and
`NEXT_PUBLIC_MOCK=1 npm run test:browser -- live-check.spec.ts` for mock playback.
Screenshots are written under `playwright-results/` (gitignored).

D14: VerRes — read your paper like Reviewer 2 would.
Every finding links to its evidence.

The landing manuscript is an explicitly labeled illustrative composite. Its
retraction example comes from recorded paper2; the Results preview uses a
subset of fixtures/demo/paper3.jsonl with unchanged quotes and source passages.
Run `node scripts/brand-assets.mjs` from web/ to regenerate ribbon assets from
the local design reference (the reference is not committed).

The desktop sequence has 300vh of travel: five 60vh beats, each animating for
42vh and holding for 18vh. CSS scroll timelines enhance the underline; a
requestAnimationFrame/IntersectionObserver mapping drives reversible annotations.
Mobile and reduced motion use static figures. Lenis is mounted only on landing
and destroyed when reduced motion is enabled or the route unmounts.

Reader settings apply to report and shared report, including portaled panels.
Size, spacing, theme, width, font, and reduced motion are stored under
`verres-reader`; blocked or malformed localStorage falls back to defaults.

Validation: `npm run lint`, `npm run typecheck`, `npm test`,
`npm run build -- --webpack`, `npm run test:browser`, `make lint`, `make test`.
