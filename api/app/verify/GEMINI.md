# Gemini model integration

VerRes supports Gemini through Google's documented OpenAI-compatible structured
output endpoint. It uses the same HTTP gateway, local Pydantic validation,
escaped document envelopes, quote gates and adjudication rules as OpenAI.
No additional SDK is required.

## Configuration

Keep API keys in the ignored `.env` file or deployment environment. Model names
and `MODEL_PRICES` overrides load from `.env` as well as process environment.

Gemini primary:

```dotenv
GEMINI_API_KEY=<your Gemini API key>
MODEL_PRIMARY=gemini-3.6-flash
```

OpenAI primary with a Gemini adjudicator:

```dotenv
OPENAI_API_KEY=<your OpenAI API key>
GEMINI_API_KEY=<your Gemini API key>
MODEL_PRIMARY=gpt-4.1-mini
MODEL_ADJUDICATOR=gemini-3.6-flash
ADJUDICATOR_ALLOW_SAME_VENDOR=false
```

Gemini can also be primary with an OpenAI adjudicator. `gemini-*` names select
Google; other names retain the existing OpenAI routing. Explicit `gemini:` and
`openai:` prefixes are accepted and stripped before the API request.
No model is selected merely because a key is present. The project number is not
required for this API-key workflow. Deployment secrets must be configured on the
server; a developer's local `.env` is not pushed with the code.

Both roles share durable daily usage accounting, while their provider circuit
breakers remain independent. A Google outage does not open OpenAI's breaker.
`/status` reports each role's vendor/model/state and missing adjudicator setup.
Gemini token costs are recorded as estimates using standard paid-tier rates;
free-tier usage, caching and billing tiers can differ. No OpenAI cache discount
is applied to Gemini. The built-in Gemini 3.6 Flash rates were checked against
Google's official documentation on 2026-10-25. Override rates when necessary:

```dotenv
MODEL_PRICES={"gemini-3.6-flash":[1.5,7.5]}
```

Values are input/output USD per million tokens. Other Gemini model names work
when available to the key; unrecognized pricing uses the existing conservative
configured-rate estimate. Verify model availability rather than assuming that
all documented models are enabled for an account. Missing usage closes further
model calls through the existing accounting guard.

Tests cover all eight production model tasks, primary/adjudicator routing,
independent circuit breakers, shared budget checks, safe failures, provenance,
missing keys, schema validation and cleanup. The integration does not bypass
source-coverage or severe-verdict gates.

## Official references

- [OpenAI-compatible endpoint and structured output](https://ai.google.dev/gemini-api/docs/openai)
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini 3.6 Flash specifications and prices](https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.6)
- [Current pricing](https://ai.google.dev/gemini-api/docs/pricing)
