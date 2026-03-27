"""Project context injection for Foundry components.

Provides :class:`FoundryContext` — a frozen Pydantic model that derives all
project-specific values (name, version, environment, env files, URLs, Sentry
mode flags) from package metadata and environment variables at call time.

Typical usage::

    from aignostics_foundry_core.foundry import FoundryContext, get_context, set_context

    set_context(FoundryContext.from_package("myproject"))

    # Anywhere in the library:
    ctx = get_context()  # raises RuntimeError if set_context() was not called

References:
    docs/decisions/0003-project-context-injection.md
"""

from __future__ import annotations

import os
import sys
from importlib import metadata
from pathlib import Path

from pydantic import BaseModel, Field


def _empty_path_list() -> list[Path]:
    return []


class SentryContext(BaseModel):
    """Sentry mode flags derived from the runtime environment.

    All flags default to ``False`` so that a plain ``SentryContext()`` is safe to
    use as a default value.
    """

    model_config = {"frozen": True}

    is_container: bool = False
    is_cli: bool = False
    is_test: bool = False
    is_library: bool = False


class FoundryContext(BaseModel):
    """Immutable project context carrying all project-specific values.

    Construct via :meth:`from_package` rather than directly so that all
    derivation logic is centralised.

    References:
        docs/decisions/0003-project-context-injection.md
    """

    model_config = {"frozen": True}

    name: str
    version: str
    version_full: str
    environment: str
    env_file: list[Path] = Field(default_factory=_empty_path_list)
    repository_url: str = ""
    documentation_url: str = ""
    sentry: SentryContext = Field(default_factory=SentryContext)

    @classmethod
    def from_package(cls, package_name: str) -> FoundryContext:
        """Create a :class:`FoundryContext` by inspecting package metadata and the environment.

        Ports the full derivation logic previously duplicated in each project's
        ``_constants.py``.  The following environment variables are read:

        * ``VCS_REF``, ``COMMIT_SHA``, ``BUILDER``, ``BUILD_DATE``,
          ``CI_RUN_ID``, ``CI_RUN_NUMBER`` — build metadata for :attr:`version_full`.
        * ``{NAME}_ENVIRONMENT``, ``ENV``, ``VERCEL_ENV``, ``RAILWAY_ENVIRONMENT``
          — deployment environment.
        * ``{NAME}_ENV_FILE`` — optional extra env-file path inserted at index 2 of
          :attr:`env_file`.
        * ``{NAME}_RUNNING_IN_CONTAINER`` — sets :attr:`SentryContext.is_container`.
        * ``PYTEST_RUNNING_{NAME}`` — controls :attr:`SentryContext.is_test` /
          :attr:`SentryContext.is_library`.

        Args:
            package_name: The importable package name (e.g. ``"bridge"``).

        Returns:
            A populated, frozen :class:`FoundryContext`.
        """
        name = package_name
        name_upper = name.upper()
        version = metadata.version(package_name)
        environment = _detect_environment(name_upper)
        repository_url, documentation_url = _extract_urls(package_name)

        return cls(
            name=name,
            version=version,
            version_full=_build_version_full(version),
            environment=environment,
            env_file=_build_env_file_list(name, name_upper, environment),
            repository_url=repository_url,
            documentation_url=documentation_url,
            sentry=_build_sentry_context(name, name_upper),
        )


