"""Receipt-validated peer review, with an explicitly selected fixture stub."""

from api.app.review.panel import ReviewPanel
from contracts.schema import Paper, ReviewComment, ReviewSummary, SupportResult

__all__ = ["ReviewPanel", "ReviewStub"]


class ReviewStub:
    async def prepare(self, paper: Paper) -> ReviewSummary:
        comments = []
        if paper.sentences:
            sentence = paper.sentences[0]
            for reviewer, issue, suggestion in (
                ("METHODS", "Methods review is pending.", "Check study design and sample size."),
                ("CLAIMS", "Claims review is pending.", "Check scope and generalizability."),
            ):
                comments.append(
                    ReviewComment(
                        reviewer=reviewer,
                        severity="MINOR",
                        sentence_ids=[sentence.id],
                        quote=sentence.text,
                        issue=issue,
                        suggestion=suggestion,
                    )
                )
        return ReviewSummary(comments=comments, warning="Review panel is a stub until A8.")

    async def run_review_panel(self, paper: Paper, support: list[SupportResult]) -> ReviewSummary:
        summary = await self.prepare(paper)
        if paper.sentences:
            sentence = paper.sentences[0]
            summary.comments.insert(
                1,
                ReviewComment(
                    reviewer="EVIDENCE",
                    severity="MINOR",
                    sentence_ids=[sentence.id],
                    quote=sentence.text,
                    issue="Evidence review is pending.",
                    suggestion="Inspect citation receipts and unresolved checks.",
                    linked_citation_ids=[result.citation_id for result in support],
                ),
            )
        summary.top_fixes = [comment.suggestion for comment in summary.comments]
        return summary
