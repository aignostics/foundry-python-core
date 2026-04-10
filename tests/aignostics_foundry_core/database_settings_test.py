"""Tests for DatabaseSettings."""

from pathlib import Path

import pytest

from aignostics_foundry_core.database import DatabaseSettings
from aignostics_foundry_core.foundry import reset_context, set_context
from tests.conftest import make_context

# Constants (SonarQube S1192)
POSTGRES_URL = "postgresql+asyncpg://user:pass@localhost:5432/postgres"
POSTGRES_URL_PSYCOPG = "postgresql+psycopg://user:pass@localhost:5432/postgres"
SQLITE_URL = "sqlite+aiosqlite:///test.db"
WRONG_SQLITE_URL = "sqlite+aiosqlite:///wrong.db"
MYAPP_ENV_PREFIX = "MYAPP_"
MYAPP_DB_URL_KEY = "MYAPP_DB_URL"
CUSTOM_PREFIX = "CUSTOM_DB_"
CUSTOM_PREFIX_URL_ENV = "CUSTOM_DB_URL"
DEFAULT_POOL_SIZE = 10
DEFAULT_POOL_MAX_OVERFLOW = 10
DEFAULT_POOL_TIMEOUT = 30
OVERRIDE_POOL_SIZE = 5
OVERRIDE_POOL_MAX_OVERFLOW = 20
OVERRIDE_POOL_TIMEOUT = 60
TEST_DB_PREFIX = "TEST_DB_"
TEST_DB_NAME_ENV = "TEST_DB_NAME"


# ---------------------------------------------------------------------------
# get_url behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_url_returns_plain_url_when_db_name_not_set() -> None:
    """get_url() returns the raw secret value unchanged when database name is None."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL)
    assert settings.get_url() == POSTGRES_URL_PSYCOPG


@pytest.mark.unit
def test_get_url_replaces_db_name_in_path() -> None:
    """get_url() substitutes the path component when name is set."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL, name="mydb")
    result = settings.get_url()
    assert result.endswith("/mydb")
    assert "postgres" not in result.split("/")[-1]


@pytest.mark.unit
def test_get_url_preserves_scheme_and_host() -> None:
    """Scheme, host, and port are intact after name substitution."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL, name="mydb")
    result = settings.get_url()
    assert result.startswith("postgresql+psycopg://")
    assert "localhost:5432" in result


@pytest.mark.unit
def test_get_url_normalises_asyncpg_to_psycopg() -> None:
    """get_url() rewrites +asyncpg to +psycopg in the returned URL."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL)
    result = settings.get_url()
    assert "+asyncpg" not in result
    assert "+psycopg" in result


@pytest.mark.unit
def test_get_url_leaves_non_asyncpg_schemes_unchanged() -> None:
    """get_url() does not modify URLs that do not contain +asyncpg."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=SQLITE_URL)
    assert settings.get_url() == SQLITE_URL


# ---------------------------------------------------------------------------
# env-prefix resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_env_prefix_reads_from_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructing DatabaseSettings() without _env_prefix reads from {ctx.env_prefix}DB_URL."""
    ctx = make_context(env_prefix="MYAPP_")
    set_context(ctx)
    monkeypatch.setenv("MYAPP_DB_URL", POSTGRES_URL)

    settings = DatabaseSettings()
    assert settings.get_url() == POSTGRES_URL_PSYCOPG


@pytest.mark.unit
def test_explicit_env_prefix_overrides_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing _env_prefix reads from that prefix regardless of the active context."""
    ctx = make_context(env_prefix="MYAPP_")
    set_context(ctx)
    monkeypatch.setenv("MYAPP_DB_URL", "postgresql+asyncpg://wrong/wrong")
    monkeypatch.setenv(CUSTOM_PREFIX_URL_ENV, POSTGRES_URL)

    settings = DatabaseSettings(_env_prefix=CUSTOM_PREFIX)
    assert settings.get_url() == POSTGRES_URL_PSYCOPG


# ---------------------------------------------------------------------------
# Pool parameter defaults and overrides
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pool_defaults_are_applied() -> None:
    """pool_size, pool_max_overflow, pool_timeout take their defaults when not set in env."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=SQLITE_URL)
    assert settings.pool_size == DEFAULT_POOL_SIZE
    assert settings.pool_max_overflow == DEFAULT_POOL_MAX_OVERFLOW
    assert int(settings.pool_timeout) == DEFAULT_POOL_TIMEOUT