def _build_version_full(version: str) -> str:
    """Append build metadata to *version* from environment variables.

    Returns:
        The version string with optional ``+<metadata>`` suffix.
    """
    vcs_ref = os.getenv("VCS_REF", "unknown")
    commit_sha = os.getenv("COMMIT_SHA", "unknown")
    builder = os.getenv("BUILDER", "uv")
    build_date = os.getenv("BUILD_DATE", "unknown")
    ci_run_id = os.getenv("CI_RUN_ID", "unknown")
    ci_run_number = os.getenv("CI_RUN_NUMBER", "unknown")

    all_values = [vcs_ref, commit_sha, builder, build_date, ci_run_number, ci_run_id]
    if not any(val != "unknown" for val in all_values):
        return version

    vcs_parts = [p for p in [vcs_ref, commit_sha] if p != "unknown"]
    extra_parts: list[str] = []
    if ci_run_id != "unknown":
        extra_parts.append(f"run.{ci_run_id}")
    if ci_run_number != "unknown":
        extra_parts.append(f"build.{ci_run_number}")
    if builder != "unknown":
        extra_parts.append(f"builder.{builder}")
    if build_date != "unknown":
        extra_parts.append(f"built.{build_date}")

    result = version + "+" + "-".join(vcs_parts)
    if extra_parts:
        result += "---" + "---".join(extra_parts)
    return result


def _detect_environment(name_upper: str) -> str:
    """Return the deployment environment from environment variables."""
    for env_var in [f"{name_upper}_ENVIRONMENT", "ENV", "VERCEL_ENV", "RAILWAY_ENVIRONMENT"]:
        value = os.getenv(env_var)
        if value:
            return value
    return "local"


def _build_env_file_list(name: str, name_upper: str, environment: str) -> list[Path]:
    """Build the ordered list of env files for *name* in *environment*.

    Returns:
        Ordered list of candidate env-file paths.
    """
    paths: list[Path] = [
        Path.home() / f".{name}" / ".env",
        Path.home() / f".{name}" / f".env.{environment}",
        Path(".env"),
        Path(f".env.{environment}"),
    ]
    extra = os.getenv(f"{name_upper}_ENV_FILE")
    if extra:
        paths.insert(2, Path(extra))
    return paths


def _extract_urls(package_name: str) -> tuple[str, str]:
    """Return ``(repository_url, documentation_url)`` from package metadata."""
    pkg_metadata = metadata.metadata(package_name)
    repository_url = ""
    documentation_url = ""
    for url_entry in pkg_metadata.get_all("Project-URL") or []:
        if url_entry.startswith("Source"):
            repository_url = url_entry.split(", ", 1)[1]
        elif url_entry.startswith("Documentation"):
            documentation_url = url_entry.split(", ", 1)[1]
    return repository_url, documentation_url


def _build_sentry_context(name: str, name_upper: str) -> SentryContext:
    """Build :class:`SentryContext` flags from environment and process state.

    Returns:
        A populated, frozen :class:`SentryContext`.
    """
    is_container = bool(os.getenv(f"{name_upper}_RUNNING_IN_CONTAINER"))
    is_cli = sys.argv[0].endswith(name) or (len(sys.argv) > 1 and sys.argv[1] == name)
    pytest_running = bool(os.getenv(f"PYTEST_RUNNING_{name_upper}"))
    return SentryContext(
        is_container=is_container,
        is_cli=is_cli,
        is_test="pytest" in sys.modules and pytest_running,
        is_library=not is_cli and not pytest_running,
    )


# Module-level context singleton — set via set_context(), read via get_context().
_context: FoundryContext | None = None


def set_context(ctx: FoundryContext) -> None:
    """Install *ctx* as the global project context.

    Subsequent calls to :func:`get_context` will return *ctx*.  Calling this a
    second time replaces the previously installed context.

    Args:
        ctx: The :class:`FoundryContext` to install.

    References:
        docs/decisions/0003-project-context-injection.md
    """
    global _context  # noqa: PLW0603
    _context = ctx


def get_context() -> FoundryContext:
    """Return the global project context.

    Returns:
        The configured :class:`FoundryContext`.

    Raises:
        RuntimeError: If :func:`set_context` has not been called yet.

    References:
        docs/decisions/0003-project-context-injection.md
    """
    if _context is None:
        msg = (
            "get_context() called before set_context() was called. "
            "Call set_context(FoundryContext.from_package(...)) at application startup."
        )
        raise RuntimeError(msg)
    return _context
