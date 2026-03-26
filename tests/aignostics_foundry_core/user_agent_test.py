"""Tests for user_agent module."""

import pytest

from aignostics_foundry_core.user_agent import user_agent

PROJECT_NAME = "myproject"
VERSION = "1.2.3"
REPOSITORY_URL = "https://github.com/example/myproject"
GITHUB_REPOSITORY = "example/myproject"
GITHUB_RUN_ID = "987654321"


class TestUserAgent:
    """Tests for the user_agent() function."""

    @pytest.mark.unit
    def test_user_agent_contains_project_and_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return value starts with '{project_name}-python-sdk/{version}'."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        result = user_agent(PROJECT_NAME, VERSION, REPOSITORY_URL)

        assert result.startswith(f"{PROJECT_NAME}-python-sdk/{VERSION}")

    @pytest.mark.unit
    def test_user_agent_contains_repository_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repository URL appears in the returned string."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        result = user_agent(PROJECT_NAME, VERSION, REPOSITORY_URL)

        assert REPOSITORY_URL in result

    @pytest.mark.unit
    def test_user_agent_includes_pytest_test_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PYTEST_CURRENT_TEST value appears in the string when env var is set."""
        test_name = "tests/mymodule/test_foo.py::test_bar (call)"
        monkeypatch.setenv("PYTEST_CURRENT_TEST", test_name)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        result = user_agent(PROJECT_NAME, VERSION, REPOSITORY_URL)

        assert test_name in result

    @pytest.mark.unit
    def test_user_agent_includes_github_run_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A github.com/…/actions/runs/… URL appears when GITHUB_RUN_ID and GITHUB_REPOSITORY are set."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("GITHUB_RUN_ID", GITHUB_RUN_ID)
        monkeypatch.setenv("GITHUB_REPOSITORY", GITHUB_REPOSITORY)

        result = user_agent(PROJECT_NAME, VERSION, REPOSITORY_URL)

        expected_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
        assert expected_url in result
