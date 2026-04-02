"""Tests for user_agent module."""

import pytest

from aignostics_foundry_core.foundry import FoundryContext
from aignostics_foundry_core.user_agent import user_agent
from tests.conftest import make_context

CTX_NAME = "myproject"
CTX_VERSION = "1.2.3"
CTX_REPOSITORY_URL = "https://github.com/example/myproject"
CTX_VERSION_FULL = "1.2.3+main-abc1234"

GITHUB_REPOSITORY = "example/myproject"
GITHUB_RUN_ID = "987654321"


class TestUserAgent:
    """Tests for the user_agent() function."""

    @pytest.mark.unit
    def test_user_agent_contains_project_and_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return value starts with '{name}-python-sdk/{version_full}'."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        ctx = make_context(name=CTX_NAME, version=CTX_VERSION, repository_url=CTX_REPOSITORY_URL)
        result = user_agent(context=ctx)

        assert result.startswith(f"{CTX_NAME}-python-sdk/{CTX_VERSION}")

    @pytest.mark.unit
    def test_user_agent_contains_repository_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repository URL appears in the returned string."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        ctx = make_context(name=CTX_NAME, version=CTX_VERSION, repository_url=CTX_REPOSITORY_URL)
        result = user_agent(context=ctx)

        assert CTX_REPOSITORY_URL in result

    @pytest.mark.unit
    def test_user_agent_uses_version_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When version_full differs from version, the result contains version_full not the base version."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        ctx = FoundryContext(
            name=CTX_NAME,
            version=CTX_VERSION,
            version_full=CTX_VERSION_FULL,
            version_with_vcs_ref=CTX_VERSION,
            environment="test",
        )
        result = user_agent(context=ctx)

        assert CTX_VERSION_FULL in result
        assert f"{CTX_NAME}-python-sdk/{CTX_VERSION} " not in result

    @pytest.mark.unit
    def test_user_agent_includes_pytest_test_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PYTEST_CURRENT_TEST value appears in the string when env var is set."""
        test_name = "tests/mymodule/test_foo.py::test_bar (call)"
        monkeypatch.setenv("PYTEST_CURRENT_TEST", test_name)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        ctx = make_context(name=CTX_NAME, version=CTX_VERSION, repository_url=CTX_REPOSITORY_URL)
        result = user_agent(context=ctx)

        assert test_name in result

    @pytest.mark.unit
    def test_user_agent_includes_github_run_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A github.com/…/actions/runs/… URL appears when GITHUB_RUN_ID and GITHUB_REPOSITORY are set."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("GITHUB_RUN_ID", GITHUB_RUN_ID)
        monkeypatch.setenv("GITHUB_REPOSITORY", GITHUB_REPOSITORY)

        ctx = make_context(name=CTX_NAME, version=CTX_VERSION, repository_url=CTX_REPOSITORY_URL)
        result = user_agent(context=ctx)

        expected_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
        assert expected_url in result
