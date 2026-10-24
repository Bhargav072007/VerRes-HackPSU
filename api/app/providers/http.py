"""The only outbound HTTP boundary. Source fetches pin validated DNS answers."""

import asyncio
import hashlib
import ipaddress
import json
import math
import random
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from aiolimiter import AsyncLimiter
from asyncpg import PostgresError

from api.app.providers.cache import Cache, MemoryCache
from api.app.providers.models import HTTPResult

DAY = 86400
MAX_BYTES = 20 * 1024 * 1024

# A1/A2 health/lifespan compatibility. Source downloads must still use safe_fetch;
# this shared client hook is for trusted configured services such as GROBID health.
_clients: dict[str, httpx.AsyncClient] = {}


def get_client(provider: str) -> httpx.AsyncClient:
    client = _clients.get(provider)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0), trust_env=False, follow_redirects=False
        )
        _clients[provider] = client
    return client


@dataclass(frozen=True)
class Policy:
    base_url: str
    rate: float
    period: float
    concurrency: int


@dataclass
class Circuit:
    failures: int = 0
    throttles: deque = field(default_factory=deque)
    open_until: float = 0
    probing: bool = False

    def enter(self, now: float) -> bool:
        if self.open_until:
            if now < self.open_until or self.probing:
                return False
            self.probing = True
        return True

    def record(self, failed: bool, status: int | None, now: float) -> None:
        self.probing = False
        while self.throttles and self.throttles[0] < now - 30:
            self.throttles.popleft()
        if not failed:
            self.failures = 0
            recovering = bool(self.open_until)
            self.open_until = 0
            if recovering:
                self.throttles.clear()
            return
        self.failures += 1
        if status == 429:
            self.throttles.append(now)
        if self.open_until or self.failures >= 5 or len(self.throttles) >= 3:
            self.open_until = now + 60


