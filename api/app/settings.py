from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: SecretStr = SecretStr("postgresql://verres@127.0.0.1:5432/verres")
    grobid_url: str = "http://127.0.0.1:8070"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    crossref_mailto: str | None = None
    frontend_origin: str = "http://localhost:3000"
    data_dir: Path = Path("data")
    llm_daily_budget: float = 10.0
    env: Literal["development", "test", "production"] = "development"
