"""Dynamic user agent string generation."""

import os
import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aignostics_foundry_core.foundry import FoundryContext
from aignostics_foundry_core.foundry import get_context


def user_agent(*, context: "FoundryContext | None" = None) -> str:
    """Generate a user agent string for HTTP requests.

    Format: {name}-python-sdk/{version_full} ({platform}; +{repository_url}; {optional_parts})

    Args:
        context: The :class:`~aignostics_foundry_core.foundry.FoundryContext` to use.
            When ``None``, falls back to the process-level context installed via
            :func:`~aignostics_foundry_core.foundry.set_context`.

    Returns:
        str: The user agent string.
    """
    ctx = context or get_context()

    current_test = os.getenv("PYTEST_CURRENT_TEST")  # Set if running under pytest
    github_run_id = os.getenv("GITHUB_RUN_ID")  # Set if running in GitHub Actions
    github_repository = os.getenv("GITHUB_REPOSITORY")  # Set if running in GitHub Actions

    optional_parts: list[str] = []

    if current_test:
        optional_parts.append(current_test)

    if github_run_id and github_repository:
        github_run_url = f"+https://github.com/{github_repository}/actions/runs/{github_run_id}"
        optional_parts.append(github_run_url)

    optional_suffix = "; " + "; ".join(optional_parts) if optional_parts else ""

    # Format: {project}-python-sdk/{version_full} ({platform}; +{repository_url}; {optional_parts})
    # TODO(oliverm): Find a way to not hard code python-sdk here. This was taken as such from Bridge.
    base_info = f"{ctx.name}-python-sdk/{ctx.version_full}"
    system_info = f"{platform.platform()}; +{ctx.repository_url}{optional_suffix}"

    return f"{base_info} ({system_info})"
