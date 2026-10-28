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

#: Settings these tests control. Cleared from the environment for every
#: test (and for the subprocess), so a developer's exported values -- an
#: `APP_ENV=development`, say -- cannot turn an "unset" case into a set one.
_CONTROLLED_ENV = (
    "APP_ENV",
    "RENDER",
    "DEV_MODE",
    "SIE_DEV_DEMO_DATA",
    "DEBUG",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "CORS_ALLOWED_ORIGINS",
    "API_DOCS_ENABLED",
)


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    for key in _CONTROLLED_ENV:
        monkeypatch.delenv(key, raising=False)


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


def test_debug_is_refused_in_production():
    with pytest.raises(UnsafeConfigurationError, match="DEBUG is true"):
        validate_startup_settings(_settings(DEBUG=True))


def test_the_development_database_password_is_refused_in_production():
    with pytest.raises(UnsafeConfigurationError, match="POSTGRES_PASSWORD is the development default"):
        validate_startup_settings(_settings(DATABASE_URL=None))
    # Components with a real password are a valid production configuration.
    validate_startup_settings(_settings(DATABASE_URL=None, POSTGRES_PASSWORD="a-real-password"))


def test_the_development_password_inside_database_url_is_refused_in_production():
    with pytest.raises(UnsafeConfigurationError, match="DATABASE_URL uses the development default password"):
        validate_startup_settings(_settings(DATABASE_URL="postgresql+psycopg://sie:sie@db.internal:5432/sie"))
    # A URL without a password (e.g. a socket or IAM login) is not refused.
    validate_startup_settings(_settings(DATABASE_URL="postgresql+psycopg://app@db.internal:5432/sie"))


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://app@db.internal:5432/sie?password=sie",
        "postgresql+psycopg://app:a-real-password@db.internal:5432/sie?password=sie",
    ],
)
def test_a_query_string_password_override_is_checked(url):
    """The psycopg dialect lets `?password=` override the authority's
    password, so the guard must check the password actually used."""
    with pytest.raises(UnsafeConfigurationError, match="DATABASE_URL uses the development default password"):
        validate_startup_settings(_settings(DATABASE_URL=url))


def test_a_real_query_string_password_overrides_a_default_authority_password():
    validate_startup_settings(
        _settings(DATABASE_URL="postgresql+psycopg://app:sie@db.internal:5432/sie?password=a-real-password")
    )


def test_app_env_means_the_same_to_every_production_guard(monkeypatch):
    """The startup checks and the embedding/LLM provider guards share
    `settings.is_production`, so a padded or capitalised APP_ENV cannot
    satisfy one and slip past the other."""
    from app.embeddings.provider import HashingProviderInProductionError, build_embedding_provider

    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", " Production ")
    with pytest.raises(HashingProviderInProductionError):
        build_embedding_provider()


@pytest.mark.parametrize("app_env", ["production", "development"])
@pytest.mark.parametrize("origins", ["*", "https://app.example.com, *"])
def test_a_cors_wildcard_is_refused_everywhere(app_env, origins):
    with pytest.raises(UnsafeConfigurationError, match="CORS_ALLOWED_ORIGINS contains"):
        validate_startup_settings(_settings(APP_ENV=app_env, CORS_ALLOWED_ORIGINS=origins))


def test_every_problem_is_reported_at_once_and_no_value_is_echoed():
    with pytest.raises(UnsafeConfigurationError) as raised:
        validate_startup_settings(
            _settings(DEV_MODE=True, SIE_DEV_DEMO_DATA=True, DEBUG=True, DATABASE_URL=None, CORS_ALLOWED_ORIGINS="*")
        )
    message = str(raised.value)
    for fragment in ("CORS_ALLOWED_ORIGINS", "DEV_MODE", "SIE_DEV_DEMO_DATA", "DEBUG", "POSTGRES_PASSWORD"):
        assert fragment in message
    with pytest.raises(UnsafeConfigurationError) as raised:
        validate_startup_settings(_settings(DATABASE_URL="postgresql+psycopg://sie:sie@db.internal:5432/sie"))
    assert "db.internal" not in str(raised.value)


