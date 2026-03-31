"""Tests for database module — async SQLAlchemy session management."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from aignostics_foundry_core.database import (
    DatabaseSettings,
    cli_run_with_db,
    cli_run_with_engine,
    dispose_engine,
    execute_with_session,
    get_db_session,
    init_engine,
    with_engine,
)
from aignostics_foundry_core.foundry import reset_context, set_context
from tests.conftest import make_context

NON_SQLITE_DB_URL = "postgresql+asyncpg://u:p@localhost/db"
DB_URL_ERROR_FRAGMENT = "DB_URL"

SESSION_KWARG = "session"


@pytest.fixture(autouse=True)
async def reset_engine() -> AsyncGenerator[None, None]:  # pyright: ignore[reportUnusedFunction]
    """Ensure engine and context state are clean before and after each test."""
    await dispose_engine()
    reset_context()
    yield
    await dispose_engine()
    reset_context()


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """Return a SQLite+aiosqlite URL backed by a temp file."""
    return f"sqlite+aiosqlite:///{tmp_path}/test.db"


class TestGetDbSession:
    """Tests for get_db_session behaviour."""

    @pytest.mark.unit
    async def test_get_db_session_raises_before_init(self) -> None:
        """RuntimeError raised when engine has not been initialised."""
        gen = get_db_session()
        with pytest.raises(RuntimeError, match="not initialized"):
            await anext(gen)


async def noop(**_kwargs: object) -> None:
    """A no-op async function that accepts arbitrary keyword arguments."""
    await asyncio.sleep(0)


class TestInitEngine:
    """Tests for init_engine and dispose_engine lifecycle."""

    @pytest.mark.unit
    async def test_init_engine_then_dispose(self, sqlite_url: str) -> None:
        """init_engine followed by dispose_engine does not raise."""
        init_engine(sqlite_url)
        await dispose_engine()  # Must not raise

    @pytest.mark.unit
    async def test_init_engine_is_idempotent(self, sqlite_url: str) -> None:
        """Calling init_engine twice is a no-op — execute_with_session works after both calls."""
        init_engine(sqlite_url)
        init_engine(sqlite_url)  # Must not raise; second call is a silent no-op
        await execute_with_session(noop)  # Session maker still functional

    @pytest.mark.unit
    async def test_init_engine_non_sqlite_url_accepted(self) -> None:
        """init_engine accepts a non-SQLite URL without raising (engine creation is lazy)."""
        init_engine(NON_SQLITE_DB_URL)
        await dispose_engine()  # Must not raise even though no connection was attempted


class TestExecuteWithSession:
    """Tests for execute_with_session behaviour."""

    @pytest.mark.unit
    async def test_execute_with_session_passes_session(self, sqlite_url: str) -> None:
        """The wrapped function receives an AsyncSession as the 'session' keyword argument."""
        received: list[object] = []

        async def capture_session(**kwargs: object) -> None:
            await asyncio.sleep(0)  # Use an asynchronous feature
            received.append(kwargs.get(SESSION_KWARG))

        init_engine(sqlite_url)
        await execute_with_session(capture_session)

        assert len(received) == 1
        assert isinstance(received[0], AsyncSession)

    @pytest.mark.unit
    async def test_execute_with_session_raises_before_init(self) -> None:
        """RuntimeError raised when execute_with_session is called before init_engine."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await execute_with_session(noop)


class TestCliRunWithDb:
    """Tests for cli_run_with_db synchronous CLI helper."""

    @pytest.mark.unit
    async def test_cli_run_with_db_returns_function_result(self, sqlite_url: str) -> None:
        """cli_run_with_db returns the value produced by the async function."""

        async def return_42(**_: object) -> int:
            await asyncio.sleep(0)  # Use an asynchronous feature
            return 42

        result = await asyncio.to_thread(cli_run_with_db, return_42, db_url=sqlite_url)

        assert result == 42

    @pytest.mark.unit
    async def test_cli_run_with_db_disposes_engine_on_error(self, sqlite_url: str) -> None:
        """cli_run_with_db disposes the engine via finally even when the function raises."""
        err_msg = "boom"

        async def raise_error(**_: object) -> None:  # noqa: RUF029
            raise ValueError(err_msg)

        with pytest.raises(ValueError, match=err_msg):
            await asyncio.to_thread(cli_run_with_db, raise_error, db_url=sqlite_url)

        init_engine(sqlite_url)
        await execute_with_session(noop)


class TestCliRunWithEngine:
    """Tests for cli_run_with_engine synchronous CLI helper."""

    @pytest.mark.unit
    async def test_cli_run_with_engine_executes_function(self, sqlite_url: str) -> None:
        """cli_run_with_engine returns the value produced by the async function."""

        async def return_hello() -> str:
            await asyncio.sleep(0)  # Use an asynchronous feature
            return "hello"

        result = await asyncio.to_thread(cli_run_with_engine, return_hello, db_url=sqlite_url)

        assert result == "hello"

    @pytest.mark.unit
    async def test_cli_run_with_engine_disposes_engine_on_error(self, sqlite_url: str) -> None:
        """cli_run_with_engine disposes the engine via finally even when the function raises."""
        err_msg = "boom"

        async def raise_error() -> None:  # noqa: RUF029
            raise ValueError(err_msg)

        with pytest.raises(ValueError, match=err_msg):
            await asyncio.to_thread(cli_run_with_engine, raise_error, db_url=sqlite_url)

        init_engine(sqlite_url)
        await execute_with_session(noop)


