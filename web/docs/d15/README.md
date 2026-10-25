# D15 final UI evidence

D15 replaces the old scroll manuscript scene with a static editorial landing, real product photography, paper excerpts and evidence-linked margin notes. Report/live summaries are ruled tables; Claims flagged includes verified partial, unsupported and contradicted findings. Reader settings and all upload, evidence, sharing and graph interactions remain available.

## Review decisions applied

- No new image generations. Reused `s1-1`, `s2-2`, `s3-2`, `s4-2`, `s5-3`.
- Hero/phone show the BERT partial-support finding. Tablet shows its verified source quote. The recorded source has no DOI, so it displays the recorded `arXiv:1810.04805` identifier.
- Trust band: six checks, five scholarly sources, and the fixture-derived 24-second median labelled “median review time, recorded runs”. No accuracy claims.
- Desktop pointer parallax is bounded to ±6px; counts run once for 600ms; line/note pairing uses a 160ms opacity tint. OS and reader reduced-motion preferences show final states.
- Orange CTA backgrounds retain `#EB4603` with ink text to meet contrast. Device AVIFs use pre-encoded responsive sizes, avoiding first-request image encoding.

## Captures

| View | Desktop | Mobile |
|---|---|---|
| Landing, full page | [1440px](landing-1440.webp) | [390px](landing-390.webp) |
| Report, light | [1440px](report-light-1440.webp) | [390px](report-light-390.webp) |
| Report, dark | [1440px](report-dark-1440.webp) | [390px](report-dark-390.webp) |

[Final mockups contact sheet](mockups-contact-sheet.webp)

## Validation

- Web lint, strict typecheck, 30 unit tests and `npm run build -- --webpack` pass.
- Full Playwright suite: 62 passed, two existing opt-in tests skipped (real development API and mock-build frame timing); snapshots regenerated. Includes two tests covering the new motion extras.
- `make lint PYTHON=../verres/.venv/bin/python` passes; `make test` with that environment: 697 passed.
- Offline mockup tests: four passed. No image-generation requests are made by these tests.
- [Mobile Lighthouse JSON](lighthouse-mobile.json): performance 91, accessibility 100, CLS 0. Default simulated mobile throttling, fresh browser storage, local production server. Below-fold device photos are lazy; hero has priority. Numbers are lab measurements, not production field metrics.
- Source ban-list check is clean for runtime app/components/lib and package manifests. Functional report reading header/tabs remain; there are no scroll-pinned scenes or navigation progress bars.
- Secret-name grep returns only the environment read in the generation script. No raw scenes, keys, or design reference directory are tracked.

## Image spend

This continuation generated **0** images and spent **$0** on image generation. The handoff records **11** prior built-in image-tool generations and **$0 Images API spend**; the built-in tool did not report a separate monetary cost.

## Reproduction

From `web/`, start the production server on port 3105, then:

```sh
CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/mockups/capture.ts
python3 scripts/mockups/composite.py --og-font scripts/mockups/work/Newsreader.ttf
CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/mockups/capture-pages.ts
PORT=3106 npm run test:browser -- --update-snapshots
npx lighthouse http://127.0.0.1:3105 --only-categories=performance,accessibility --output=json --output-path=docs/d15/lighthouse-mobile.json --chrome-flags='--headless' --quiet
```

Scene inputs and the OG font remain in the ignored local work directory; generation is not part of this procedure.
