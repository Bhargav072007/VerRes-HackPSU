import re

import bm25s

from api.app.verify.models import Passage


def passages(text: str, words: int = 200) -> list[Passage]:
    matches = list(re.finditer(r"\S+", text))
    return [
        Passage(
            id=f"p{i // words + 1:05d}",
            text=text[matches[i].start() : matches[min(i + words, len(matches)) - 1].end()],
        )
        for i in range(0, len(matches), words)
    ]


def retrieve(query: str, source: str, abstract: str | None = None) -> list[Passage]:
    return retrieve_passages(query, passages(source), abstract)


def retrieve_passages(
    query: str, chunks: list[Passage], abstract: str | None = None
) -> list[Passage]:
    """Rank existing passages without changing their shared-contract identifiers."""
    if not chunks:
        return []
    corpus = [p.text for p in chunks]
    tokens = bm25s.tokenize(corpus, stopwords="en", show_progress=False)
    queries = bm25s.tokenize([query], stopwords="en", show_progress=False)
    if not any(tokens.ids) or not any(queries.ids):
        selected = chunks[:8]
    else:
        retriever = bm25s.BM25()
        retriever.index(tokens, show_progress=False)
        results, _ = retriever.retrieve(queries, k=min(8, len(chunks)), show_progress=False)
        selected = [chunks[int(i)] for i in results[0]]
    if (
        abstract
        and abstract not in [p.text for p in selected]
        and not any(p.id == "abstract" for p in selected)
    ):
        selected.append(Passage(id="abstract", text=abstract))
    return selected
