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
