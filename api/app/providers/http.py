"""TODO(Agent B): own rate limiting, retries, cache, and circuit breaker."""

import httpx

_clients: dict[str, httpx.AsyncClient] = {}


def get_client(provider: str) -> httpx.AsyncClient:
    client = _clients.get(provider)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        _clients[provider] = client
    return client
