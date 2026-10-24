import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from api.app.providers.cache import MemoryCache, PostgresCache
from api.app.providers.http import DAY, Circuit, Gateway, Policy, retry_after
from api.app.providers.models import HTTPResult

POLICIES = {
    "test": Policy("https://provider.example", 1000, 1, 2),
    "source": Policy("https://example.org", 1000, 1, 2),
    "openalex": Policy("https://api.openalex.org", 1000, 1, 2),
}


async def public_dns(host, port):
    return ["93.184.216.34"]


async def test_cache_ttl_and_negative_ttl():
    now = [0]
    cache = MemoryCache(clock=lambda: now[0])
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    async with Gateway(POLICIES, cache=cache, transport=httpx.MockTransport(handler)) as gateway:
        assert (await gateway.request("test", "/missing", ttl=30 * DAY)).status == 404
        assert (await gateway.request("test", "/missing", ttl=30 * DAY)).cached
        now[0] += DAY + 1
        await gateway.request("test", "/missing", ttl=30 * DAY)
    assert len(calls) == 2


async def test_empty_searches_cached_for_one_day():
    cache = MemoryCache(clock=lambda: 0)
    async with Gateway(
        POLICIES,
        cache=cache,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []})),
    ) as gateway:
        await gateway.request("test", "/works", ttl=7 * DAY)
    assert next(iter(cache.entries.values()))[0] == DAY


async def test_retry_after_and_errors_not_cached():
    calls, waits = [], []

    async def sleep(seconds):
        waits.append(seconds)

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) < 3
            else httpx.Response(200, json={"ok": True})
        )

    cache = MemoryCache()
    async with Gateway(
        POLICIES, cache=cache, sleep=sleep, transport=httpx.MockTransport(handler)
    ) as gateway:
        assert (await gateway.request("test", "/", ttl=DAY)).status == 200
    assert waits == [2, 2] and len(cache.entries) == 1


async def test_long_retry_after_is_not_shortened():
    async with Gateway(
        POLICIES,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, headers={"Retry-After": "3600"})
        ),
    ) as gateway:
        result = await gateway.request("test", "/")
    assert result.error == "Retry-After exceeds retry budget"


@pytest.mark.parametrize("status", [500, 503])
async def test_errors_are_never_cached(status):
    cache = MemoryCache()
    async with Gateway(
        POLICIES,
        cache=cache,
        attempts=1,
        transport=httpx.MockTransport(lambda r: httpx.Response(status)),
    ) as gateway:
        await gateway.request("test", "/", ttl=DAY)
    assert not cache.entries


def test_circuit_failure_threshold_and_half_open():
    circuit = Circuit()
    for n in range(5):
        assert circuit.enter(n)
        circuit.record(True, 503, n)
    assert not circuit.enter(63)
    assert circuit.enter(64)
    assert not circuit.enter(64)
    circuit.record(False, 200, 64)
    assert circuit.enter(65) and circuit.failures == 0


def test_circuit_throttles_window():
    circuit = Circuit()
    for stamp in (0, 1, 2):
        circuit.record(True, 429, stamp)
    assert not circuit.enter(3)
    other = Circuit()
    for stamp in (0, 31, 62):
        other.record(True, 429, stamp)
    assert other.enter(63)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/a",
        "https://user:pass@example.org/a",
        "https://example.org:444/a",
        "file:///etc/passwd",
    ],
)
async def test_bad_source_urls(url):
    async with Gateway(POLICIES, resolver=public_dns) as gateway:
        assert (await gateway.safe_fetch(url)).error


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.1.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "100.64.0.1",
        "192.168.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "ff02::1",
        "2002:7f00:0001::",
    ],
)
async def test_private_and_metadata_ips_blocked(ip):
    async def dns(host, port):
        return [ip]

    async with Gateway(POLICIES, resolver=dns) as gateway:
        assert (await gateway.safe_fetch("https://example.org/paper")).error


async def test_redirect_private_destination_is_rechecked():
    calls = []

    async def dns(host, port):
        return ["127.0.0.1"] if host == "localhost" else ["93.184.216.34"]

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://localhost/secret"})

    async with Gateway(POLICIES, resolver=dns, transport=httpx.MockTransport(handler)) as gateway:
        result = await gateway.safe_fetch("https://example.org/a")
    assert result.error and len(calls) == 1


