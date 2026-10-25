# D14 review evidence

Baseline: `799e39f` — origin/main including D12 (#43, `b24f445`), Sach’s #38–#41, and #44. Rebased without conflicts.

Only web/ changes. No API, contract, verdict calculation, intake, SSE, sharing/export request, or report data changes. The export filenames remain compatible.

Validation: frontend lint, strict typecheck, 30 unit tests, webpack production build, full Playwright (61 passed; two existing environment opt-ins skipped), make lint and 697 backend tests. Playwright records console/page errors and checks horizontal overflow at 1440px and 390px. The final six D14 browser checks also pass separately.

The real development API test requires a running dev API; the mock timing test requires a separate NEXT_PUBLIC_MOCK=1 build. Neither environment is enabled in the standard production suite.

The MCP Node runtime could load Playwright but could not launch or connect to local Chrome because of its sandbox. Browser checks and the screenshots below were produced with the approved Playwright CLI. The shared headless environment measured about 30fps for both the manuscript sequence and an empty page; a 60fps hardware run remains to be verified.

All three reader themes have zero axe WCAG 2/2.1 A/AA violations in the recorded paper3 report after motion settles. See [theme audit](theme-audit.json).

## Lighthouse

Production build, Lighthouse defaults for each form factor. Desktop: performance **100**, accessibility **100**, CLS **0**. Mobile: performance **90**, accessibility **100**, CLS **0.0047**.

Raw results: [desktop](lighthouse-desktop.json), [mobile](lighthouse-mobile.json). The hero uses the same desktop geometry before and after hydration, avoiding the earlier pinning layout shift.

## Screenshots

Lossless screenshots at their original viewport resolution, 900px tall.

| View | 1440px | 390px |
|---|---|---|
| Landing top | [Open](landing-top-1440.webp) | [Open](landing-top-390.webp) |
| Manuscript sequence | [Open](landing-sequence-1440.webp) | [Open](landing-sequence-390.webp) |
| 1 Abstract | [Open](landing-abstract-1440.webp) | [Open](landing-abstract-390.webp) |
| 2 Methods | [Open](landing-how-it-works-1440.webp) | [Open](landing-how-it-works-390.webp) |
| 3 Results | [Open](landing-results-1440.webp) | [Open](landing-results-390.webp) |
| 4 Limitations | [Open](landing-honesty-1440.webp) | [Open](landing-honesty-390.webp) |
| 5 Submit | [Open](landing-submit-1440.webp) | [Open](landing-submit-390.webp) |
| Report · light | [Open](report-private-light-1440.webp) | [Open](report-private-light-390.webp) |
| Report · sepia | [Open](report-private-sepia-1440.webp) | [Open](report-private-sepia-390.webp) |
| Report · dark | [Open](report-private-dark-1440.webp) | [Open](report-private-dark-390.webp) |
| Settings · light | [Open](settings-report-light-1440.webp) | [Open](settings-report-light-390.webp) |
| Settings · sepia | [Open](settings-report-sepia-1440.webp) | [Open](settings-report-sepia-390.webp) |
| Settings · dark | [Open](settings-report-dark-1440.webp) | [Open](settings-report-dark-390.webp) |

## Intended snapshot changes

Landing snapshots reflect the manuscript hero. Live snapshots reflect the ribbon and copy. Report, peer-review, and graph snapshots reflect shared branding, academic copy, borders, card radii, and the Aa control. D12's reader/evidence snapshots and correctness assertions are unchanged. The older sticky-tabs expectation now checks D12's existing 174px desktop / 158px mobile position instead of the pre-D12 84px position.

- `web/tests/landing-polish.spec.ts-snapshots/landing-1440-no-preference-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/landing-1440-reduce-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/landing-390-no-preference-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/landing-390-reduce-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/live-1440-no-preference-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/live-1440-reduce-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/live-390-no-preference-darwin.png`
- `web/tests/landing-polish.spec.ts-snapshots/live-390-reduce-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/claim-graph-1440-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/claim-graph-390-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/peer-review-1440-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/peer-review-390-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/report-1440-darwin.png`
- `web/tests/report-polish.spec.ts-snapshots/report-390-darwin.png`
