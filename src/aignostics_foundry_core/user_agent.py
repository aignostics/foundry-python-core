"""Dynamic user agent string generation."""

import os
import platform


def user_agent(project_name: str, version: str, repository_url: str) -> str:
    """Generate a user agent string for HTTP requests.

    Format: {project_name}-python-sdk/{version} ({platform}; +{repository_url}; {optional_parts})

    Args:
        project_name: The name of the project (e.g. "bridge").
        version: The version string (e.g. "1.2.3").
        repository_url: The URL of the project repository.

    Returns:
        str: The user agent string.
    """
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

    # Format: {project}-python-sdk/{version} ({platform}; +{repository_url}; {optional_parts})
    base_info = f"{project_name}-python-sdk/{version}"
    system_info = f"{platform.platform()}; +{repository_url}{optional_suffix}"

    return f"{base_info} ({system_info})"
