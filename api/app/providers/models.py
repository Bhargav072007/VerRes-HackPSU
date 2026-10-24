from typing import Any

from pydantic import Field

from api.app.ingest.models import Record


class Work(Record):
    provider: str
    id: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv: str | None = None
    abstract: str | None = None
    abstract_origin: str | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    oa_url: str | None = None
    is_retracted: bool | None = None


class ProviderResult(Record):
    provider: str
    definitive: bool
    works: list[Work] = Field(default_factory=list)
    reason: str | None = None


class HTTPResult(Record):
    status: int | None = None
    content: bytes = b""
    headers: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    cached: bool = False

    def json(self) -> Any:
        import json

        return json.loads(self.content)
