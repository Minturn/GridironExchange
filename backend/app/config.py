from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.2.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRIDX_", env_file=".env", extra="ignore")

    # SQLite for local dev; Postgres on the deploy target (Fly.io).
    database_url: str = "sqlite:///./gridx.db"
    port: int = 8200
    # MUST be overridden in production (GRIDX_SECRET_KEY) — signs session cookies.
    secret_key: str = "dev-only-not-a-secret"
    # Background jobs (player sync, game locks, Tuesday dividends). Off for dev/tests.
    enable_scheduler: bool = False
    # Where the built frontend lives in the deploy image; served if present.
    static_dir: str = "../frontend/dist"


settings = Settings()
