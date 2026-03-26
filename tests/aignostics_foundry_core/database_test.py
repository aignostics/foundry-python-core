"""Tests for database module — async SQLAlchemy session management."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from aignostics_foundry_core.database import (
    dispose_engine,
    execute_with_session,
    get_db_session,
    init_engine,
    with_engine,
)

SESSION_KWARG = "session"


@pytest.fixture(autouse=True)
async def reset_engine() -> AsyncGenerator[None, None]:  # pyright: ignore[reportUnusedFunction]
    """Ensure engine state is clean before and after each test."""
    await dispose_engine()
    yield
    await dispose_engine()


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

        async def noop(**_kwargs: object) -> None:
            pass

        await execute_with_session(noop)  # Session maker still functional


class TestExecuteWithSession:
    """Tests for execute_with_session behaviour."""

    @pytest.mark.unit
    async def test_execute_with_session_passes_session(self, sqlite_url: str) -> None:
        """The wrapped function receives an AsyncSession as the 'session' keyword argument."""
        received: list[object] = []

        async def capture_session(**kwargs: object) -> None:  # noqa: RUF029
            received.append(kwargs.get(SESSION_KWARG))

        init_engine(sqlite_url)
        await execute_with_session(capture_session)

        assert len(received) == 1
        assert isinstance(received[0], AsyncSession)


class TestWithEngine:
    """Tests for the with_engine decorator factory."""

    @pytest.mark.unit
    async def test_with_engine_decorator_initialises_engine(self, sqlite_url: str) -> None:
        """A function decorated with @with_engine(db_url=...) runs without error."""
        calls: list[bool] = []

        @with_engine(db_url=sqlite_url)
        async def my_job() -> None:  # noqa: RUF029
            calls.append(True)

        await my_job()

        assert calls == [True]
