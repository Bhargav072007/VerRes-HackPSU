from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: SecretStr = SecretStr("postgresql://verres@127.0.0.1:5432/verres")
    grobid_url: str = "http://127.0.0.1:8070"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    model_primary: str | None = None
    model_adjudicator: str | None = None
    review_model: str | None = None
    gemini_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    crossref_mailto: str | None = None
    frontend_origin: str = "http://localhost:3000"
    data_dir: Path = Path("data")
    llm_daily_budget: float = 10.0
    jobs_per_hour_per_ip: int = Field(default=100, ge=1)
    rate_limit_allowlist: str = ""
    forwarded_allow_ips: str = ""
    env: Literal["dev", "development", "test", "production"] = "development"
