"""Centralized database connection management.

This module manages database connections using SQLAlchemy async engine and sessions.
Following the pattern from https://blog.danielclayton.co.uk/posts/database-connections-with-fastapi/
adapted for SQLAlchemy/SQLModel.

The engine is initialized once per process and reused across all operations.
This is a shared utility used by all modules that need database access.

Multiprocessing: Uses multiprocessing.util.register_after_fork() to automatically
reset the engine in child processes, ensuring fresh connections.
"""

import functools
import multiprocessing.util
from collections.abc import AsyncGenerator, Callable
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Global engine and session maker - initialized once per process and kept open
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _reset_engine_after_fork() -> None:
    """Reset the database engine after fork/spawn.

    This is automatically called by multiprocessing in child processes.
    Registered via multiprocessing.util.register_after_fork() below.
    """
    global _engine, _async_session_maker  # noqa: PLW0603

    logger.trace("Resetting database engine after fork in child process")
    if _engine is not None:
        logger.trace("Resetting inherited database engine after fork")
        # Don't dispose() - connections are already invalid in child process
        _engine = None
    else:
        logger.trace("No database engine to reset after fork")

    if _async_session_maker is not None:
        logger.trace("Resetting inherited async session maker after fork")
        _async_session_maker = None
    else:
        logger.trace("No async session maker to reset after fork")


# Sentinel object for registering the fork hook (can't use None with weakref)
class _DatabaseModuleSentinel:
    """Sentinel object to register database cleanup on fork."""


_module_sentinel = _DatabaseModuleSentinel()

# Register the reset function to be called after fork/spawn in child processes
multiprocessing.util.register_after_fork(_module_sentinel, lambda _obj: _reset_engine_after_fork())


def init_engine(
    db_url: str,
    pool_size: int = 10,
    max_overflow: int = 10,
    pool_timeout: float = 30,
) -> None:
    """Initialize the database engine singleton.

    Creates a global connection pool that is reused across all operations in the process.
    Called during FastAPI lifespan startup or first job execution.
    Subsequent calls are no-ops (engine is already initialized).

    For multiprocessing: Engine is automatically reset in child processes via
    multiprocessing.util.register_after_fork().

    Args:
        db_url: Database connection URL (e.g. ``postgresql+asyncpg://user:pass@host/db``).
        pool_size: Number of connections to keep in the pool. Ignored for dialects that
            do not support QueuePool (e.g. SQLite).
        max_overflow: Number of additional connections above pool_size. Ignored for
            dialects that do not support QueuePool.
        pool_timeout: Seconds to wait for a connection from the pool. Ignored for
            dialects that do not support QueuePool.
    """
    global _engine, _async_session_maker  # noqa: PLW0603

    if _engine is not None:
        logger.trace("Database engine already initialized, reusing existing engine and connection pool.")
        return  # Already initialized

    logger.trace(
        "Initializing global database engine with pool_size={}, max_overflow={}, pool_timeout={}",
        pool_size,
        max_overflow,
        pool_timeout,
    )

    # Pool settings not supported for all dialects (e.g., SQLite does not use QueuePool)
    engine_kwargs: dict[str, Any] = {
        "url": db_url,
        "pool_pre_ping": True,
        "echo": False,
    }
    if not db_url.startswith("sqlite"):
        engine_kwargs["pool_size"] = pool_size
        engine_kwargs["max_overflow"] = max_overflow
        engine_kwargs["pool_timeout"] = pool_timeout

    _engine = create_async_engine(**engine_kwargs)

    logger.trace("Creating global async session maker")
    _async_session_maker = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.debug("Global database engine and session maker initialized.")


