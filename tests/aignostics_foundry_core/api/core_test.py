"""Unit tests for aignostics_foundry_core.api.core."""

import pytest

TITLE_KEY = "title"
TEST_TITLE = "My API"
MODULE_TAG = "test-module"
CUSTOM_PREFIX = "/custom-prefix"
EXTRA_TAG = "extra-tag"
VERSION_STEP1 = "v-step1-test"
VERSION_GVI = "v-cov-test"
TEST_VERSION_STR = "1.2.3"
BASE_URL = "https://example.com"


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


@pytest.mark.unit
def test_create_public_router_default_prefix() -> None:
    """create_public_router uses /{module_tag} as the default prefix."""
    from aignostics_foundry_core.api.core import create_public_router

    router = create_public_router(MODULE_TAG, version=VERSION_STEP1)

    assert router.prefix == f"/{MODULE_TAG}"


@pytest.mark.unit
def test_create_public_router_custom_prefix() -> None:
    """create_public_router uses the explicit prefix when provided."""
    from aignostics_foundry_core.api.core import create_public_router

    router = create_public_router(MODULE_TAG, version=VERSION_STEP1, prefix=CUSTOM_PREFIX)

    assert router.prefix == CUSTOM_PREFIX


@pytest.mark.unit
def test_create_public_router_tags() -> None:
    """create_public_router includes module_tag and API_TAG_PUBLIC in tags."""
    from aignostics_foundry_core.api.core import API_TAG_PUBLIC, create_public_router

    router = create_public_router(MODULE_TAG, version=VERSION_STEP1)

    assert MODULE_TAG in router.tags
    assert API_TAG_PUBLIC in router.tags


@pytest.mark.unit
def test_create_public_router_extra_tags() -> None:
    """create_public_router appends extra_tags to the tag list."""
    from aignostics_foundry_core.api.core import create_public_router

    router = create_public_router(MODULE_TAG, version=VERSION_STEP1, extra_tags=[EXTRA_TAG])

    assert EXTRA_TAG in router.tags


@pytest.mark.unit
def test_create_authenticated_router_injects_auth_dependency() -> None:
    """create_authenticated_router adds Depends(require_authenticated) to dependencies."""
    from aignostics_foundry_core.api.auth import require_authenticated
    from aignostics_foundry_core.api.core import create_authenticated_router

    router = create_authenticated_router(MODULE_TAG, version=VERSION_STEP1)

    assert any(d.dependency is require_authenticated for d in router.dependencies)


@pytest.mark.unit
def test_create_admin_router_injects_auth_dependency() -> None:
    """create_admin_router adds Depends(require_admin) to dependencies."""
    from aignostics_foundry_core.api.auth import require_admin
    from aignostics_foundry_core.api.core import create_admin_router

    router = create_admin_router(MODULE_TAG, version=VERSION_STEP1)

    assert any(d.dependency is require_admin for d in router.dependencies)


@pytest.mark.unit
def test_create_internal_router_injects_auth_dependency() -> None:
    """create_internal_router adds Depends(require_internal) to dependencies."""
    from aignostics_foundry_core.api.auth import require_internal
    from aignostics_foundry_core.api.core import create_internal_router

    router = create_internal_router(MODULE_TAG, version=VERSION_STEP1)

    assert any(d.dependency is require_internal for d in router.dependencies)


@pytest.mark.unit
def test_create_internal_admin_router_injects_auth_dependency() -> None:
    """create_internal_admin_router adds Depends(require_internal_admin) to dependencies."""
    from aignostics_foundry_core.api.auth import require_internal_admin
    from aignostics_foundry_core.api.core import create_internal_admin_router

    router = create_internal_admin_router(MODULE_TAG, version=VERSION_STEP1)

    assert any(d.dependency is require_internal_admin for d in router.dependencies)


@pytest.mark.unit
def test_versioned_api_router_add_exception_handler_registration() -> None:
    """add_exception_handler_registration stores the (exc_class, handler) pair."""
    from typing import Any, cast

    from aignostics_foundry_core.api.core import VersionedAPIRouter

    def handler(request: object, exc: Exception) -> None:
        pass

    router = VersionedAPIRouter(VERSION_STEP1)
    cast("Any", router).add_exception_handler_registration(ValueError, handler)

    assert (ValueError, handler) in cast("Any", router).exception_handlers


@pytest.mark.unit
def test_build_api_metadata_includes_version_when_provided() -> None:
    """build_api_metadata adds a 'version' key when version is supplied."""
    from aignostics_foundry_core.api.core import build_api_metadata

    result = build_api_metadata(title=TEST_TITLE, version=TEST_VERSION_STR)

    assert result["version"] == TEST_VERSION_STR


@pytest.mark.unit
def test_build_versioned_api_tags_returns_tag_for_version() -> None:
    """build_versioned_api_tags returns a single-element list with the correct name."""
    from aignostics_foundry_core.api.core import build_versioned_api_tags

    tags = build_versioned_api_tags("v2", repository_url=BASE_URL)

    assert len(tags) == 1
    assert tags[0]["name"] == "v2"
    assert BASE_URL in tags[0]["externalDocs"]["url"]


@pytest.mark.unit
def test_build_root_api_tags_one_entry_per_version() -> None:
    """build_root_api_tags returns one tag dict per version with correct name and URL."""
    from aignostics_foundry_core.api.core import build_root_api_tags

    versions = ["v1", "v2"]
    tags = build_root_api_tags(BASE_URL, versions)

    assert len(tags) == len(versions)
    for tag, version in zip(tags, versions, strict=True):
        assert tag["name"] == version
        assert f"/api/{version}/docs" in tag["externalDocs"]["url"]


@pytest.mark.unit
def test_get_versioned_api_instances_returns_fastapi_per_version() -> None:
    """get_versioned_api_instances returns a FastAPI instance for each requested version."""
    from fastapi import FastAPI

    from aignostics_foundry_core.api.core import VersionedAPIRouter, get_versioned_api_instances

    VersionedAPIRouter(VERSION_GVI)
    result = get_versioned_api_instances("aignostics_foundry_core", [VERSION_GVI])

    assert VERSION_GVI in result
    assert isinstance(result[VERSION_GVI], FastAPI)


@pytest.mark.unit
def test_init_api_with_custom_exception_handler_registrations() -> None:
    """init_api registers custom exception handler pairs before the standard handlers."""
    from fastapi import FastAPI

    from aignostics_foundry_core.api.core import init_api

    def handler(request: object, exc: Exception) -> None:
        pass

    app = init_api(exception_handler_registrations=[(ValueError, handler)])

    assert isinstance(app, FastAPI)
    assert ValueError in app.exception_handlers
