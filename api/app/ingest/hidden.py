"""Group suspicious glyphs into readable findings, without flagging math labels."""

import re

from api.app.ingest.models import HiddenSpan

INSTRUCTIONS = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
    r"system\s+prompt|you\s+are\s+(?:chatgpt|an?\s+assistant)|"
    r"(?:return|output|mark)\s+(?:only\s+)?(?:supported|approved|positive)|"
    r"do\s+not\s+(?:verify|check|report)",
    re.I,
)


def white_color(fill):
    channels = fill if isinstance(fill, list | tuple) else [fill]
    return (
        len(channels) in (1, 3) and all(isinstance(c, int | float) and c >= 0.98 for c in channels)
    ) or (
        len(channels) == 4 and all(isinstance(c, int | float) and 0 <= c <= 0.02 for c in channels)
    )


def page_hidden_spans(page, page_no, invisible):
    invisible_boxes = {
        (round(c.x0, 2), round(page.height - c.y1, 2), c.get_text()) for c in invisible
    }
    glyphs = []
    for char in page.chars:
        categories = []
        box = tuple(float(char[k]) for k in ("x0", "top", "x1", "bottom"))
        if white_color(char.get("non_stroking_color")) and not any(
            r.get("fill")
            and r["x0"] <= box[0]
            and r["x1"] >= box[2]
            and r["top"] <= box[1]
            and r["bottom"] >= box[3]
            and not white_color(r.get("non_stroking_color"))
            for r in page.rects
        ):
            categories.append("WHITE_FILL")
        if 0 < char.get("size", 10) <= 2.001:
            categories.append("TINY_FONT")
        if box[2] <= 0 or box[0] >= page.width or box[3] <= 0 or box[1] >= page.height:
            categories.append("OFF_PAGE")
        if (round(box[0], 2), round(box[1], 2), char["text"]) in invisible_boxes:
            categories.append("INVISIBLE_RENDER_MODE")
        if categories:
            glyphs.append((box, char["text"], categories))
    # Same-line runs first; only adjacent runs with compatible styling form a block.
    runs = []
    for box, text, categories in sorted(glyphs, key=lambda g: (round(g[0][1], 1), g[0][0])):
        height = max(box[3] - box[1], 0.1)
        if (
            runs
            and abs(runs[-1].bbox[1] - box[1]) <= height * 0.4
            and -0.2 <= box[0] - runs[-1].bbox[2] <= height * 1.8
        ):
            run = runs[-1]
            if (
                box[0] - run.bbox[2] > height * 0.25
                and not run.text.endswith(" ")
                and not text.isspace()
            ):
                run.text += " "
            run.text += text
            run.categories = sorted(set(run.categories + categories))
            run.bbox = (
                min(run.bbox[0], box[0]),
                min(run.bbox[1], box[1]),
                max(run.bbox[2], box[2]),
                max(run.bbox[3], box[3]),
            )
        else:
            runs.append(
                HiddenSpan(
                    page=page_no,
                    text=text,
                    categories=categories,
                    bbox=box,
                    reason="unusual PDF styling; intent requires review",
                )
            )
    blocks = []
    for run in runs:
        height = max(run.bbox[3] - run.bbox[1], 0.1)
        if (
            blocks
            and set(run.categories) == set(blocks[-1].categories)
            and abs(run.bbox[0] - blocks[-1].bbox[0]) <= height
            and 0 <= run.bbox[1] - blocks[-1].bbox[3] <= height * 0.8
        ):
            block = blocks[-1]
            block.text += "\n" + run.text
            block.bbox = (
                min(block.bbox[0], run.bbox[0]),
                block.bbox[1],
                max(block.bbox[2], run.bbox[2]),
                run.bbox[3],
            )
        else:
            blocks.append(run)
    # Isolated tiny glyphs are common in equations, plots and superscripts.
    blocks = [
        b
        for b in blocks
        if b.text.strip()
        and (
            b.categories != ["TINY_FONT"]
            or (
                len(re.findall(r"[A-Za-z]+", b.text)) >= 2
                and len(re.findall(r"[A-Za-z]", b.text)) >= 6
            )
            or re.search(r"[A-Za-z]{8,}", b.text)
        )
    ]
    for match in page.search(INSTRUCTIONS, return_chars=False):
        box = tuple(float(match[k]) for k in ("x0", "top", "x1", "bottom"))
        overlaps = [
            b
            for b in blocks
            if b.bbox[0] <= box[2]
            and b.bbox[2] >= box[0]
            and b.bbox[1] <= box[3]
            and b.bbox[3] >= box[1]
        ]
        if overlaps:
            for block in overlaps:
                block.categories = sorted(set(block.categories + ["INSTRUCTION_PATTERN"]))
        else:
            blocks.append(
                HiddenSpan(
                    page=page_no,
                    text=match["text"],
                    categories=["INSTRUCTION_PATTERN"],
                    bbox=box,
                    reason="instruction-like text; treated only as document data",
                )
            )
    return blocks