async def dispose_engine() -> None:
    """Dispose the database engine singleton.

    Should only be called during application shutdown (e.g., FastAPI lifespan shutdown).
    NOT to be called after individual jobs - the connection pool should persist.
    """
    global _engine, _async_session_maker  # noqa: PLW0603

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Get a database session for dependency injection.

    This is a FastAPI dependency that provides a database session to route handlers.
    The session is automatically committed and closed after the request.

    Yields:
        AsyncSession: Database session.

    Raises:
        RuntimeError: If the engine has not been initialized.
    """
    if _async_session_maker is None:
        msg = "Async session maker not initialized in get_db_session. Call init_engine() in lifespan context."
        logger.exception(msg)
        raise RuntimeError(msg)

    async with _async_session_maker() as session:
        logger.trace("Providing database session via get_db_session dependency")
        yield session


async def execute_with_session(async_func: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    """Execute an async function with a database session.

    This is a helper for executing async database functions outside of the FastAPI request context.
    Used by CLI commands and jobs.

    Args:
        async_func: The async function to execute.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the async function.

    Raises:
        RuntimeError: If the engine has not been initialized.
    """
    if _async_session_maker is None:
        msg = "Async session maker not initialized in execute_with_session. Call init_engine() in lifespan context."
        logger.exception(msg)
        raise RuntimeError(msg)

    async with _async_session_maker() as session:
        # Inject session as keyword argument
        kwargs["session"] = session
        func_name = getattr(async_func, "__name__", str(async_func))
        logger.trace("Executing function {func_name} with database session", func_name=func_name)
        return await async_func(*args, **kwargs)


def cli_run_with_db(
    async_func: Any,  # noqa: ANN401
    *args: Any,  # noqa: ANN401
    db_url: str,
    pool_size: int = 10,
    max_overflow: int = 10,
    pool_timeout: float = 30,
    **kwargs: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Run an async database function from a synchronous CLI context.

    This helper is specifically for CLI commands. It initializes the DB connection using
    the provided URL, runs the async function with a session, and cleans up after completion.

    NOT for use in long-lived processes (API, workers) - use @with_engine decorator instead.

    Args:
        async_func: The async function to run (receives ``session`` as a keyword argument).
        *args: Positional arguments forwarded to ``async_func``.
        db_url: Database connection URL.
        pool_size: Connection pool size (ignored for SQLite).
        max_overflow: Max overflow connections (ignored for SQLite).
        pool_timeout: Pool wait timeout in seconds (ignored for SQLite).
        **kwargs: Keyword arguments forwarded to ``async_func``.

    Returns:
        The result of the async function.
    """
    import asyncio  # noqa: PLC0415

    logger.trace("Initializing database engine for cli_run_with_db")
    init_engine(db_url=db_url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=pool_timeout)
    logger.debug("Database engine initialized for cli_run_with_db")

    try:
        func_name = getattr(async_func, "__name__", str(async_func))
        logger.trace("Running async function {func_name} with database session in CLI context", func_name=func_name)
        return asyncio.run(execute_with_session(async_func, *args, **kwargs))
    finally:
        logger.trace("Disposing database engine after cli_run_with_db")
        asyncio.run(dispose_engine())


def cli_run_with_engine(
    async_func: Any,  # noqa: ANN401
    *args: Any,  # noqa: ANN401
    db_url: str,
    pool_size: int = 10,
    max_overflow: int = 10,
    pool_timeout: float = 30,
    **kwargs: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Run an async function with initialized database engine from a synchronous CLI context.

    This helper is specifically for CLI commands. It initializes the DB engine using
    the provided URL, runs the async function, and cleans up after completion.

    NOT for use in long-lived processes (API, workers) - use @with_engine decorator instead.

    Args:
        async_func: The async function to run (does not require a session parameter).
        *args: Positional arguments forwarded to ``async_func``.
        db_url: Database connection URL.
        pool_size: Connection pool size (ignored for SQLite).
        max_overflow: Max overflow connections (ignored for SQLite).
        pool_timeout: Pool wait timeout in seconds (ignored for SQLite).
        **kwargs: Keyword arguments forwarded to ``async_func``.

    Returns:
        The result of the async function.
    """
    import asyncio  # noqa: PLC0415

    logger.trace("Initializing database engine for cli_run_with_engine")
    init_engine(db_url=db_url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=pool_timeout)
    logger.debug("Database engine initialized for cli_run_with_engine")

    try:
        logger.trace("Running async function {func} with initialized engine in CLI context", func=async_func)
        return asyncio.run(async_func(*args, **kwargs))
    finally:
        logger.trace("Disposing database engine after cli_run_with_engine")
        asyncio.run(dispose_engine())


def with_engine(
    db_url: str,
    pool_size: int = 10,
    max_overflow: int = 10,
    pool_timeout: float = 30,
) -> Callable[[Any], Any]:
    """Decorator factory to ensure database engine is initialized for async functions.

    This decorator wraps an async function to automatically initialize the database
    engine singleton before execution. The connection pool persists across all jobs
    in the process for efficiency. Useful for background jobs and workers.

    For multiprocessing: Engine is automatically reset in child processes via
    multiprocessing.util.register_after_fork().

    Args:
        db_url: Database connection URL.
        pool_size: Connection pool size (ignored for SQLite).
        max_overflow: Max overflow connections (ignored for SQLite).
        pool_timeout: Pool wait timeout in seconds (ignored for SQLite).

    Returns:
        A decorator that wraps an async function with engine initialization.

    Example:
        @with_engine(db_url="postgresql+asyncpg://user:pass@host/db")
        async def my_job():
            result = await execute_with_session(some_db_operation)
            return result
    """

    def decorator(func: Any) -> Any:  # noqa: ANN401
        func_name = getattr(func, "__name__", str(func))
        logger.trace("Applying with_engine decorator to function {}", func_name)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            logger.trace("Initializing database engine in with_engine wrapper for function {}", func_name)
            init_engine(db_url=db_url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=pool_timeout)
            logger.debug("Database engine initialized in with_engine wrapper for function {}", func_name)

            try:
                logger.trace("Executing function {} within with_engine wrapper", func_name)
                result = await func(*args, **kwargs)
                logger.trace("Successfully executed function {} within with_engine wrapper", func_name)
                return result
            except Exception:
                logger.exception("Exception occurred while executing function {} within with_engine wrapper", func_name)
                raise

        return wrapper

    return decorator
