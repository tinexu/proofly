"""App settings, read from environment variables or api/.env.

Never commit a real .env file. Copy .env.example to .env for local development.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROOFLY_", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://proofly:proofly@localhost:5432/proofly"
    # Comma-separated list of web origins allowed to call the API.
    cors_origins: str = "http://localhost:3000"

    # Sign-in (Day 3). Links in emails point at the web app.
    web_base_url: str = "http://localhost:3000"
    magic_link_ttl_minutes: int = 15
    # Max sign-in emails per address per hour; extra requests are silently dropped.
    magic_link_hourly_limit: int = 5
    # "console" prints emails to the terminal. A real provider arrives in Week 8.
    email_backend: str = "console"

    # Sessions (Day 4).
    session_cookie_name: str = "proofly_session"
    session_ttl_days: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()