def test_development_keeps_its_conveniences():
    validate_startup_settings(
        _settings(APP_ENV="development", DEV_MODE=True, SIE_DEV_DEMO_DATA=True, DEBUG=True, DATABASE_URL=None)
    )


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


def _render_settings(**overrides) -> Settings:
    """A Render service: RENDER=true and, unless given, no APP_ENV at all
    (not even the default passed explicitly)."""
    values = {"RENDER": True, "DATABASE_URL": _PROD_DB, "CORS_ALLOWED_ORIGINS": "https://app.example.com"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_render_without_app_env_counts_as_a_real_deployment():
    settings = _render_settings()
    assert settings.APP_ENV == "development"
    assert settings.is_deployed and not settings.is_production
    validate_startup_settings(settings)


@pytest.mark.parametrize(
    "flag,fragment",
    [
        ({"DEV_MODE": True}, "DEV_MODE is true"),
        ({"SIE_DEV_DEMO_DATA": True}, "SIE_DEV_DEMO_DATA is true"),
        ({"DEBUG": True}, "DEBUG is true"),
        ({"DATABASE_URL": None}, "POSTGRES_PASSWORD is the development default"),
    ],
)
def test_render_without_app_env_gets_the_production_checks(flag, fragment):
    with pytest.raises(UnsafeConfigurationError, match=fragment):
        validate_startup_settings(_render_settings(**flag))


def test_an_explicit_non_production_app_env_on_render_opts_out():
    """A deliberately configured staging service on Render keeps its
    development conveniences."""
    settings = _render_settings(APP_ENV="staging", DEV_MODE=True, DEBUG=True)
    assert not settings.is_deployed
    validate_startup_settings(settings)


def test_render_hides_api_docs_unless_enabled():
    assert _render_settings().api_docs_enabled is False
    assert _render_settings(API_DOCS_ENABLED=True).api_docs_enabled is True


def test_render_does_not_trigger_the_test_provider_guards(monkeypatch):
    """The embedding/LLM guards stay on APP_ENV: a Render service still on
    the default test providers keeps serving instead of failing requests."""
    from app.embeddings.provider import build_embedding_provider
    from app.llm.provider import build_llm_provider

    monkeypatch.setattr("app.core.config.settings", _render_settings())
    monkeypatch.setattr("app.embeddings.provider.settings", _render_settings())
    monkeypatch.setattr("app.llm.provider.settings", _render_settings())
    assert build_embedding_provider(provider="hashing") is not None
    assert build_llm_provider(provider="fake") is not None


def _import_app(tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    """Imports app.main in a child process run from an empty directory,
    with the backend on PYTHONPATH, so a developer's backend/.env (which
    Settings reads from the working directory) cannot change the result."""
    clean = {key: value for key, value in os.environ.items() if key not in _CONTROLLED_ENV}
    code = "import app.main as m; print('docs', m.app.docs_url, m.app.openapi_url)"
    pythonpath = os.pathsep.join(filter(None, [str(BACKEND_DIR), clean.get("PYTHONPATH")]))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**clean, **env, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_misconfigured_production_process_exits_instead_of_serving(tmp_path):
    result = _import_app(tmp_path, APP_ENV="production", DATABASE_URL=_PROD_DB, DEV_MODE="true")
    assert result.returncode != 0
    assert "UnsafeConfigurationError" in result.stderr
    assert "DEV_MODE is true" in result.stderr


def test_a_production_process_starts_without_api_docs(tmp_path):
    result = _import_app(tmp_path, APP_ENV="production", DATABASE_URL=_PROD_DB, EMBEDDING_PROVIDER="hashing")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("docs None None")


def test_a_render_process_without_app_env_refuses_dev_mode(tmp_path):
    result = _import_app(tmp_path, RENDER="true", DATABASE_URL=_PROD_DB, DEV_MODE="true")
    assert result.returncode != 0
    assert "DEV_MODE is true" in result.stderr


def test_a_render_process_without_app_env_starts_without_api_docs(tmp_path):
    result = _import_app(tmp_path, RENDER="true", DATABASE_URL=_PROD_DB)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("docs None None")
