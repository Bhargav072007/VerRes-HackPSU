"""Informational citation outcomes within the frozen support-result contract."""

from contracts.schema import SupportResult

BACKGROUND_REASON = "Background citation: no specific factual finding is attributed to this source."
METHOD_REASON = (
    "Method reference: this citation identifies a method or tool, not a specific finding."
)


def informational_citation(result: SupportResult) -> bool:
    return result.label == "NEEDS_REVIEW" and result.needs_review_reason in {
        BACKGROUND_REASON,
        METHOD_REASON,
    }
