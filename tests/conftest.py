"""Common test fixtures and configuration."""

import logging
import os
from pathlib import Path

import psutil
import pytest

from aignostics_foundry_core.database import DatabaseSettings
from aignostics_foundry_core.foundry import FoundryContext

__all__ = ["make_context"]

logger = logging.getLogger(__name__)


TEST_PROJECT_NAME = "test_project"
TEST_PROJECT_PREFIX = "TEST_PROJECT_"


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Set the number of workers for xdist to a factor of the (logical) CPU cores.

    If the pytest option `--numprocesses` is set to "logical" or "auto", the number of workers is calculated
    based on the logical CPU count multiplied by the factor. If the option is set otherwise, that value is
    used directly.

    The factor (float) can be adjusted via the environment variable `XDIST_WORKER_FACTOR`, defaulting to 1.

    Args:
        config: The pytest configuration object.

    Returns:
        int: The number of workers set for xdist.
    """
    if config.getoption("numprocesses") in {"logical", "auto"}:
        logical_cpu_count = psutil.cpu_count(logical=config.getoption("numprocesses") == "logical") or 1
        factor = float(os.getenv("XDIST_WORKER_FACTOR", "1"))
        print(f"xdist_worker_factor: {factor}")
        num_workers = max(1, int(logical_cpu_count * factor))
        print(f"xdist_num_workers: {num_workers}")
        logger.info(
            "Set number of xdist workers to '%s' based on logical CPU count of %s.", num_workers, logical_cpu_count
        )
        return num_workers
    return config.getoption("numprocesses")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Run after the test session ends.

    Does change behavior if no test matching the marker is found:
    - Sets the exit status to 0 instead of 5.

    Args:
        session: The pytest session object.
        exitstatus: The exit status of the test session.
    """
    if exitstatus == 5:
        session.exitstatus = 0


def make_context(  # noqa: PLR0913
    name: str = TEST_PROJECT_NAME,
    *,
    env_prefix: str = TEST_PROJECT_PREFIX,
    version: str = "0.0.0",
    environment: str = "test",
    project_path: Path | None = None,
    repository_url: str = "",
    database: DatabaseSettings | None = None,
    env_file: list[Path] | None = None,
    **kwargs: bool,
) -> FoundryContext:
    """Create a minimal FoundryContext for testing.

    Args:
        name: The project name.
        env_prefix: The environment variable prefix (e.g. ``"MYPROJECT_"``).
        version: The version string (defaults to ``"0.0.0"``).
        environment: The deployment environment (defaults to ``"test"``).
        project_path: Optional path to the project root.
        repository_url: The project repository URL (defaults to ``""``).
        database: Optional :class:`~aignostics_foundry_core.database.DatabaseSettings`
            instance to attach to the context.
        env_file: Optional list of ``.env`` file paths to attach to the context.
        **kwargs: Optional boolean flags forwarded to :class:`FoundryContext`
            (``is_test``, ``is_cli``, ``is_container``, ``is_library``).
    """
    return FoundryContext(
        name=name,
        version=version,
        version_full=version,
        version_with_vcs_ref=version,
        environment=environment,
        env_prefix=env_prefix,
        project_path=project_path,
        repository_url=repository_url,
        database=database,
        env_file=env_file or [],
        **kwargs,  # type: ignore[arg-type]
    )
