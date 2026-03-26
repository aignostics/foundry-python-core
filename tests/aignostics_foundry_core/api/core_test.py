"""Unit tests for aignostics_foundry_core.api.core."""

import pytest

TITLE_KEY = "title"
TEST_TITLE = "My API"


@pytest.mark.unit
def test_versioned_api_router_is_api_router_subclass() -> None:
    """VersionedAPIRouter instances are FastAPI APIRouter subclasses."""
    from fastapi import APIRouter

    from aignostics_foundry_core.api.core import VersionedAPIRouter

    router = VersionedAPIRouter("v1")
    assert isinstance(router, APIRouter)


@pytest.mark.unit
def test_versioned_api_router_tracks_instances() -> None:
    """A newly created VersionedAPIRouter appears in get_instances()."""
    from aignostics_foundry_core.api.core import VersionedAPIRouter

    before = {id(r) for r in VersionedAPIRouter.get_instances()}
    new_router = VersionedAPIRouter("v99-test")
    after = VersionedAPIRouter.get_instances()

    assert any(id(r) == id(new_router) for r in after if id(r) not in before)


@pytest.mark.unit
def test_api_tag_constants() -> None:
    """All API_TAG_* constants are non-empty strings."""
    from aignostics_foundry_core.api.core import (
        API_TAG_ADMIN,
        API_TAG_AUTHENTICATED,
        API_TAG_INTERNAL,
        API_TAG_INTERNAL_ADMIN,
        API_TAG_PUBLIC,
    )

    for tag in (API_TAG_PUBLIC, API_TAG_AUTHENTICATED, API_TAG_ADMIN, API_TAG_INTERNAL, API_TAG_INTERNAL_ADMIN):
        assert isinstance(tag, str)
        assert len(tag) > 0


@pytest.mark.unit
def test_build_api_metadata_returns_dict_with_title() -> None:
    """build_api_metadata returns a dict containing the title key."""
    from aignostics_foundry_core.api.core import build_api_metadata

    result = build_api_metadata(title=TEST_TITLE, description="Test API", repository_url="https://example.com")

    assert isinstance(result, dict)
    assert result[TITLE_KEY] == TEST_TITLE


@pytest.mark.unit
def test_init_api_returns_fastapi_instance() -> None:
    """init_api() with no arguments returns a FastAPI application."""
    from fastapi import FastAPI

    from aignostics_foundry_core.api.core import init_api

    app = init_api()

    assert isinstance(app, FastAPI)
