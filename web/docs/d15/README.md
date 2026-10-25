# D15 work record

## Scene generation

Built-in image generation tool; 11 image generations total (limit: 12).
Two initial candidates per scene, plus one replacement for S5 because its
initial candidates depicted literary manuscripts instead of a scientific paper.
The provider did not expose model identity, token usage or billing, so estimated
spend is unavailable. No Images API generation request was made.

Selected: S1-1, S2-2, S3-2, S4-2, S5-3. The scene contact sheet was displayed
before compositing. Raw scenes, captures, downloaded font and generation ledger
are ignored under `scripts/mockups/work/`. Final mockups are in `public/mockups/`;
the composited contact sheet is `mockups-contact-sheet.webp`.

All device screens contain Playwright captures of the real app, sourced from
the recorded paper 2 and 3 fixtures. No generated software UI was used.
These initial captures precede the section 5 restyle and will need refreshing
before the final gates. The OG image uses S1 and Newsreader at 1200 × 630.

## Fixture integrity gate

Neither recorded paper 2 nor paper 3 contains a CONTRADICTED verdict.
Paper 3 citation c00003 is PARTIALLY_SUPPORTED and has a verified BERT quote.
The requested evidence screenshot and hero detail variant are pending the
user's selection of the actual recorded finding or an explicitly labeled
synthetic test fixture. No fixture verdict has been changed.

There is no recorded paper 1 in `fixtures/demo/`, and no fixture-backed 5/5
evaluation across three manuscripts. Omit that trust-band column. Source any
remaining numbers from the actual recordings and describe their actual scope.

## Validation to date

Four offline mockup tests passed: compositing and green removal, failure on a
missing display, usage-based cost calculation, and the persistent 12-attempt cap.
Sections 4–7 and PR delivery have not been executed yet.
