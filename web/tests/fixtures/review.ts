import { readFileSync } from "node:fs";
import { replayReport, type Report } from "../../lib/report";
import type { ReviewComment } from "../../lib/review";

export function reviewFixture(): Report {
  const base = replayReport(readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line)))!;
  const panel = JSON.parse(readFileSync("../fixtures/review/panel.json", "utf8"));
  const comments: ReviewComment[] = ["r1_methods", "r3_claims", "r2_evidence"].flatMap(key => panel[key].comments);
  return { ...base, hidden_text: [], review_comments: comments, review: { comments, top_fixes: panel.chair.comment_ids.map((id: string) => comments[Number(id.split("-")[1]) - 1].suggestion), warning: null } };
}
