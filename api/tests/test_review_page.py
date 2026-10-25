"""Local reviewer UI never imports proposals, fills labels, or reaches the network."""

import json
import re

import pytest

from api.app.eval.review_page import render_review_page


@pytest.fixture
def rows():
    packet = [
        {
            "id": "candidate-1",
            "paper_id": "paper3_planted_problems",
            "synthetic": True,
            "page": 1,
            "citing_sentence": "A < B [1].",
            "citation_marker": "[1]",
            "cited_reference": "Real reference",
            "source_id": "arxiv:1234.12345",
            "source_title": "Source",
            "source_url": "https://example.org/source",
            "source_caution": None,
            "source_quote": "An exact source quote here.",
            "source_locator": "Abstract",
            "prepared_scope": "ABSTRACT_ONLY",
            "initial_quote_in_prepared_source": True,
            "review_flags": ["Check source identity"],
        }
    ]
    reviews = [
        {
            "candidate_id": "candidate-1",
            "candidate_sha256": "1" * 64,
            "source_receipt_sha256": "2" * 64,
            "prepared_source_sha256": "3" * 64,
            "annotation_status": "PENDING",
            "citation_function": None,
            "claim": None,
            "human_label": None,
            "labeled_by": None,
            "label_reason": None,
            "evidence_quote": None,
            "source_identity": None,
            "human_attestation": False,
            "reviewed_at": None,
        }
    ]
    return packet, reviews


def payload(html):
    return json.loads(re.search(r'id="payload">(.*?)</script>', html, flags=re.S)[1])


def test_review_page_keeps_annotations_blank_and_excludes_packet_proposals(rows):
    packet, reviews = rows
    packet[0]["proposed_label"] = "CONTRADICTED"
    packet[0]["proposed_reason"] = "Secret proposal that must not be shown"
    html = render_review_page(packet, reviews)
    data = payload(html)
    assert data["reviews"] == reviews
    assert not data["reviews"][0]["human_attestation"]
    assert data["reviews"][0]["human_label"] is None
    assert data["reviews"][0]["claim"] is None
    assert "proposed_label" not in html and "Secret proposal" not in html
    assert "fetch(" not in html and "localStorage" not in html and "XMLHttpRequest" not in html
    assert "connect-src 'none'" in html


def test_review_page_escapes_paper_text_and_creates_dom_with_textcontent(rows):
    packet, reviews = rows
    attack = '</script><script>alert("injected")</script><img src=x onerror=alert(1)>'
    packet[0]["citing_sentence"] = attack
    packet[0]["source_quote"] = attack
    reviews[0]["label_reason"] = attack
    html = render_review_page(packet, reviews)
    assert attack not in html and r"\u003c/script\u003e" in html
    assert payload(html)["packet"][0]["citing_sentence"] == attack
    assert html.count("</script>") == 2
    assert "innerHTML" not in html
    assert "textContent" in html
    assert "script-src 'sha256-" in html


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://example.org", "https://a:b@x.org"])
def test_review_page_removes_unsafe_or_authenticated_source_links(rows, url):
    packet, reviews = rows
    packet[0]["source_url"] = url
    assert payload(render_review_page(packet, reviews))["packet"][0]["source_url"] is None


def test_review_page_includes_manual_workflow_and_strict_import_controls(rows):
    html = render_review_page(*rows)
    for control in [
        "Previous",
        "Next",
        "Save review",
        "Approve reviewed candidate",
        "Exclude candidate",
        "Mark pending",
        "Download reviews.jsonl",
        "Resume from matching reviews.jsonl",
        "new Blob",
        "JSON.parse(line)",
        "validateImport(rows)",
        "prepared_source_sha256",
        "source_receipt_sha256",
        "Unexpected or missing review fields",
        "SYNTHETIC TEST DRAFT",
        "useQuote.disabled=!item.initial_quote_in_prepared_source",
        "noopener noreferrer",
        "requiredClaim",
        "human_attestation=attestation.checked",
    ]:
        assert control in html
    assert "controls.evidence_quote.value=packet[current].source_quote" in html
    # The only quote-copy operation is inside the explicit button handler.
    assert html.index("const useQuote=button") < html.index("controls.evidence_quote.value=")
    assert "claimControls[key].value=row.claim?.[key]??''" in html


def test_review_page_rejects_mismatched_or_duplicate_rows(rows):
    packet, reviews = rows
    with pytest.raises(ValueError, match="nonempty"):
        render_review_page([], [])
    with pytest.raises(ValueError, match="candidate IDs"):
        render_review_page(packet, [{**reviews[0], "candidate_id": "other"}])
    with pytest.raises(ValueError, match="duplicate"):
        render_review_page(packet * 2, reviews * 2)
    with pytest.raises(ValueError, match="unexpected"):
        render_review_page(packet, [{**reviews[0], "proposed_label": "SUPPORTED"}])
