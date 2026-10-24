# VerRes frontend

Run `npm ci`, then `npm run dev` from `web/`. Requires Node.js 20.9+.
Set `NEXT_PUBLIC_API_URL` before building to override `http://localhost:8000`.

`npm run types` generates `lib/api-types.ts` from the checked-in `openapi.json`.
The interim `/jobs` shape lives in `lib/api.ts` until the A2 schema update.
PDF requests use multipart `file`; identifiers use JSON `arxiv_id` or `doi`.
The app makes real API requests. Samples are explicitly unavailable placeholders.

Checks: `npm run lint`, `npm test`, `npm run build`, then `npm run test:browser`.
Browser checks use installed Chrome and the production build; port 3000 must be free.
Screenshots are written under `playwright-results/` (gitignored).
