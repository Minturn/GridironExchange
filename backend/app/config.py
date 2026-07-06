from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRIDX_", env_file=".env", extra="ignore")

    # SQLite for local dev; Postgres on the deploy target (Fly.io).
    database_url: str = "sqlite:///./gridx.db"
    port: int = 8200


settings = Settings()
