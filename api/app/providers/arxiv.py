"""Coalesced arXiv ID lookups with validated, per-ID persistent metadata cache."""

import asyncio
import re
from xml.etree.ElementTree import ParseError

from asyncpg import PostgresError
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from api.app.providers.http import DAY, Gateway
from api.app.providers.identifiers import normalize_arxiv, same_arxiv
from api.app.providers.models import HTTPResult, ProviderResult, Work


class Arxiv:
    def __init__(self, gateway: Gateway):
        self.gateway = gateway
        self.pending = {}
        self.inflight = {}
        self.worker = None

    async def lookup(self, identifier: str) -> ProviderResult:
        identifier = normalize_arxiv(identifier)
        if not identifier:
            return ProviderResult(provider="arxiv", definitive=False, reason="invalid arXiv ID")
        try:
            cached = await self.gateway.cache.get("arxiv-metadata:v1:" + identifier)
            if cached:
                result = ProviderResult.model_validate_json(cached.content)
                if (
                    result.provider == "arxiv"
                    and result.definitive
                    and all(same_arxiv(identifier, w.arxiv) for w in result.works)
                ):
                    return result
        except (ValueError, TypeError, PostgresError, OSError):
            pass
        if identifier not in self.inflight:
            future = asyncio.get_running_loop().create_future()
            self.inflight[identifier] = self.pending[identifier] = future
            if self.worker is None:
                self.worker = asyncio.create_task(self.flush())
        return (await asyncio.shield(self.inflight[identifier])).model_copy(deep=True)

    async def store(self, identifier, result):
        if not result.definitive:
            return
        value = HTTPResult(status=200, content=result.model_dump_json().encode())
        aliases = {identifier, *(w.arxiv for w in result.works if w.arxiv)}
        for alias in aliases:
            try:
                await self.gateway.cache.put(
                    "arxiv-metadata:v1:" + alias, value, 7 * DAY if result.works else DAY
                )
            except (PostgresError, OSError):
                pass  # Independently retrieved evidence survives an unavailable cache.

    async def search(self, title: str) -> ProviderResult:
        phrase = " ".join(re.findall(r"\w+", title))
        result = await self.query({"search_query": f'ti:"{phrase}"', "max_results": 20})
        if result.definitive:
            for work in result.works:
                await self.store(work.arxiv, result.model_copy(update={"works": [work]}))
        return result

    async def flush(self):
        active = {}
        try:
            await asyncio.sleep(0.01)
            while self.pending:
                ids = list(self.pending)[:50]
                active = {i: self.pending.pop(i) for i in ids}
                result = await self.query({"id_list": ",".join(ids), "max_results": len(ids)})
                if any(not any(same_arxiv(i, w.arxiv) for i in ids) for w in result.works):
                    result = ProviderResult(
                        provider="arxiv", definitive=False, reason="unexpected arXiv identifier"
                    )
                for identifier, future in active.items():
                    works = [w for w in result.works if same_arxiv(identifier, w.arxiv)]
                    # A batch can include both an unversioned and a pinned version of one work.
                    works.sort(
                        key=lambda w: int(re.search(r"v(\d+)$", w.arxiv).group(1))
                        if re.search(r"v(\d+)$", w.arxiv)
                        else 0,
                        reverse=True,
                    )
                    individual = result.model_copy(update={"works": works[:1]})
                    await self.store(identifier, individual)
                    if not future.done():
                        future.set_result(individual)
                    self.inflight.pop(identifier, None)
                active = {}
        finally:
            incomplete = ProviderResult(
                provider="arxiv", definitive=False, reason="arXiv batch did not complete"
            )
            for identifier, future in {**active, **self.pending}.items():
                if not future.done():
                    future.set_result(incomplete)
                self.inflight.pop(identifier, None)
            self.pending.clear()
            self.worker = None

    async def query(self, params) -> ProviderResult:
        response = await self.gateway.request("arxiv", "/api/query", params=params)
        if response.error or response.status != 200:
            return ProviderResult(
                provider="arxiv",
                definitive=False,
                reason=response.error or f"HTTP {response.status}",
            )
        ns = "{http://www.w3.org/2005/Atom}"
        try:
            root = ElementTree.fromstring(response.content, forbid_dtd=True)
            if root.tag != ns + "feed":
                raise ValueError("invalid Atom feed")
            works = []
            for item in root.findall(ns + "entry"):
                title, identity = item.findtext(ns + "title"), item.findtext(ns + "id")
                if not title or not normalize_arxiv(identity):
                    raise ValueError("invalid arXiv entry")
                works.append(
                    Work(
                        provider="arxiv",
                        id=identity,
                        arxiv=normalize_arxiv(identity),
                        title=" ".join(title.split()),
                        year=int(item.findtext(ns + "published", "")[:4]),
                        authors=[
                            a.findtext(ns + "name", "").strip()
                            for a in item.findall(ns + "author")
                            if a.findtext(ns + "name", "").strip()
                        ],
                        author_names_are_full=True,
                        abstract=item.findtext(ns + "summary"),
                    )
                )
            total = root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
            if "id_list" in params and total is not None and int(total) > len(works):
                raise ValueError("incomplete arXiv ID response")
            if total is not None and int(total) > len(works):
                return ProviderResult(
                    provider="arxiv",
                    definitive=False,
                    works=works,
                    reason="arXiv search results are truncated",
                )
            return ProviderResult(provider="arxiv", definitive=True, works=works)
        except (ParseError, DefusedXmlException, ValueError, IndexError, TypeError):
            return ProviderResult(
                provider="arxiv", definitive=False, reason="malformed arXiv metadata"
            )
