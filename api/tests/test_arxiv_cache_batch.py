import asyncio
import json
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
import pytest

from api.app.providers.arxiv import Arxiv
from api.app.providers.cache import MemoryCache
from api.app.providers.http import DAY, Gateway, Policy
from api.app.providers.models import HTTPResult

WORKS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures/demo-arxiv-metadata.jsonl")
    .read_text()
    .splitlines()
]


def feed(works):
    entries = []
    for w in works:
        entries.append(
            f"<entry><id>{escape(w['id'])}</id><title>{escape(w['title'])}</title>"
            f"<published>{w['year']}-01-01</published><author><name>{escape(w['authors'][0])}</name></author></entry>"
        )
    return ('<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>").encode()


def gateway(handler, cache=None):
    return Gateway(
        {"arxiv": Policy("https://arxiv.example", 100, 1, 1)},
        cache=cache,
        attempts=1,
        transport=httpx.MockTransport(handler),
    )


async def test_25_concurrent_ids_use_one_request_and_source_version_aliases_are_cached():
    requests = []

    def handler(req):
        requests.append(req)
        return httpx.Response(200, content=feed(WORKS))

    async with gateway(handler) as g:
        provider = Arxiv(g)
        ids = [w["arxiv"].split("v")[0] for w in WORKS]
        results = await asyncio.gather(*(provider.lookup(i) for i in ids))
        assert len(requests) == 1 and len(requests[0].url.params["id_list"].split(",")) == 25
        assert requests[0].url.params["max_results"] == "25"
        assert all(r.definitive and len(r.works) == 1 for r in results)
        again = Arxiv(g)  # New provider instance uses the persistent Gateway cache adapter.
        await asyncio.gather(*(again.lookup(w["arxiv"]) for w in WORKS))
        assert len(requests) == 1
        results[0].works[0].title = "Caller mutation"
        assert (await again.lookup(ids[0])).works[0].title != "Caller mutation"


async def test_same_id_concurrent_callers_share_request_and_cancel_independently():
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(req):
        started.set()
        await release.wait()
        return httpx.Response(200, content=feed(WORKS[:1]))

    async with gateway(handler) as g:
        provider = Arxiv(g)
        first = asyncio.create_task(provider.lookup(WORKS[0]["arxiv"]))
        second = asyncio.create_task(provider.lookup(WORKS[0]["arxiv"]))
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second).definitive


@pytest.mark.parametrize(
    "body,status",
    [
        (b"not XML", 200),
        (b"", 503),
        (feed([dict(WORKS[0], arxiv="9999.00001", id="http://arxiv.org/abs/9999.00001")]), 200),
    ],
)
async def test_failures_and_wrong_ids_are_not_negative_cached(body, status):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, content=body)

    async with gateway(handler) as g:
        provider = Arxiv(g)
        assert not (await provider.lookup(WORKS[0]["arxiv"])).definitive
        assert not (await provider.lookup(WORKS[0]["arxiv"])).definitive
        assert len(calls) == 2 and not g.cache.entries


async def test_valid_empty_feed_is_negative_cached_for_one_day():
    calls = []
    now = [0]

    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=feed([]))

    async with gateway(handler, MemoryCache(clock=lambda: now[0])) as g:
        provider = Arxiv(g)
        result = await provider.lookup("2401.12345")
        assert result.definitive and not result.works
        assert (await provider.lookup("2401.12345")).definitive and len(calls) == 1
        now[0] = DAY + 1
        assert (await provider.lookup("2401.12345")).definitive and len(calls) == 2


async def test_invalid_cache_and_invalid_identifier_do_not_become_findings():
    async with gateway(lambda req: httpx.Response(200, content=feed(WORKS[:1]))) as g:
        await g.cache.put(
            "arxiv-metadata:v1:" + WORKS[0]["arxiv"], HTTPResult(content=b"broken"), 7 * DAY
        )
        provider = Arxiv(g)
        assert (await provider.lookup(WORKS[0]["arxiv"])).definitive
        assert not (await provider.lookup("../../invalid")).definitive


