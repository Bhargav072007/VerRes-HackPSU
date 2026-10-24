"""Provider-neutral strict JSON adapter; caller supplies configured model/family/endpoint."""

import html
import json
import secrets
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from app.providers.http import Gateway

PROMPTS = Path(__file__).parent.parent / "prompts"


class ModelFailure(Exception):
    """Expected model service, context-limit or structured-output failure."""


class Model(Protocol):
    model_id: str
    family: str

    async def complete(self, *, task: str, system: str, data: str, schema: dict) -> str: ...


def untrusted(data: object) -> str:
    nonce = secrets.token_hex(16)
    # Escape angle brackets so document-supplied closing tags cannot end the envelope.
    value = html.escape(json.dumps(data, ensure_ascii=False), quote=False)
    return f'<untrusted nonce="{nonce}">{value}</untrusted>'


async def call_model(model: Model, task: str, data: object, schema: type[BaseModel]):
    system = (
        (PROMPTS / "preamble.v1.md").read_text() + "\n" + (PROMPTS / f"{task}.v1.md").read_text()
    )
    response = await model.complete(
        task=task, system=system, data=untrusted(data), schema=schema.model_json_schema()
    )
    if not isinstance(response, str) or len(response) > 100_000:
        raise ModelFailure("model output is missing or oversized")
    return schema.model_validate_json(response)


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
    ):
        if not model_id or not family or not api_key or max_input_chars <= 0:
            raise ValueError("model identity, family, credentials and context limit are required")
        if not gateway.policies[provider].base_url.startswith("https://"):
            raise ValueError("model endpoint must use HTTPS")
        self.gateway, self.provider, self.path = gateway, provider, path
        self.model_id, self.family = model_id, family
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
                    "json_schema": {"name": task, "strict": True, "schema": schema},
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
