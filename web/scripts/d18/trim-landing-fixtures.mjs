// node scripts/d18/trim-landing-fixtures.mjs — the landing ships these trimmed recordings instead of the full job fixtures,
// whose event journals (about 150KB) the page never reads. tests/landing-data.test.ts checks they stay in sync.
import { readFile, writeFile } from "node:fs/promises";
export const dropped = ["events", "review_comments", "claim_map"];
for (const name of ["paper2", "paper3"]) {
  const job = JSON.parse(await readFile(`tests/fixtures/prod/${name}-job.json`, "utf8"));
  for (const key of dropped) delete job[key];
  await writeFile(`fixtures/landing/${name}.json`, JSON.stringify(job) + "\n");
}
console.log("Wrote fixtures/landing/paper2.json and paper3.json");