@pytest.mark.unit
def test_pool_overrides_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pool params read from {PREFIX}POOL_SIZE, {PREFIX}POOL_MAX_OVERFLOW, {PREFIX}POOL_TIMEOUT."""
    monkeypatch.setenv("TEST_DB_URL", SQLITE_URL)
    monkeypatch.setenv("TEST_DB_POOL_SIZE", str(OVERRIDE_POOL_SIZE))
    monkeypatch.setenv("TEST_DB_POOL_MAX_OVERFLOW", str(OVERRIDE_POOL_MAX_OVERFLOW))
    monkeypatch.setenv("TEST_DB_POOL_TIMEOUT", str(OVERRIDE_POOL_TIMEOUT))

    settings = DatabaseSettings(_env_prefix="TEST_DB_")
    assert settings.pool_size == OVERRIDE_POOL_SIZE
    assert settings.pool_max_overflow == OVERRIDE_POOL_MAX_OVERFLOW
    assert int(settings.pool_timeout) == OVERRIDE_POOL_TIMEOUT


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_db_name_reads_from_name_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting {PREFIX}NAME populates name and get_url() substitutes the database name."""
    monkeypatch.setenv("TEST_DB_URL", POSTGRES_URL)
    monkeypatch.setenv(TEST_DB_NAME_ENV, "mydb")

    settings = DatabaseSettings(_env_prefix=TEST_DB_PREFIX)

    assert settings.name == "mydb"
    assert settings.get_url().endswith("/mydb")


@pytest.mark.unit
def test_raw_url_is_masked_in_repr() -> None:
    """repr(settings) does not expose the secret value of raw_url."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL)
    representation = repr(settings)
    assert "pass" not in representation
    assert "**" in representation or "SecretStr" in representation


# ---------------------------------------------------------------------------
# env-file resolution via context (integration)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_database_settings_reads_url_from_env_file_via_context(tmp_path: Path) -> None:
    """DatabaseSettings() with no args reads URL from context env_file when context is set."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"{MYAPP_DB_URL_KEY}={SQLITE_URL}\n")

    ctx = make_context(env_prefix=MYAPP_ENV_PREFIX, env_file=[env_file])
    set_context(ctx)

    settings = DatabaseSettings()
    assert settings.get_url() == SQLITE_URL


@pytest.mark.integration
def test_database_settings_explicit_env_file_overrides_context(tmp_path: Path) -> None:
    """An explicit _env_file passed to DatabaseSettings() takes precedence over the context env_file."""
    context_env_file = tmp_path / "context.env"
    context_env_file.write_text(f"{MYAPP_DB_URL_KEY}={WRONG_SQLITE_URL}\n")

    explicit_env_file = tmp_path / "explicit.env"
    explicit_env_file.write_text(f"{MYAPP_DB_URL_KEY}={SQLITE_URL}\n")

    ctx = make_context(env_prefix=MYAPP_ENV_PREFIX, env_file=[context_env_file])
    set_context(ctx)

    settings = DatabaseSettings(_env_file=[explicit_env_file])
    assert settings.get_url() == SQLITE_URL


@pytest.mark.integration
def test_database_settings_no_context_raises_without_prefix() -> None:
    """DatabaseSettings() raises RuntimeError when no context is installed and no prefix is given."""
    reset_context()
    with pytest.raises(RuntimeError, match="get_context\\(\\) called before set_context"):
        DatabaseSettings()
