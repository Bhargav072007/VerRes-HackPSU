"""Configure independent model vendors with one accounting gateway."""

import os

from api.app.db import Jobs
from api.app.providers.http import Policy
from api.app.review.runtime import ResilientGateway
from api.app.verify.gemini import GeminiModel
from api.app.verify.model import JSONGatewayModel


def model_spec(name, settings):
    vendor = "gemini" if name.startswith(("gemini-", "gemini:")) else "review"
    model_id = name.removeprefix("gemini:") if vendor == "gemini" else name.removeprefix("openai:")
    key = settings.gemini_api_key if vendor == "gemini" else settings.openai_api_key
    return vendor, model_id, key


def build_models(settings, pool=None, *, primary=None):
    name = (os.getenv("MODEL_PRIMARY") or settings.model_primary or "").strip() or (
        os.getenv("REVIEW_MODEL") or settings.review_model or ""
    ).strip()
    second_name = (os.getenv("MODEL_ADJUDICATOR") or settings.model_adjudicator or "").strip()
    reason = None if primary else "model not configured"
    second_reason = "set MODEL_ADJUDICATOR" if not second_name else None
    specs = {}
    if primary is None and name:
        specs["primary"] = model_spec(name, settings)
    if (primary is not None or name) and second_name:
        specs["adjudicator"] = model_spec(second_name, settings)
    policies = {
        vendor: Policy(
            "https://generativelanguage.googleapis.com"
            if vendor == "gemini"
            else "https://api.openai.com",
            4,
            1,
            3,
        )
        for vendor, _, key in specs.values()
        if key
    }
    gateway = (
        ResilientGateway(
            policies,
            jobs=Jobs(pool) if pool else None,
            daily_budget_usd=settings.llm_daily_budget,
            price_overrides=settings.model_prices,
        )
        if policies
        else None
    )
    models = {"primary": primary, "adjudicator": None}
    for role, (vendor, model_id, key) in specs.items():
        if not key:
            missing = (
                "GEMINI_API_KEY is not set" if vendor == "gemini" else "OPENAI_API_KEY is not set"
            )
            if role == "primary":
                reason = missing if vendor == "gemini" else "model not configured"
            else:
                second_reason = missing
            continue
        if vendor == "gemini":
            models[role] = GeminiModel(gateway, model_id=model_id, api_key=key.get_secret_value())
        else:
            models[role] = JSONGatewayModel(
                gateway,
                provider="review",
                model_id=model_id,
                family="openai",
                vendor="openai",
                api_key=key.get_secret_value(),
                max_input_chars=100_000,
            )
        if role == "primary":
            reason = None
    if primary is None and not name and (settings.openai_api_key or settings.gemini_api_key):
        reason = "set MODEL_PRIMARY"
    return gateway, models["primary"], models["adjudicator"], reason, second_reason
