"""Canonical arXiv identifiers shared by extraction and provider boundaries."""

import re

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7})(?:v\d+)?"
ARXIV_MARKER = re.compile(
    rf"(?:arxiv[:\s/]+|arxiv\.org/(?:abs|pdf)/|\babs/|10\.48550/arxiv\.)({ARXIV_ID})(?![\w/])",
    re.I,
)


def normalize_arxiv(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(
        r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|^arxiv\s*:\s*|^abs/|^(?:https?://doi\.org/)?10\.48550/arxiv\.",
        "",
        value.strip(),
        flags=re.I,
    )
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    return value.lower() if re.fullmatch(ARXIV_ID, value, re.I) else None


def extract_arxiv(raw: str) -> str | None:
    match = ARXIV_MARKER.search(raw)
    return normalize_arxiv(match.group(1)) if match else None


def same_arxiv(requested: str | None, returned: str | None) -> bool:
    requested, returned = normalize_arxiv(requested), normalize_arxiv(returned)
    if not requested or not returned:
        return False
    return (
        requested == returned
        if re.search(r"v\d+$", requested)
        else requested == re.sub(r"v\d+$", "", returned)
    )
