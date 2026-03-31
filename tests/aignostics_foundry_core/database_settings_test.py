"""Tests for DatabaseSettings."""

from collections.abc import Generator

import pytest

from aignostics_foundry_core.database import DatabaseSettings
from aignostics_foundry_core.foundry import reset_context, set_context
from tests.conftest import make_context

# Constants (SonarQube S1192)
POSTGRES_URL = "postgresql+asyncpg://user:pass@localhost:5432/postgres"
SQLITE_URL = "sqlite+aiosqlite:///test.db"
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


@pytest.fixture(autouse=True)
def _reset_context() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Reset global context before and after every test."""
    reset_context()
    yield
    reset_context()


# ---------------------------------------------------------------------------
# get_url behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_url_returns_plain_url_when_db_name_not_set() -> None:
    """get_url() returns the raw secret value unchanged when database name is None."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL)
    assert settings.get_url() == POSTGRES_URL


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
    assert result.startswith("postgresql+asyncpg://")
    assert "localhost:5432" in result


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
    assert settings.get_url() == POSTGRES_URL


@pytest.mark.unit
def test_explicit_env_prefix_overrides_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing _env_prefix reads from that prefix regardless of the active context."""
    ctx = make_context(env_prefix="MYAPP_")
    set_context(ctx)
    monkeypatch.setenv("MYAPP_DB_URL", "postgresql+asyncpg://wrong/wrong")
    monkeypatch.setenv(CUSTOM_PREFIX_URL_ENV, POSTGRES_URL)

    settings = DatabaseSettings(_env_prefix=CUSTOM_PREFIX)
    assert settings.get_url() == POSTGRES_URL


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
def test_url_is_masked_in_repr() -> None:
    """repr(settings) / str(settings) does not expose the raw URL."""
    settings = DatabaseSettings(_env_prefix="TEST_DB_", url=POSTGRES_URL)
    representation = repr(settings)
    assert "pass" not in representation
    assert "**" in representation or "SecretStr" in representation
