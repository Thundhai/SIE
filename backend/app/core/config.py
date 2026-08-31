"""Environment-based application configuration.

Settings are read from process environment variables (and a local .env file
in development, see .env.example) via pydantic-settings. Nothing in this
module hardcodes secrets or environment-specific values.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    APP_NAME: str = "SIE - Safety Intelligence Engine"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    # Either set DATABASE_URL directly, or set the POSTGRES_* components and
    # let it be assembled below.
    DATABASE_URL: str | None = None

    POSTGRES_USER: str = "sie"
    POSTGRES_PASSWORD: str = "sie"
    POSTGRES_DB: str = "sie"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment variables are parsed once per process; tests that
    need different settings should construct Settings() directly instead of
    mutating the cached singleton.
    """
    return Settings()


settings = get_settings()