def retry_after(value: str | None, now: datetime | None = None) -> float:
    try:
        number = float(value)
        return max(0, number) if math.isfinite(number) else 0
    except (TypeError, ValueError):
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            return max(0, (stamp - (now or datetime.now(UTC))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


async def resolve_host(host: str, port: int) -> list[str]:
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(record[4][0] for record in records))


def load_policies(path: Path | None = None) -> dict[str, Policy]:
    config = yaml.safe_load((path or Path(__file__).with_name("providers.yaml")).read_text())
    return {name: Policy(**value) for name, value in config.items()}


class Gateway:
    def __init__(
        self,
        policies: dict[str, Policy] | None = None,
        *,
        cache: Cache | None = None,
        transport=None,
        resolver=resolve_host,
        clock=time.monotonic,
        sleep=asyncio.sleep,
        attempts: int = 3,
        daily_budget_usd: float = 1.0,
    ):
        if policies is None:
            policies = load_policies()
        if attempts < 1 or daily_budget_usd <= 0:
            raise ValueError("positive retry count and daily budget are required")
        if any(p.rate < 1 or p.period <= 0 or p.concurrency < 1 for p in policies.values()):
            raise ValueError("provider policies require positive rate, period and concurrency")
        self.policies = policies
        self.cache = cache if cache is not None else MemoryCache()
        self.clients = {
            name: httpx.AsyncClient(
                base_url=p.base_url,
                transport=transport,
                follow_redirects=False,
                trust_env=False,
                timeout=20,
            )
            for name, p in policies.items()
        }
        self.limiters = {n: AsyncLimiter(p.rate, p.period) for n, p in policies.items()}
        self.slots = {n: asyncio.Semaphore(p.concurrency) for n, p in policies.items()}
        self.circuits = {n: Circuit() for n in policies}
        self.resolver, self.clock, self.sleep = resolver, clock, sleep
        self.attempts = attempts
        self.daily_budget_usd = daily_budget_usd
        self.cost_day = datetime.now(UTC).date()
        self.spent_usd = 0.0
        self.cost_unknown = False
        self.budget_lock = asyncio.Lock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    async def aclose(self):
        await asyncio.gather(*(client.aclose() for client in self.clients.values()))

    async def request(  # noqa: ASYNC109 - enforced with asyncio.timeout inside the gateway
        self,
        provider: str,
        path: str,
        *,
        method="GET",
        ttl=0,
        timeout=20,  # noqa: ASYNC109 - gateway owns the enforced deadline
        **kwargs,  # noqa: ASYNC109
    ) -> HTTPResult:
        # Callers select a configured provider; they cannot redirect it to another host.
        url = httpx.URL(self.policies[provider].base_url).join(path)
        configured = httpx.URL(self.policies[provider].base_url)
        if (url.scheme, url.host, url.port) != (
            configured.scheme,
            configured.host,
            configured.port,
        ):
            return HTTPResult(error="provider URL escaped configured origin")
        if provider == "openalex":
            async with self.budget_lock:
                today = datetime.now(UTC).date()
                if today != self.cost_day:
                    self.cost_day, self.spent_usd, self.cost_unknown = today, 0.0, False
                result = await self._request(provider, url, method, ttl, timeout, **kwargs)
                if result.status == 200 and not result.cached and not result.error:
                    try:
                        cost = result.json()["meta"]["cost_usd"]
                        if isinstance(cost, bool) or not isinstance(cost, int | float):
                            raise ValueError("invalid cost")
                        if not math.isfinite(cost) or cost < 0:
                            raise ValueError("invalid cost")
                        self.spent_usd += cost
                    except (KeyError, TypeError, ValueError):
                        self.cost_unknown = True
                return result
        return await self._request(provider, url, method, ttl, timeout, **kwargs)

    async def _request(self, provider, url, method, ttl, timeout, **kwargs):  # noqa: ASYNC109
        validate_json = kwargs.pop("validate_json", None)
        params = kwargs.get("params", {})
        key = hashlib.sha256(
            f"{provider}:{method}:{url}:{json.dumps(params, sort_keys=True)}".encode()
        ).hexdigest()
        if method == "GET" and ttl:
            try:
                cached = await self.cache.get(key)
            except (PostgresError, OSError):
                return HTTPResult(error="HTTP cache unavailable")
            if cached:
                return cached
        if provider == "openalex" and (
            self.cost_unknown or self.spent_usd >= self.daily_budget_usd
        ):
            return HTTPResult(error="OpenAlex daily cost guard is closed")
        circuit = self.circuits[provider]
        for attempt in range(self.attempts):
            async with self.slots[provider], self.limiters[provider]:
                if not circuit.enter(self.clock()):
                    return HTTPResult(error="provider circuit open")
                try:
                    async with asyncio.timeout(timeout):
                        request = self.clients[provider].build_request(
                            method, url, timeout=timeout, **kwargs
                        )
                        response = await self.clients[provider].send(request, stream=True)
                        try:
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > MAX_BYTES:
                                    raise ValueError("response exceeds 20 MB")
                            result = HTTPResult(
                                status=response.status_code,
                                content=bytes(body),
                                headers=dict(response.headers),
                            )
                        finally:
                            await response.aclose()
                except asyncio.CancelledError:
                    circuit.probing = False
                    raise
                except (httpx.HTTPError, TimeoutError, ValueError) as error:
                    result = HTTPResult(error=f"HTTP request failed: {type(error).__name__}")
            failed = result.error is not None or result.status == 429 or result.status >= 500
            circuit.record(failed, result.status, self.clock())
            if not failed:
                if method == "GET" and ttl and result.status in (200, 404):
                    # Validate JSON for metadata before caching; malformed responses are errors.
                    try:
                        if result.status == 200:
                            payload = result.json()
                            if validate_json:
                                validate_json(payload)
                            if isinstance(payload, dict) and (
                                payload.get("results") == []
                                or isinstance(payload.get("message"), dict)
                                and payload["message"].get("items") == []
                            ):
                                ttl = DAY
                    except (
                        ValueError,
                        UnicodeDecodeError,
                        KeyError,
                        TypeError,
                        IndexError,
                        AttributeError,
                    ):
                        return HTTPResult(status=result.status, error="invalid provider JSON")
                    try:
                        await self.cache.put(key, result, DAY if result.status == 404 else ttl)
                    except (PostgresError, OSError):
                        return HTTPResult(error="HTTP cache unavailable")
                return result
            if attempt + 1 < self.attempts:
                delay = max(
                    retry_after(result.headers.get("retry-after")),
                    random.uniform(0, min(8, 2**attempt)),
                )
                # Do not violate long Retry-After values; hand back an incomplete result.
                if delay > 20:
                    return HTTPResult(
                        status=result.status, error="Retry-After exceeds retry budget"
                    )
                await self.sleep(delay)
        return result

    async def safe_fetch(self, url: str) -> HTTPResult:
        try:
            async with asyncio.timeout(20):
                for _ in range(6):
                    target = httpx.URL(url)
                    if (
                        target.scheme != "https"
                        or not target.host
                        or target.userinfo
                        or target.port not in (None, 443)
                    ):
                        return HTTPResult(error="source URL must be HTTPS without credentials")
                    addresses = await self.resolver(target.host, 443)
                    parsed = [ipaddress.ip_address(ip) for ip in addresses]
                    if not parsed or any(
                        not ip.is_global
                        or ip.is_multicast
                        or ip.is_reserved
                        or bool(getattr(ip, "sixtofour", None))
                        or bool(getattr(ip, "teredo", None))
                        for ip in parsed
                    ):
                        return HTTPResult(error="source destination is not public")
                    # Connect to the validated IP, preserving TLS SNI and HTTP Host. No second
                    # hostname resolution occurs at connection time (DNS rebinding defense).
                    pinned = target.copy_with(host=addresses[0])
                    result = await self._request(
                        "arxiv" if target.host in {"arxiv.org", "export.arxiv.org"} else "source",
                        pinned,
                        "GET",
                        0,
                        20,
                        headers={"Host": target.netloc.decode(), "Connection": "close"},
                        extensions={"sni_hostname": target.host},
                    )
                    if result.status in (301, 302, 303, 307, 308):
                        location = result.headers.get("location")
                        if not location:
                            return HTTPResult(error="redirect has no location")
                        url = urljoin(url, location)
                        continue
                    return result
                return HTTPResult(error="too many source redirects")
        except (httpx.InvalidURL, ValueError, OSError, TimeoutError):
            return HTTPResult(error="source URL or DNS lookup failed")