async def test_dns_pinned_with_host_and_sni():
    calls = []

    async def dns(host, port):
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["127.0.0.1"]

    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "example.org"
        assert request.headers["Connection"] == "close"
        assert request.extensions["sni_hostname"] == "example.org"
        return httpx.Response(200, content=b"source")

    async with Gateway(POLICIES, resolver=dns, transport=httpx.MockTransport(handler)) as gateway:
        assert (await gateway.safe_fetch("https://example.org/a")).content == b"source"
    assert calls == ["example.org"]


async def test_mixed_public_private_dns_is_rejected():
    async def dns(host, port):
        return ["93.184.216.34", "10.0.0.1"]

    async with Gateway(POLICIES, resolver=dns) as gateway:
        assert (await gateway.safe_fetch("https://example.org/a")).error


async def test_response_size_bound_and_cleanup(monkeypatch):
    monkeypatch.setattr("api.app.providers.http.MAX_BYTES", 16)
    async with Gateway(
        POLICIES,
        resolver=public_dns,
        attempts=1,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 17)),
    ) as gateway:
        assert (await gateway.safe_fetch("https://example.org/a")).error
    assert all(c.is_closed for c in gateway.clients.values())


async def test_openalex_cost_guard():
    async with Gateway(
        POLICIES,
        daily_budget_usd=0.01,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"meta": {"cost_usd": 0.01}})
        ),
    ) as gateway:
        assert (await gateway.request("openalex", "/works")).status == 200
        assert (await gateway.request("openalex", "/works")).error


async def test_unknown_openalex_cost_closes_guard():
    async with Gateway(
        POLICIES, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    ) as gateway:
        await gateway.request("openalex", "/works")
        assert (await gateway.request("openalex", "/works")).error


async def test_concurrency_and_cancellation_release_slots():
    active, maximum = 0, 0
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        nonlocal active, maximum
        active += 1
        maximum = max(active, maximum)
        started.set()
        try:
            await release.wait()
            return httpx.Response(200)
        finally:
            active -= 1

    async with Gateway(POLICIES, transport=httpx.MockTransport(handler)) as gateway:
        tasks = [asyncio.create_task(gateway.request("test", "/")) for _ in range(3)]
        await started.wait()
        await asyncio.sleep(0)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        release.set()
        await asyncio.gather(*tasks[1:])
        assert maximum <= 2
        assert gateway.slots["test"]._value == 2


async def test_rate_limit_enforced():
    stamps = []
    loop = asyncio.get_running_loop()

    def handler(request):
        stamps.append(loop.time())
        return httpx.Response(200)

    async with Gateway(
        {"test": Policy("https://example.org", 1, 0.05, 3)}, transport=httpx.MockTransport(handler)
    ) as gateway:
        await asyncio.gather(gateway.request("test", "/1"), gateway.request("test", "/2"))
    assert stamps[1] - stamps[0] >= 0.045


def test_retry_after_http_date_and_invalid_values():
    now = datetime(2026, 10, 24, 20, 0, 0, tzinfo=UTC)
    assert retry_after("Sat, 24 Oct 2026 20:00:10 GMT", now) == 10
    assert retry_after("NaN") == retry_after("broken") == 0


async def test_cache_db_adapter():
    class Pool:
        async def fetchrow(self, query, key):
            assert key == "key" and "expires_at > now()" in query
            return {"payload": '{"status":200,"body_base64":"e30=","headers":{}}'}

        async def execute(self, query, *params):
            assert params[-1] == DAY and "ON CONFLICT" in query
            assert "payload" in query and "body,headers" not in query

    cache = PostgresCache(Pool())
    assert (await cache.get("key")).cached
    await cache.put("key", HTTPResult(status=200, content=b"{}"), DAY)


async def test_cache_outage_is_incomplete():
    class BrokenCache:
        async def get(self, key):
            raise OSError("database down")

    async with Gateway(POLICIES, cache=BrokenCache()) as gateway:
        assert (await gateway.request("test", "/", ttl=DAY)).error == "HTTP cache unavailable"


async def test_provider_origin_cannot_escape():
    async with Gateway(POLICIES) as gateway:
        assert (await gateway.request("test", "http://provider.example/a")).error
        assert (await gateway.request("test", "https://elsewhere.example/a")).error
