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
import urllib.parse
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from aignostics_foundry_core.settings import OpaqueSettings


class DatabaseSettings(OpaqueSettings):
    """Database connection settings whose env prefix is derived from the active FoundryContext.

    The effective prefix defaults to ``{FoundryContext.env_prefix}DB_``, resolved at
    instantiation time via :func:`aignostics_foundry_core.foundry.get_context`.  Pass
    ``_env_prefix`` explicitly to bypass the context lookup (required inside
    :meth:`FoundryContext.from_package` to avoid circular imports).

    Environment variables (with default prefix ``{NAME}_DB_``):

    * ``{PREFIX}URL`` — required; the full database connection URL
    * ``{PREFIX}POOL_SIZE`` — optional; connection pool size (default ``10``)
    * ``{PREFIX}MAX_OVERFLOW`` — optional; maximum pool overflow (default ``10``)
    * ``{PREFIX}POOL_TIMEOUT`` — optional; pool checkout timeout in seconds (default ``30.0``)
    * ``{PREFIX}NAME`` — optional; override the database name in the URL path component
    """

    model_config = SettingsConfigDict(extra="ignore")

    url: SecretStr
    pool_size: int = 10
    max_overflow: int = 10
    pool_timeout: float = 30.0
    db_name: str | None = None

    def __init__(self, _env_prefix: str | None = None, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialise settings, deriving env prefix from the active FoundryContext when not given.

        Args:
            _env_prefix: Optional explicit environment variable prefix (e.g. ``"MYAPP_DB_"``).
                When ``None``, the prefix is derived from the active FoundryContext as
                ``f"{get_context().env_prefix}DB_"``.
            **kwargs: Forwarded to :class:`~pydantic_settings.BaseSettings`.
        """
        if _env_prefix is None:
            from aignostics_foundry_core.foundry import get_context  # noqa: PLC0415

            _env_prefix = f"{get_context().env_prefix}DB_"
        super().__init__(_env_prefix=_env_prefix, **kwargs)  # pyright: ignore[reportCallIssue]

    def get_url(self) -> str:
        """Return the database URL string, optionally substituting the database name.

        When :attr:`db_name` is set, the path component of the URL is replaced with
        ``/{db_name}``, leaving the scheme, host, port, query, and fragment unchanged.

        Returns:
            The database URL as a plain string.
        """
        raw = self.url.get_secret_value()
        if self.db_name is None:
            return raw
        parsed = urllib.parse.urlparse(raw)
        return urllib.parse.urlunparse(parsed._replace(path=f"/{self.db_name}"))


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


_DEFAULT_POOL_SIZE = 10
_DEFAULT_MAX_OVERFLOW = 10
_DEFAULT_POOL_TIMEOUT = 30.0


def _resolve_db_params(
    db_url: str | None,
    pool_size: int | None,
    max_overflow: int | None,
    pool_timeout: float | None,
) -> tuple[str, int, int, float]:
    """Resolve database connection parameters, falling back to the active context.

    When ``db_url`` is ``None``, all four values are sourced from
    ``get_context().database``.  When ``db_url`` is provided, any ``None`` pool
    params are replaced by their module-level defaults.

    Returns:
        A tuple of ``(db_url, pool_size, max_overflow, pool_timeout)``.

    Raises:
        RuntimeError: If ``db_url`` is ``None`` and no context is installed, or
            the context has no ``database`` configured.
    """
    if db_url is None:
        from aignostics_foundry_core.foundry import get_context  # noqa: PLC0415

        ctx = get_context()
        if ctx.database is None:
            msg = f"No database URL configured. Set {ctx.env_prefix}DB_URL or pass db_url explicitly."
            raise RuntimeError(msg)
        return (
            ctx.database.get_url(),
            pool_size if pool_size is not None else ctx.database.pool_size,
            max_overflow if max_overflow is not None else ctx.database.max_overflow,
            pool_timeout if pool_timeout is not None else ctx.database.pool_timeout,
        )
    return (
        db_url,
        pool_size if pool_size is not None else _DEFAULT_POOL_SIZE,
        max_overflow if max_overflow is not None else _DEFAULT_MAX_OVERFLOW,
        pool_timeout if pool_timeout is not None else _DEFAULT_POOL_TIMEOUT,
    )


def init_engine(
    db_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
) -> None:
    """Initialize the database engine singleton.

    Creates a global connection pool that is reused across all operations in the process.
    Called during FastAPI lifespan startup or first job execution.
    Subsequent calls are no-ops (engine is already initialized).

    For multiprocessing: Engine is automatically reset in child processes via
    multiprocessing.util.register_after_fork().

    When ``db_url`` is ``None``, the URL and pool settings are resolved from the
    active :class:`~aignostics_foundry_core.foundry.FoundryContext`.  A
    :exc:`RuntimeError` is raised if no context is installed or the context has no
    ``database`` configured.

    Args:
        db_url: Database connection URL (e.g. ``postgresql+asyncpg://user:pass@host/db``).
            When ``None``, resolved from the active context's ``database`` settings.
        pool_size: Number of connections to keep in the pool. Ignored for dialects that
            do not support QueuePool (e.g. SQLite).  Defaults to the context value or 10.
        max_overflow: Number of additional connections above pool_size. Ignored for
            dialects that do not support QueuePool.  Defaults to the context value or 10.
        pool_timeout: Seconds to wait for a connection from the pool. Ignored for
            dialects that do not support QueuePool.  Defaults to the context value or 30.

    Raises:
        RuntimeError: If ``db_url`` is ``None`` and no context is installed, or the
            context has no ``database`` configured.
    """
    global _engine, _async_session_maker  # noqa: PLW0603

    if _engine is not None:
        logger.trace("Database engine already initialized, reusing existing engine and connection pool.")
        return  # Already initialized

    db_url, pool_size, max_overflow, pool_timeout = _resolve_db_params(db_url, pool_size, max_overflow, pool_timeout)

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
    db_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Run an async database function from a synchronous CLI context.

    This helper is specifically for CLI commands. It initializes the DB connection using
    the provided URL, runs the async function with a session, and cleans up after completion.

    NOT for use in long-lived processes (API, workers) - use @with_engine decorator instead.

    When ``db_url`` is ``None``, the URL and pool settings are resolved from the active
    :class:`~aignostics_foundry_core.foundry.FoundryContext` (same behaviour as
    :func:`init_engine`).

    Args:
        async_func: The async function to run (receives ``session`` as a keyword argument).
        *args: Positional arguments forwarded to ``async_func``.
        db_url: Database connection URL.  When ``None``, resolved from the active context.
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
    db_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Run an async function with initialized database engine from a synchronous CLI context.

    This helper is specifically for CLI commands. It initializes the DB engine using
    the provided URL, runs the async function, and cleans up after completion.

    NOT for use in long-lived processes (API, workers) - use @with_engine decorator instead.

    When ``db_url`` is ``None``, the URL and pool settings are resolved from the active
    :class:`~aignostics_foundry_core.foundry.FoundryContext` (same behaviour as
    :func:`init_engine`).

    Args:
        async_func: The async function to run (does not require a session parameter).
        *args: Positional arguments forwarded to ``async_func``.
        db_url: Database connection URL.  When ``None``, resolved from the active context.
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
    func: Any | None = None,  # noqa: ANN401
    *,
    db_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
) -> Any:  # noqa: ANN401
    """Decorator (or decorator factory) to ensure database engine is initialized for async functions.

    Supports two calling conventions:

    * ``@with_engine`` — no-parens form; resolves URL and pool settings from the
      active :class:`~aignostics_foundry_core.foundry.FoundryContext`.
    * ``@with_engine()`` or ``@with_engine(db_url=..., ...)`` — explicit-parens form;
      any omitted params are resolved from the active context.

    The connection pool persists across all jobs in the process for efficiency.
    Useful for background jobs and workers.

    For multiprocessing: Engine is automatically reset in child processes via
    multiprocessing.util.register_after_fork().

    Args:
        func: The async function to decorate (only when used as ``@with_engine``
            without parentheses).  Do not pass explicitly.
        db_url: Database connection URL.  When ``None``, resolved from the active context.
        pool_size: Connection pool size (ignored for SQLite).
        max_overflow: Max overflow connections (ignored for SQLite).
        pool_timeout: Pool wait timeout in seconds (ignored for SQLite).

    Returns:
        The decorated async function (no-parens form) or a decorator (parens form).

    Example::

        # Context-aware — no arguments needed once set_context() is called:
        @with_engine
        async def my_job():
            result = await execute_with_session(some_db_operation)
            return result


        # Explicit URL (e.g. secondary database):
        @with_engine(db_url="postgresql+asyncpg://user:pass@host/db")
        async def my_other_job(): ...
    """

    def decorator(f: Any) -> Any:  # noqa: ANN401
        func_name = getattr(f, "__name__", str(f))
        logger.trace("Applying with_engine decorator to function {}", func_name)

        @functools.wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            logger.trace("Initializing database engine in with_engine wrapper for function {}", func_name)
            init_engine(db_url=db_url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=pool_timeout)
            logger.debug("Database engine initialized in with_engine wrapper for function {}", func_name)

            try:
                logger.trace("Executing function {} within with_engine wrapper", func_name)
                result = await f(*args, **kwargs)
                logger.trace("Successfully executed function {} within with_engine wrapper", func_name)
                return result
            except Exception:
                logger.exception("Exception occurred while executing function {} within with_engine wrapper", func_name)
                raise

        return wrapper

    if func is not None:  # called as @with_engine (no parens)
        return decorator(func)
    return decorator  # called as @with_engine() or @with_engine(db_url=...)
