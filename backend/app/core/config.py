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

    # Identity & access (see app/api/deps_auth.py, app/services/identity_service.py)
    #
    # DEV_MODE gates the one development-only identity mechanism this
    # codebase has: a request header naming an existing user id, trusted
    # without any cryptographic verification (see
    # app/api/deps_auth.py::get_dev_authenticated_user_id). It defaults to
    # False specifically so a deployment that forgets to configure real
    # authentication fails closed (every authenticated route returns 501,
    # not "trust a header") rather than silently accepting spoofed
    # identity. This must never be set true in a production environment —
    # see the README's "Identity architecture" section.
    DEV_MODE: bool = False

    # Ingestion (see app/ingestion/storage.py, app/ingestion/pipeline.py)
    #
    # Local-filesystem StorageProvider root. Development-only, per the
    # milestone spec — a production deployment swaps
    # get_storage_provider() for an object-storage-backed implementation
    # rather than pointing this at a "real" path.
    INGESTION_STORAGE_DIR: str = "var/ingested_files"
    # Hard cap on one uploaded file's size, enforced before any parsing
    # is attempted. 25 MiB is a reasonable default for the document/
    # spreadsheet/presentation formats this milestone supports.
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

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
