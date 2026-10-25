# D16 motion layer: evidence

Spec: `../verres/design-ref/D16_MOTION.md` (not tracked). Branch `d/final-ui`, PR #45.

## Frames (1440×900, current production build)
- Hero scene at p = 0 / 0.3 / 0.6 / 0.9: `hero-p0-1440.webp`, `hero-p03-1440.webp`, `hero-p06-1440.webp`, `hero-p09-1440.webp`
- Stepper stages 1 / 3 / 5: `stepper-stage1-1440.webp`, `stepper-stage3-1440.webp`, `stepper-stage5-1440.webp`

Each stepper frame is an instant jump to that card, so earlier cards that were never 60% visible still show their pre-play state. That is the intended play-once trigger.

## Gates
- `npm run lint`, `npm run typecheck`, `npm test` (34 unit tests), `npx next build --webpack`: pass.
- `npx playwright test`: 68 passed, 2 skipped (the two environment opt-ins documented in D15). Snapshots refreshed with `--update-snapshots`, then a clean second run.
- Mobile Lighthouse ([lighthouse-mobile.json](lighthouse-mobile.json)): performance 91, accessibility 100, CLS 0, TBT 10–20 ms, LCP 3.5 s (simulated throttling, local production server, two runs). Lab numbers, not field data.
- Hero scroll trace ([hero-scroll-trace.json](hero-scroll-trace.json)): wheel scroll through the whole 220vh scene. 0 tasks over 50 ms (longest 3.8 ms), 0 layouts forced inside script, 43 layouts totalling 10.6 ms.

## Hard rules, as built
- One engine: `motion` (`useScroll`, `useTransform`, `useInView`, `animate`, its `frame` loop for the dot-matrix canvas). No GSAP, Lenis, CSS view-timeline or `--beat`; `d16-motion.spec.ts` checks the manifest and CSS.
- Only transform, opacity and clip-path animate (the highlighter sweep uses clip-path), plus the single `filter: blur` on "What we won't guess."
- One pinned scene (the hero, 220vh with a sticky 100vh stage). The stepper rail is sticky but adds no scroll height. Below 900px nothing pins.
- Reduced motion (OS or the reader setting) shows final states with the same layout, also before hydration via CSS.
- Scene text is 14px or larger. Cards keep a 14px font while the spec's scale-to-0.32 flight shrinks them in transit.

## Commands
```
npx next build --webpack && npx next start --hostname 127.0.0.1 --port 3106
CAPTURE_URL=http://127.0.0.1:3106 npx tsx scripts/d16/capture-frames.ts
CAPTURE_URL=http://127.0.0.1:3106 npx tsx scripts/d16/trace-hero.ts
npx lighthouse http://127.0.0.1:3106 --only-categories=performance,accessibility --output=json --output-path=docs/d16/lighthouse-mobile.json --chrome-flags='--headless' --quiet
```

No images were generated. S3, S4, S5 and the method crops stay in `public/mockups/` but are no longer imported.
