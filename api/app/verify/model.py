"""Provider-neutral strict JSON adapter; caller supplies configured model/family/endpoint."""

import html
import json
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from api.app.providers.http import Gateway

PROMPTS = Path(__file__).parent.parent / "prompts"
PROMPT_VERSIONS = {"judge": "v3", "adjudicate": "v3"}


class ModelFailure(Exception):
    """Expected model service, context-limit or structured-output failure."""


class Model(Protocol):
    model_id: str
    family: str
    vendor: str | None

    async def complete(self, *, task: str, system: str, data: str, schema: dict) -> str: ...


def untrusted(data: object) -> str:
    nonce = secrets.token_hex(16)
    # Escape angle brackets so document-supplied closing tags cannot end the envelope.
    value = html.escape(json.dumps(data, ensure_ascii=False), quote=False)
    return f'<untrusted nonce="{nonce}">{value}</untrusted>'


def output_schema(task: str, schema: type[BaseModel]) -> dict:
    result = schema.model_json_schema()
    if task in {"judge", "adjudicate"}:
        result["properties"]["evidence"]["maxItems"] = 3
    return result


async def call_model(model: Model, task: str, data: object, schema: type[BaseModel]):
    version = PROMPT_VERSIONS.get(task, "v1")
    system = (
        (PROMPTS / "preamble.v1.md").read_text()
        + "\n"
        + (PROMPTS / f"{task}.{version}.md").read_text()
    )
    response = await model.complete(
        task=task, system=system, data=untrusted(data), schema=output_schema(task, schema)
    )
    if not isinstance(response, str) or len(response) > 100_000:
        raise ModelFailure("model output is missing or oversized")
    result = schema.model_validate_json(response)
    if task in {"judge", "adjudicate"} and len(result.evidence) > 3:
        raise ModelFailure("judge returned more than three evidence quotes")
    return result


def strict_schema(schema: dict) -> dict:
    """Render shared schemas for strict JSON providers without changing contracts.

    Public Pydantic defaults remain intact. The provider must explicitly emit every
    object property; nullable fields retain their existing null alternatives.
    """
    result = deepcopy(schema)

    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


class JSONGatewayModel:
    """Adapter for a configured chat-completions-compatible service; no default model/key.

    Add its HTTPS origin as a Gateway policy. Credentials stay in memory, never cache keys.
    The integrator must configure a true context limit; the adapter never truncates sources.
    """

    def __init__(
        self,
        gateway: Gateway,
        *,
        provider: str,
        model_id: str,
        family: str,
        api_key: str,
        max_input_chars: int,
        path="/v1/chat/completions",
        vendor: str | None = None,
    ):
        if not model_id or not family or not api_key or max_input_chars <= 0:
            raise ValueError("model identity, family, credentials and context limit are required")
        if not gateway.policies[provider].base_url.startswith("https://"):
            raise ValueError("model endpoint must use HTTPS")
        self.gateway, self.provider, self.path = gateway, provider, path
        self.model_id, self.family = model_id, family
        self.vendor = vendor
        self.api_key, self.max_input_chars = api_key, max_input_chars

    async def complete(self, *, task, system, data, schema) -> str:
        if len(system) + len(data) > self.max_input_chars:
            raise ModelFailure("complete source exceeds configured model context limit")
        result = await self.gateway.request(
            self.provider,
            self.path,
            method="POST",
            timeout=60,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_id,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": data},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": task, "strict": True, "schema": strict_schema(schema)},
                },
            },
        )
        if result.error or result.status != 200:
            raise ModelFailure("model service failed")
        try:
            choice = result.json()["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ModelFailure("model did not finish a complete structured response")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ModelFailure("model response content is missing")
            return content
        except (ValueError, TypeError, KeyError, IndexError) as error:
            raise ModelFailure("malformed model service response") from error


def _openai_tuples(node):
    """OpenAI strict mode rejects tuple schemas (prefixItems); emit plain arrays instead."""
    if isinstance(node, dict):
        if "prefixItems" in node:
            prefix = node.pop("prefixItems")
            node.pop("minItems", None)
            node.pop("maxItems", None)
            same = all(item == prefix[0] for item in prefix)
            node["items"] = prefix[0] if same else {"anyOf": prefix}
        for value in node.values():
            _openai_tuples(value)
    elif isinstance(node, list):
        for value in node:
            _openai_tuples(value)
    return node


_strict_schema_base = strict_schema


def strict_schema(schema):  # noqa: F811 - wraps the base builder for OpenAI compatibility
    return _openai_tuples(_strict_schema_base(schema))