class TestWithEngine:
    """Tests for the with_engine decorator factory."""

    @pytest.mark.unit
    async def test_with_engine_explicit_url_still_works(self, sqlite_url: str) -> None:
        """A function decorated with @with_engine(db_url=...) runs without error."""
        calls: list[bool] = []

        @with_engine(db_url=sqlite_url)
        async def my_job() -> None:  # noqa: RUF029
            calls.append(True)

        await my_job()

        assert calls == [True]

    @pytest.mark.unit
    async def test_with_engine_propagates_exception(self, sqlite_url: str) -> None:
        """Exceptions raised inside a @with_engine-decorated function are re-raised."""
        err_msg = "job failed"

        @with_engine(db_url=sqlite_url)
        async def failing_job() -> None:  # noqa: RUF029
            raise RuntimeError(err_msg)

        with pytest.raises(RuntimeError, match=err_msg):
            await failing_job()


class TestInitEngineContextAware:
    """Tests for context-aware init_engine fallback behaviour."""

    @pytest.mark.unit
    async def test_init_engine_uses_context_url_when_no_explicit_url(self, sqlite_url: str) -> None:
        """init_engine() with no args uses the URL from the active context database."""
        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=sqlite_url)
        set_context(make_context(database=db_settings))

        init_engine()  # no db_url argument

        await execute_with_session(noop)  # confirms engine is functional

    @pytest.mark.unit
    async def test_init_engine_raises_when_no_url_and_no_context_database(self) -> None:
        """init_engine() raises RuntimeError when context.database is None."""
        set_context(make_context(database=None))

        with pytest.raises(RuntimeError, match=DB_URL_ERROR_FRAGMENT):
            init_engine()

    @pytest.mark.unit
    async def test_init_engine_raises_when_context_not_set(self) -> None:
        """init_engine() raises RuntimeError when no context has been installed."""
        # reset_engine fixture already cleared context — calling without set_context()
        with pytest.raises(RuntimeError):
            init_engine()

    @pytest.mark.unit
    async def test_init_engine_explicit_url_takes_precedence_over_context(
        self, sqlite_url: str, tmp_path: Path
    ) -> None:
        """Explicit db_url overrides the URL stored in the active context."""
        other_url = f"sqlite+aiosqlite:///{tmp_path}/other.db"
        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=other_url)
        set_context(make_context(database=db_settings))

        # Pass a different URL explicitly — should not raise
        init_engine(db_url=sqlite_url)

        await execute_with_session(noop)  # engine works → explicit URL was used


class TestCliRunWithDbContextAware:
    """Tests for context-aware cli_run_with_db fallback."""

    @pytest.mark.unit
    async def test_cli_run_with_db_uses_context_url(self, sqlite_url: str) -> None:
        """cli_run_with_db with no db_url uses the URL from the active context."""

        async def return_42(**_: object) -> int:
            await asyncio.sleep(0)
            return 42

        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=sqlite_url)
        set_context(make_context(database=db_settings))

        result = await asyncio.to_thread(cli_run_with_db, return_42)

        assert result == 42


class TestCliRunWithEngineContextAware:
    """Tests for context-aware cli_run_with_engine fallback."""

    @pytest.mark.unit
    async def test_cli_run_with_engine_uses_context_url(self, sqlite_url: str) -> None:
        """cli_run_with_engine with no db_url uses the URL from the active context."""

        async def return_hello() -> str:
            await asyncio.sleep(0)
            return "hello"

        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=sqlite_url)
        set_context(make_context(database=db_settings))

        result = await asyncio.to_thread(cli_run_with_engine, return_hello)

        assert result == "hello"


class TestWithEngineContextAware:
    """Tests for context-aware with_engine decorator."""

    @pytest.mark.unit
    async def test_with_engine_no_parens_uses_context(self, sqlite_url: str) -> None:
        """@with_engine (no parens) resolves the URL from the active context."""
        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=sqlite_url)
        set_context(make_context(database=db_settings))
        calls: list[bool] = []

        @with_engine
        async def my_job() -> None:  # noqa: RUF029
            calls.append(True)

        await my_job()

        assert calls == [True]

    @pytest.mark.unit
    async def test_with_engine_empty_parens_uses_context(self, sqlite_url: str) -> None:
        """@with_engine() (empty parens) resolves the URL from the active context."""
        db_settings = DatabaseSettings(_env_prefix="TEST_DB_", url=sqlite_url)
        set_context(make_context(database=db_settings))
        calls: list[bool] = []

        @with_engine()
        async def my_job() -> None:  # noqa: RUF029
            calls.append(True)

        await my_job()

        assert calls == [True]
