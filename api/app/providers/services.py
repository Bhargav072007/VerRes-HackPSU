"""Create injectable contract implementations; Lane A owns job orchestration/lifespan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from api.app.graph.service import GraphService
from api.app.ingest.service import IngestService
from api.app.providers.cache import PostgresCache
from api.app.providers.http import Gateway, Policy, load_policies
from api.app.providers.metadata import Arxiv, Crossref, OpenAlex
from api.app.providers.models import ProviderResult
from api.app.resolve.retraction import PostgresRetractions
from api.app.resolve.service import ResolveService
from api.app.sources.service import SourceService
from api.app.verify.model import Model
from api.app.verify.service import VerifyService
from contracts.interfaces import Graph, Ingest, Resolve, Sources, Verify

if TYPE_CHECKING:
    from api.app.settings import Settings


class UnconfiguredProvider:
    def __init__(self, provider: str, reason: str):
        self.provider, self.reason = provider, reason

    async def lookup(self, identifier: str) -> ProviderResult:
        return ProviderResult(provider=self.provider, definitive=False, reason=self.reason)

    async def search(self, query: str) -> ProviderResult:
        return ProviderResult(provider=self.provider, definitive=False, reason=self.reason)


@dataclass
class BackendServices:
    gateway: Gateway
    ingest: Ingest
    resolve: Resolve
    sources: Sources
    verify: Verify
    graph: Graph

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_):
        await self.gateway.aclose()


def build_backend(
    settings: Settings,
    *,
    pool=None,
    primary: Model | None = None,
    adjudicator: Model | None = None,
    gateway: Gateway | None = None,
    openalex_daily_budget_usd: float = 1.0,
) -> BackendServices:
    if gateway is None:
        policies = load_policies()
        policies["grobid"] = Policy(settings.grobid_url, rate=1, period=1, concurrency=1)
        gateway = Gateway(
            policies,
            cache=PostgresCache(pool) if pool else None,
            daily_budget_usd=openalex_daily_budget_usd,
        )
    crossref = (
        Crossref(gateway, settings.crossref_mailto)
        if settings.crossref_mailto
        else UnconfiguredProvider("crossref", "Crossref mailto is not configured")
    )
    key = settings.openalex_api_key.get_secret_value() if settings.openalex_api_key else None
    openalex, arxiv = OpenAlex(gateway, key), Arxiv(gateway)
    return BackendServices(
        gateway=gateway,
        ingest=IngestService(gateway),
        resolve=ResolveService(
            crossref, openalex, arxiv=arxiv, retractions=PostgresRetractions(pool) if pool else None
        ),
        sources=SourceService(gateway, crossref=crossref, openalex=openalex, arxiv=arxiv),
        verify=VerifyService(primary, adjudicator=adjudicator),
        graph=GraphService(primary),
    )
