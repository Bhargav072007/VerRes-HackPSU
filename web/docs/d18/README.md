# D18 ship pass: evidence

Spec: `../verres/design-ref/D18_SHIP.md` (untracked). Branch `d/final-ui`, PR #45.

## Screenshots (production build, `scripts/d18/capture.ts`)
- Hero at p = 1: `hero-p1-light-1440.webp`, `hero-p1-dark-1440.webp`, mobile `hero-p1-light-390.webp`
- Review room mid-run and done (fed recorded `fixtures/demo/paper3.jsonl` events): `room-mid-{light,dark}-1440.webp`, `room-done-{light,dark}-1440.webp`, mobile `room-mid-light-390.webp`
- Report in dark mode: `report-dark-1440.webp`

## Gates
- lint, typecheck, 41 unit tests, `next build --webpack`: pass.
- Playwright: 83 passed, 2 skipped (D15's environment opt-ins); snapshots refreshed (light and dark), then a clean second run.
- Axe at 1440 in dark on `/`, `/check/[sample]`, `/report/sample-paper3`: zero violations.
- Mobile Lighthouse on `/` in light mode ([lighthouse-mobile.json](lighthouse-mobile.json)): performance 90, accessibility 100, CLS 0 (three runs alike). Lab numbers.

## Notes
- Builds for tests use `NEXT_PUBLIC_API_URL=http://localhost:8000`: the untracked `web/.env.local` points at a deployed API, and the specs mock localhost.
- Lighthouse's simulated LCP for the hero H1 tracks script weight: the observed LCP is ~64 ms (same as FCP), but the simulation counts every script requested before it. Trimming the landing's fixture imports (`fixtures/landing/*.json`, no event journals) took performance from 89 to 90; it sits at the gate.
- Mobile CLS was 0.30 before the fix: the server-rendered flying cards occupied the mobile flow until hydration removed them; they are now hidden by CSS below 900px.
- Brand SVGs were traced with potrace from Bhargav's logo in design-ref; only the derived SVGs are committed.
