"""Startup safety checks (`validate_startup_settings()` in
app/core/config.py) and API-docs gating in production.

The unit tests build `Settings` directly. The subprocess tests import
`app.main` exactly as uvicorn does, so they prove a misconfigured
deployment really exits instead of serving.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings, UnsafeConfigurationError, validate_startup_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROD_DB = "postgresql+psycopg://app:not-the-default@db.internal:5432/sie"


def _settings(**overrides) -> Settings:
    values = {"APP_ENV": "production", "DATABASE_URL": _PROD_DB, "CORS_ALLOWED_ORIGINS": "https://app.example.com"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_a_correct_production_configuration_starts():
    validate_startup_settings(_settings())


@pytest.mark.parametrize("app_env", ["production", "prod", " Production "])
def test_dev_mode_is_refused_in_production(app_env):
    with pytest.raises(UnsafeConfigurationError, match="DEV_MODE is true"):
        validate_startup_settings(_settings(APP_ENV=app_env, DEV_MODE=True))


def test_demo_data_is_refused_in_production():
    with pytest.raises(UnsafeConfigurationError, match="SIE_DEV_DEMO_DATA is true"):
        validate_startup_settings(_settings(SIE_DEV_DEMO_DATA=True))


def test_the_development_database_password_is_refused_in_production():
    with pytest.raises(UnsafeConfigurationError, match="POSTGRES_PASSWORD is the development default"):
        validate_startup_settings(_settings(DATABASE_URL=None))
    # Components with a real password are a valid production configuration.
    validate_startup_settings(_settings(DATABASE_URL=None, POSTGRES_PASSWORD="a-real-password"))


@pytest.mark.parametrize("app_env", ["production", "development"])
@pytest.mark.parametrize("origins", ["*", "https://app.example.com, *"])
def test_a_cors_wildcard_is_refused_everywhere(app_env, origins):
    with pytest.raises(UnsafeConfigurationError, match="CORS_ALLOWED_ORIGINS contains"):
        validate_startup_settings(_settings(APP_ENV=app_env, CORS_ALLOWED_ORIGINS=origins))


def test_every_problem_is_reported_at_once_and_no_value_is_echoed():
    with pytest.raises(UnsafeConfigurationError) as raised:
        validate_startup_settings(
            _settings(DEV_MODE=True, SIE_DEV_DEMO_DATA=True, DATABASE_URL=None, CORS_ALLOWED_ORIGINS="*")
        )
    message = str(raised.value)
    for fragment in ("CORS_ALLOWED_ORIGINS", "DEV_MODE", "SIE_DEV_DEMO_DATA", "POSTGRES_PASSWORD"):
        assert fragment in message
    assert "not-the-default" not in message


def test_development_keeps_its_conveniences():
    validate_startup_settings(_settings(APP_ENV="development", DEV_MODE=True, SIE_DEV_DEMO_DATA=True, DATABASE_URL=None))


@pytest.mark.parametrize(
    "app_env,flag,expected",
    [
        ("development", None, True),
        ("production", None, False),
        ("prod", None, False),
        ("production", True, True),
        ("development", False, False),
    ],
)
def test_api_docs_are_off_in_production_unless_enabled(app_env, flag, expected):
    assert _settings(APP_ENV=app_env, API_DOCS_ENABLED=flag).api_docs_enabled is expected


def _import_app(**env: str) -> subprocess.CompletedProcess:
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in {"APP_ENV", "DEV_MODE", "SIE_DEV_DEMO_DATA", "DATABASE_URL", "CORS_ALLOWED_ORIGINS", "API_DOCS_ENABLED"}
    }
    code = "import app.main as m; print('docs', m.app.docs_url, m.app.openapi_url)"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_misconfigured_production_process_exits_instead_of_serving():
    result = _import_app(APP_ENV="production", DATABASE_URL=_PROD_DB, DEV_MODE="true")
    assert result.returncode != 0
    assert "UnsafeConfigurationError" in result.stderr
    assert "DEV_MODE is true" in result.stderr


def test_a_production_process_starts_without_api_docs():
    result = _import_app(APP_ENV="production", DATABASE_URL=_PROD_DB, EMBEDDING_PROVIDER="hashing")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("docs None None")
