"""Gemini's documented OpenAI-compatible structured-output endpoint."""

from api.app.providers.http import Gateway
from api.app.verify.model import JSONGatewayModel


class GeminiModel(JSONGatewayModel):
    def __init__(
        self, gateway: Gateway, *, model_id: str, api_key: str, max_input_chars: int = 100_000
    ):
        super().__init__(
            gateway,
            provider="gemini",
            model_id=model_id,
            family="gemini",
            vendor="google",
            api_key=api_key,
            max_input_chars=max_input_chars,
            path="/v1beta/openai/chat/completions",
            temperature=None,
        )
