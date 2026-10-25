import { readFileSync } from "node:fs";
import { replayReport } from "../../lib/report";

export function claimGraphFixture() {
  return replayReport(readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line)))!;
}
