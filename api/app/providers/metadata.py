import re
from urllib.parse import quote

from api.app.providers.arxiv import Arxiv as Arxiv
from api.app.providers.http import DAY, Gateway
from api.app.providers.models import ProviderResult, Work


def normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/|^doi:\s*", "", value.strip(), flags=re.I)
    return value.lower() if re.fullmatch(r"10\.\d{4,9}/\S+", value, re.I) else None


def first_string(value):
    return value[0] if isinstance(value, list) and value and isinstance(value[0], str) else None


def crossref_work(item: dict) -> Work:
    stamp = item.get("published", {}).get("date-parts", [[]])[0]
    year = stamp[0] if stamp and type(stamp[0]) is int else None
    return Work(
        provider="crossref",
        id=item["DOI"],
        doi=normalize_doi(item["DOI"]),
        title=first_string(item.get("title")),
        authors=[a["family"] for a in item.get("author", []) if isinstance(a.get("family"), str)],
        year=year,
        venue=first_string(item.get("container-title")),
        abstract=item.get("abstract") if isinstance(item.get("abstract"), str) else None,
        abstract_origin="crossref" if item.get("abstract") else None,
        updated_by=item.get("updated-by", []),
        update_to=item.get("update-to", []),
    )


def openalex_work(item: dict) -> Work:
    location = item.get("best_oa_location") or {}
    source = (item.get("primary_location") or {}).get("source") or {}
    authors = [
        a["author"]["display_name"].strip()
        for a in item.get("authorships", [])
        if isinstance(a.get("author", {}).get("display_name"), str)
        and a["author"]["display_name"].split()
    ]
    return Work(
        provider="openalex",
        id=item["id"],
        title=item.get("title"),
        doi=normalize_doi(item.get("doi")),
        authors=authors,
        author_names_are_full=True,
        year=item.get("publication_year"),
        venue=source.get("display_name"),
        oa_url=location.get("pdf_url"),
        is_retracted=item.get("is_retracted"),
        abstract_inverted_index=item.get("abstract_inverted_index"),
        abstract_origin="openalex" if item.get("abstract_inverted_index") else None,
    )


class Crossref:
    def __init__(self, gateway: Gateway, mailto: str):
        if not mailto or "@" not in mailto:
            raise ValueError("Crossref requires a configured mailto address")
        self.gateway, self.mailto = gateway, mailto

    async def lookup(self, doi: str) -> ProviderResult:
        value = normalize_doi(doi)
        if not value:
            return ProviderResult(provider="crossref", definitive=False, reason="invalid DOI")
        return await self._get(
            "crossref_single", "/works/" + quote(value, safe=""), {}, single=True
        )

    async def search(self, raw: str) -> ProviderResult:
        return await self._get("crossref_query", "/works", {"query.bibliographic": raw, "rows": 5})

    async def _get(self, provider, path, params, single=False):
        def validate(payload):
            items = [payload["message"]] if single else payload["message"]["items"]
            if not isinstance(items, list):
                raise ValueError("invalid items")
            for item in items:
                work = crossref_work(item)
                if not work.doi or not work.title:
                    raise ValueError("missing identity metadata")

        response = await self.gateway.request(
            provider,
            path,
            params={**params, "mailto": self.mailto},
            ttl=30 * DAY if single else 7 * DAY,
            validate_json=validate,
        )
        if response.status == 404:
            return ProviderResult(provider="crossref", definitive=True)
        if response.error or response.status != 200:
            return ProviderResult(
                provider="crossref",
                definitive=False,
                reason=response.error or f"HTTP {response.status}",
            )
        try:
            payload = response.json()["message"]
            items = [payload] if single else payload["items"]
            works = [crossref_work(item) for item in items]
            if any(not w.doi or not w.title for w in works):
                raise ValueError("missing identity metadata")
            return ProviderResult(provider="crossref", definitive=True, works=works)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return ProviderResult(
                provider="crossref", definitive=False, reason="malformed metadata"
            )


class OpenAlex:
    def __init__(self, gateway: Gateway, api_key: str | None = None):
        self.gateway, self.api_key = gateway, api_key

    async def lookup(self, doi: str) -> ProviderResult:
        value = normalize_doi(doi)
        if not value:
            return ProviderResult(provider="openalex", definitive=False, reason="invalid DOI")
        return await self._get("/works/" + quote("https://doi.org/" + value, safe=""), {}, True)

    async def search(self, title: str) -> ProviderResult:
        return await self._get("/works", {"search": title, "per-page": 5})

    async def _get(self, path, params, single=False):
        if self.api_key:
            params = {**params, "api_key": self.api_key}

        def validate(payload):
            items = [payload] if single else payload["results"]
            if not isinstance(items, list):
                raise ValueError("invalid items")
            for item in items:
                if not openalex_work(item).title:
                    raise ValueError("missing title")

        response = await self.gateway.request(
            "openalex", path, params=params, ttl=7 * DAY, validate_json=validate
        )
        if response.status == 404:
            return ProviderResult(provider="openalex", definitive=True)
        if response.error or response.status != 200:
            return ProviderResult(
                provider="openalex",
                definitive=False,
                reason=response.error or f"HTTP {response.status}",
            )
        try:
            payload = response.json()
            works = [openalex_work(item) for item in ([payload] if single else payload["results"])]
            if any(not w.title for w in works):
                raise ValueError("missing title")
            return ProviderResult(provider="openalex", definitive=True, works=works)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return ProviderResult(
                provider="openalex", definitive=False, reason="malformed metadata"
            )
