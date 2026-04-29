"""Shared fixtures for GUI tests."""

import os
from collections.abc import Generator

import pytest

from aignostics_foundry_core.gui import clear_page_registry
from tests.aignostics_foundry_core.api import INTERNAL_ORG_ID_VAR_NAME, ROLE_CLAIM_VAR_NAME

_INTERNAL_ORG = "org_internal"
_ROLE_CLAIM = "https://example.com/role"


@pytest.fixture(autouse=True)
def _clear_registry() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Ensure the page registry is clean before and after each test."""
    clear_page_registry()
    yield
    clear_page_registry()


@pytest.fixture(autouse=True)
def _gui_auth_context() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Set required AuthSettings environment variables for GUI auth tests."""
    os.environ[INTERNAL_ORG_ID_VAR_NAME] = _INTERNAL_ORG
    os.environ[ROLE_CLAIM_VAR_NAME] = _ROLE_CLAIM
    yield
    os.environ.pop(INTERNAL_ORG_ID_VAR_NAME, None)
    os.environ.pop(ROLE_CLAIM_VAR_NAME, None)