async def test_truncated_id_feed_cannot_negative_cache_missing_ids():
    body = feed(WORKS[:1]).replace(
        b"</feed>",
        b'<totalResults xmlns="http://a9.com/-/spec/opensearch/1.1/">2</totalResults></feed>',
    )
    async with gateway(lambda req: httpx.Response(200, content=body)) as g:
        result = await Arxiv(g).lookup(WORKS[0]["arxiv"])
        assert not result.definitive and not g.cache.entries


async def test_cache_outage_preserves_fresh_metadata():
    class UnavailableCache:
        async def get(self, key):
            raise OSError("offline cache")

        async def put(self, *args):
            raise OSError("offline cache")

    async with gateway(
        lambda req: httpx.Response(200, content=feed(WORKS[:1])), UnavailableCache()
    ) as g:
        result = await Arxiv(g).lookup(WORKS[0]["arxiv"])
        assert result.definitive and len(result.works) == 1


async def test_title_search_recovers_proceedings_paper_and_caches_its_identifier():
    from api.app.resolve.service import ResolveService
    from api.tests.test_shared_interfaces import provider
    from contracts.schema import Reference

    # Bibliographic facts verified at https://arxiv.org/abs/1610.08613.
    work = dict(
        provider="arxiv",
        id="http://arxiv.org/abs/1610.08613v1",
        arxiv="1610.08613v1",
        title="Can Active Memory Replace Attention?",
        authors=["Łukasz Kaiser"],
        year=2016,
    )
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=feed([work]))

    async with gateway(handler) as g:
        arxiv = Arxiv(g)
        reference = Reference(
            id="b15",
            raw_text="Kaiser and Bengio. Can active memory replace attention? In NIPS, 2016.",
            title=work["title"],
            authors=["Kaiser", "Bengio"],
            year=2016,
        )
        result = await ResolveService(
            provider("crossref", []), provider("openalex", []), arxiv=arxiv
        ).resolve_reference(reference)
        assert result.status == "VERIFIED" and result.matched_reference.arxiv_id == "1610.08613v1"
        assert "search_query" in calls[0].url.params
        assert (await arxiv.lookup("1610.08613v1")).definitive and len(calls) == 1


async def test_empty_title_search_does_not_hide_failed_provider():
    from api.app.resolve.service import ResolveService
    from api.tests.test_shared_interfaces import provider
    from contracts.schema import Reference

    reference = Reference(
        id="synthetic-test",
        raw_text="Synthetic article title. Journal of Testing, 14(3), 211-229.",
        title="Synthetic article title",
        authors=["Smith"],
        year=2024,
    )
    async with gateway(lambda req: httpx.Response(503)) as g:
        result = await ResolveService(
            provider("crossref", []), provider("openalex", []), arxiv=Arxiv(g)
        ).resolve_reference(reference)
        assert result.status == "CHECK_INCOMPLETE"


async def test_title_search_competing_identities_stay_ambiguous():
    from api.app.resolve.service import ResolveService
    from api.tests.test_shared_interfaces import provider
    from contracts.schema import Reference

    # Deliberately conflicting synthetic API identities, not evaluation candidates.
    first = dict(
        WORKS[0], title="Synthetic identity conflict study", authors=["Jane Smith"], year=2024
    )
    second = dict(first, id="http://arxiv.org/abs/2401.00002", arxiv="2401.00002")
    async with gateway(lambda req: httpx.Response(200, content=feed([first, second]))) as g:
        reference = Reference(
            id="synthetic-conflict", raw_text="", title=first["title"], authors=["Smith"], year=2024
        )
        result = await ResolveService(
            provider("crossref", []), provider("openalex", []), arxiv=Arxiv(g)
        ).resolve_reference(reference)
        assert result.status == "AMBIGUOUS"
