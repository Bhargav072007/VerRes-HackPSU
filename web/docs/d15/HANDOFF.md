# D15 handoff

Spec: ../verres/design-ref/D15_PROMPT.md (read first). Branch d/final-ui, PR #45 (draft).

## Done
- §3 scenes: 11 generations (Codex built-in image tool, $0 API). Green-screen scenes are in
  web/scripts/mockups/work/ (gitignored). Backup: ../verres/design-ref/mockup-scenes/.
  Selected scenes: S1 library laptop, S2 phone over journal, S3 café tablet, S4 lamp-desk laptop, S5 annotated paper.
- Scripts: capture.ts, generate.py (key from os.environ only), composite.py, test_mockups.py (4 pass).
- Draft composites in web/public/mockups/ and og-image.png. These are NOT FINAL because they show the OLD UI.

## Review decisions (from Bhargav)
- Use paper 3's real PARTIALLY_SUPPORTED BERT finding for the evidence shot and hero detail. Drop the "5/5" column.
  The trust band must be fixture-driven.
- Re-capture after the §4–§5 restyle. Use deviceScaleFactor 2 with smaller viewports (laptop 1280×800,
  tablet 1024×768), cropped so the text is readable.
- S1: paper column plus margin notes with a flagged citation visible.
- S2: no text under the sticky header; show the BERT line and its inline note.
- S3: evidence panel open on BERT (verified quote + DOI) instead of the empty claim graph.
- S4: restyled live check, mid-run.
- S5: background only, darkened to ≥55%.
- NO new image generations.

## Left
§4 landing, §5 report/live/settings restyle plus reportCounts "Claims flagged" with a test, §6 motion,
then the final capture plus composite, the contact sheet, and the §7 gates. Push, then mark #45 ready.

## Next step
Start §4 (landing rebuild), following the spec.

## Re-run mockups (after the restyle)
cd web && npx tsx scripts/mockups/capture.ts   # check the script header for exact args
python3 scripts/mockups/composite.py           # uses work/ scenes; no generation

## Continuation checkpoint: §4 complete
- Landing rebuilt; static navigation, Newsreader/Inter Tight/IBM Plex Mono, two-weight headings, method selector, real paper excerpt, upload band and footer.
- User updated trust band: 6 checks, 5 scholarly sources, fixture median with “median review time, recorded runs”. No accuracy claim.
- BERT fixture has arXiv:1810.04805, no DOI; show its recorded identifier without inventing one.
- Selected scenes confirmed: s1-1, s2-2, s3-2, s4-2, s5-3. No new generations.
- Typecheck, lint, webpack production build pass. Method crops and device composites await final capture after §5–§6.

## Continuation checkpoint: §5 complete
- Report and live counters are ruled Check / Result / Count tables; Claims flagged includes verified partial, unsupported and contradicted findings.
- Shared MarginNote component is rendered beside paper lines and inline on mobile. Reader settings remain complete with theme tints; report/evidence tokens are flat and semantic.
- Old manuscript sequence and beat mapping removed. Functional report reading header remains flat, with its obsolete progress strip removed.
- Typecheck, lint, all 30 unit tests, and webpack build pass. Browser snapshots are regenerated at §7 after final capture.
