import re
from datetime import date
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from api.app.ingest.models import (
    ParsedCitation,
    ParsedPaper,
    ParsedReference,
    ParsedSentence,
    ParseResult,
)
from api.app.providers.identifiers import extract_arxiv, normalize_arxiv

NS = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DOI = re.compile(r"\b10\.\d{4,9}/[^\s<>\"\]]+", re.I)
PMID = re.compile(r"(?:PMID\s*[:=]?\s*|pubmed\.ncbi\.nlm\.nih\.gov/)(\d+)", re.I)


def text(node) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def identifiers(value: str) -> dict[str, str | None]:
    doi, pmid = DOI.search(value), PMID.search(value)
    doi_value = doi.group().rstrip(".,;").lower() if doi else None
    if doi_value:
        while doi_value.endswith(")") and doi_value.count(")") > doi_value.count("("):
            doi_value = doi_value[:-1]
    return {
        "doi": doi_value,
        "arxiv": extract_arxiv(value),
        "pmid": pmid.group(1) if pmid else None,
    }


def parse_tei(data: bytes) -> ParseResult:
    if len(data) > 20 * 1024 * 1024:
        return ParseResult(status="FAILED", parser="grobid", reasons=["TEI exceeds 20 MB"])
    try:
        root = ElementTree.fromstring(data, forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError):
        return ParseResult(status="FAILED", parser="grobid", reasons=["malformed or unsafe TEI"])
    if root.tag != NS + "TEI":
        return ParseResult(status="FAILED", parser="grobid", reasons=["unexpected TEI namespace"])
    reasons = []
    paper = ParsedPaper(title=text(root.find(f".//{NS}titleStmt/{NS}title")) or None)
    stamp = root.find(f".//{NS}sourceDesc//{NS}date")
    if stamp is not None:
        try:
            paper.published = date.fromisoformat(stamp.get("when", ""))
        except ValueError:
            # Optional metadata: the orchestrator uses today when no full date exists.
            pass
    seen = set()
    for item in root.findall(f".//{NS}listBibl/{NS}biblStruct"):
        ref_id = item.get(XML_ID)
        if not ref_id or ref_id in seen:
            reasons.append("missing or duplicate bibliography ID; entry omitted")
            continue
        seen.add(ref_id)
        raw = text(item.find(f"{NS}note[@type='raw_reference']")) or text(item)
        title = item.find(f"{NS}analytic/{NS}title")
        if title is None:
            title = item.find(f"{NS}monogr/{NS}title")
        surnames = [text(n) for n in item.findall(f".//{NS}author//{NS}surname") if text(n)]
        year_node = item.find(f".//{NS}imprint/{NS}date")
        year_match = (
            re.search(r"\b(?:18|19|20)\d{2}\b", year_node.get("when", "") or text(year_node))
            if year_node is not None
            else None
        )
        ids = identifiers(raw)
        for node in item.findall(f".//{NS}idno"):
            kind, value = node.get("type", "").lower(), text(node)
            if kind == "doi":
                ids["doi"] = identifiers(value)["doi"]
            elif kind in ("arxiv", "pmid"):
                ids[kind] = normalize_arxiv(value) if kind == "arxiv" else value or None
        paper.references.append(
            ParsedReference(
                id=ref_id,
                raw=raw,
                title=text(title) or None,
                authors=surnames,
                year=int(year_match.group()) if year_match else None,
                venue=text(item.find(f"{NS}monogr/{NS}title")) or None,
                kind="journal-article" if item.find(f"{NS}analytic") is not None else "unknown",
                **ids,
            )
        )
    parents = {child: parent for parent in root.iter() for child in parent}
    body = root.find(f"{NS}text/{NS}body")
    abstract = root.find(f".//{NS}profileDesc/{NS}abstract")
    selected = []
    for container in [abstract, body]:
        if container is None:
            continue
        for p in container.findall(f".//{NS}p"):
            sentences = p.findall(f".//{NS}s")
            if not sentences:
                sentences = [p]
                reasons.append("sentence segmentation unavailable for a paragraph")
            for node in sentences:
                section, ancestor = "Abstract" if container is abstract else "Body", p
                while ancestor is not None and ancestor is not container:
                    head = ancestor.find(f"{NS}head")
                    if head is not None:
                        section = text(head)
                        break
                    ancestor = parents.get(ancestor)
                if text(node):
                    selected.append((node, section))
    for index, (node, section) in enumerate(selected):
        sid = f"s{index + 1:05d}"
        value = text(node)
        paper.sentences.append(ParsedSentence(id=sid, text=value, section=section))
        for marker in node.findall(f".//{NS}ref[@type='bibr']"):
            targets = marker.get("target", "").split()
            if not targets:
                reasons.append("citation has no bibliography target")
            for target in dict.fromkeys(targets):
                target = target.removeprefix("#")
                if target not in seen:
                    reasons.append(f"broken citation target: {target}")
                    continue
                paper.citations.append(
                    ParsedCitation(
                        id=f"c{len(paper.citations) + 1:05d}",
                        reference_id=target,
                        sentence_id=sid,
                        text=value,
                        marker=text(marker),
                        section=section,
                        reference_title=next(r.title for r in paper.references if r.id == target),
                        reference_raw=next(r.raw for r in paper.references if r.id == target),
                        previous=text(selected[index - 1][0]) if index else None,
                        next=text(selected[index + 1][0]) if index + 1 < len(selected) else None,
                    )
                )
    if not paper.references:
        reasons.append("no bibliography recovered")
    if not paper.sentences:
        reasons.append("no document sentences recovered")
    status = "FAILED" if not paper.sentences else "PARTIAL" if reasons else "FULL"
    return ParseResult(
        status=status, paper=paper, reasons=list(dict.fromkeys(reasons)), parser="grobid"
    )
