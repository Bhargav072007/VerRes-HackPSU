"""Per-job panel state; untrusted model output never bypasses receipt validation."""

import asyncio
import logging
from pathlib import Path

from pydantic import Field

from api.app.verify.model import Model, ModelFailure, untrusted
from contracts.schema import Contract, Paper, ReviewComment, ReviewSummary, SupportResult

logger = logging.getLogger(__name__)
HIDDEN_WARNING = "This paper contains hidden text addressed to AI reviewers."


class ReviewerOutput(Contract):
    comments: list[ReviewComment] = Field(max_length=6)


class ChairOutput(Contract):
    comment_ids: list[str] = Field(max_length=5)


class ReviewPanel:
    def __init__(self, model: Model | None = None, *, report=None, on_review=None):
        self.model, self.report, self.on_review = model, report, on_review
        self.prepared = None
        self.failure = None
        self.seen = set()

    def unavailable(self, reason):
        self.failure = f"Review panel unavailable: {reason}"
        logger.warning("%s", self.failure)
        return ReviewSummary(warning=self.failure)

    async def ask(self, task, data, schema):
        system = (Path(__file__).parent / "prompts" / f"{task}.v1.md").read_text()
        response = await self.model.complete(
            task=task, system=system, data=untrusted(data), schema=schema.model_json_schema()
        )
        if not isinstance(response, str) or len(response) > 100_000:
            raise ModelFailure("missing or oversized output")
        return schema.model_validate_json(response, strict=True)

    def citation_table(self, paper, support):
        existence = {r.reference_id: r.status for r in self.report.existence} if self.report else {}
        retractions = (
            {r.reference_id: r.status for r in self.report.retractions} if self.report else {}
        )
        results = {r.citation_id: r for r in support}
        return [
            {
                "citation_id": c.id,
                "sentence_ids": c.sentence_ids,
                "existence_status": existence.get(c.reference_id, "CHECK_INCOMPLETE"),
                "retraction_status": retractions.get(c.reference_id, "UNKNOWN"),
                "support_label": results[c.id].label if c.id in results else "NEEDS_REVIEW",
                "mismatch_types": results[c.id].mismatch_types if c.id in results else [],
            }
            for c in paper.citations
        ]

    def validate(self, comment, reviewer, paper, table):
        sentences = {s.id: s.text for s in paper.sentences}
        ids = set(comment.sentence_ids)
        if comment.reviewer != reviewer or not ids <= sentences.keys():
            return False
        quote = " ".join(comment.quote.split())
        text = " ".join(" ".join(s.text.split()) for s in paper.sentences if s.id in ids)
        if not quote or quote not in text:
            return False
        citations = {c.id: c for c in paper.citations}
        if any(c not in citations for c in comment.linked_citation_ids):
            return False
        if reviewer == "EVIDENCE":
            flagged = {
                r["citation_id"]
                for r in table
                if (r["support_label"], r["existence_status"], r["retraction_status"])
                != ("SUPPORTED", "VERIFIED", "NONE")
            }
            if comment.linked_citation_ids:
                if any(
                    c not in flagged or not ids.intersection(citations[c].sentence_ids)
                    for c in comment.linked_citation_ids
                ):
                    return False
            elif any(ids.intersection(c.sentence_ids) for c in paper.citations):
                return False
        key = (tuple(sorted(ids)), quote, " ".join(comment.issue.lower().split()))
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    async def reviewer(self, task, reviewer, paper, table=None):
        data = {
            "sentences": [
                {"sentence_id": s.id, "text": s.text, "section": s.section} for s in paper.sentences
            ]
        }
        if table is not None:
            data["citation_results"] = table
        try:
            result = await self.ask(task, data, ReviewerOutput)
        except Exception as error:
            self.unavailable(f"{task} failed ({type(error).__name__})")
            return []
        comments = [c for c in result.comments if self.validate(c, reviewer, paper, table or [])]
        if self.on_review:
            for comment in comments:
                await self.on_review(comment)
        return comments

    async def prepare(self, paper: Paper) -> ReviewSummary:
        if self.failure:
            return ReviewSummary(warning=self.failure)
        if self.model is None:
            return self.unavailable("no model configured")
        if self.prepared is None:
            results = await asyncio.gather(
                self.reviewer("r1_methods", "METHODS", paper),
                self.reviewer("r3_claims", "CLAIMS", paper),
            )
            self.prepared = [c for group in results for c in group]
        return ReviewSummary(comments=[] if self.failure else self.prepared, warning=self.failure)

    async def run_review_panel(self, paper: Paper, support: list[SupportResult]) -> ReviewSummary:
        await self.prepare(paper)
        if self.failure:
            return ReviewSummary(warning=self.failure)
        evidence = await self.reviewer(
            "r2_evidence", "EVIDENCE", paper, self.citation_table(paper, support)
        )
        if self.failure:
            return ReviewSummary(warning=self.failure)
        comments = self.prepared + evidence
        surviving = {f"comment-{i + 1}": c for i, c in enumerate(comments)}
        try:
            chair = await self.ask(
                "chair", {k: c.model_dump() for k, c in surviving.items()}, ChairOutput
            )
        except Exception as error:
            return self.unavailable(f"chair failed ({type(error).__name__})")
        selected = list(dict.fromkeys(c for c in chair.comment_ids if c in surviving))
        selected.sort(key=lambda c: surviving[c].severity != "MAJOR")
        return ReviewSummary(
            comments=comments,
            top_fixes=list(dict.fromkeys(surviving[c].suggestion for c in selected)),
            warning=HIDDEN_WARNING
            if self.report
            and not any(f.kind == "CHECK_INCOMPLETE" for f in self.report.hidden_text)
            and any("INSTRUCTION_PATTERN" in f.reason for f in self.report.hidden_text)
            else None,
        )
