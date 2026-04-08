"""Core API utilities for FastAPI.

This module provides:
- VersionedAPIRouter: Router with version tracking
- Router factory functions
- API initialization and metadata building
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from aignostics_foundry_core.di import load_modules
from aignostics_foundry_core.foundry import get_context

if TYPE_CHECKING:
    from aignostics_foundry_core.foundry import FoundryContext

from .exceptions import (
    AccessDeniedException,
    ApiException,
    NotFoundException,
    api_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

# Re-export exceptions for backward compatibility
__all__ = [
    "AccessDeniedException",
    "ApiException",
    "NotFoundException",
    "api_exception_handler",
    "unhandled_exception_handler",
    "validation_exception_handler",
]

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

API_TAG_AUTHENTICATED = "authenticated"
API_TAG_PUBLIC = "public"
API_TAG_ADMIN = "admin"
API_TAG_INTERNAL = "internal"
API_TAG_INTERNAL_ADMIN = "internal_admin"


class VersionedAPIRouter:
    """APIRouter with version attribute.

    Use this class to create versioned routers for a FastAPI application
    that are automatically registered into the FastAPI app via
    ``get_versioned_api_instances``.

    The version attribute identifies which API version the router belongs to.
    """

    # Class variable to track all created instances
    _instances: ClassVar[list[VersionedAPIRouter]] = []

    @classmethod
    def get_instances(cls) -> list[VersionedAPIRouter]:
        """Get all created router instances.

        Returns:
            A copy of the list of all router instances created so far.
        """
        return cls._instances.copy()

    def __new__(cls, version: str, *args: Any, **kwargs: Any) -> Self:  # noqa: ANN401
        """Create a new instance with lazy-loaded dependencies.

        Args:
            version: The API version this router belongs to.
            *args: Arguments forwarded to the FastAPI APIRouter.
            **kwargs: Keyword arguments forwarded to the FastAPI APIRouter.

        Returns:
            An instance of VersionedAPIRouter backed by a FastAPI APIRouter.
        """
        from fastapi import APIRouter  # noqa: PLC0415

        class VersionedAPIRouterImpl(APIRouter):
            """Implementation of VersionedAPIRouter with lazy-loaded dependencies."""

            version: str
            exception_handlers: list[tuple[type[Exception], Any]]

            def __init__(self, version: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
                """Initialise the router.

                Args:
                    version: The API version this router belongs to.
                    *args: Arguments forwarded to the FastAPI APIRouter.
                    **kwargs: Keyword arguments forwarded to the FastAPI APIRouter.
                """
                super().__init__(*args, **kwargs)
                self.version = version
                self.exception_handlers = []

            def add_exception_handler_registration(
                self,
                exc_class: type[Exception],
                handler: Any,  # noqa: ANN401
            ) -> None:
                """Register an exception handler to be added to the FastAPI app.

                Args:
                    exc_class: The exception class to handle.
                    handler: The handler function.
                """
                self.exception_handlers.append((exc_class, handler))

        instance = VersionedAPIRouterImpl(version, *args, **kwargs)
        cls._instances.append(instance)  # type: ignore[arg-type]
        return instance  # type: ignore[return-value]


def create_public_router(
    module_tag: str,
    *,
    version: str = "v1",
    prefix: str | None = None,
    extra_tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Create a public API router (no authentication required).

    Args:
        module_tag: The module tag used for prefix and tags (e.g., "hello-world").
        version: API version (default: "v1").
        prefix: URL prefix (default: "/{module_tag}").
        extra_tags: Additional tags to add to the router.
        extra_dependencies: Additional dependencies to add to the router.

    Returns:
        A configured APIRouter instance.
    """
    actual_prefix = prefix if prefix is not None else f"/{module_tag}"
    tags = [module_tag, API_TAG_PUBLIC] + (extra_tags or [])
    dependencies = extra_dependencies or []
    return cast("APIRouter", VersionedAPIRouter(version, prefix=actual_prefix, tags=tags, dependencies=dependencies))


def create_authenticated_router(
    module_tag: str,
    *,
    version: str = "v1",
    prefix: str | None = None,
    extra_tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Create an authenticated API router (requires valid Auth0 session).

    Args:
        module_tag: The module tag used for prefix and tags (e.g., "hello-world").
        version: API version (default: "v1").
        prefix: URL prefix (default: "/{module_tag}").
        extra_tags: Additional tags to add to the router.
        extra_dependencies: Additional dependencies to add to the router.

    Returns:
        A configured APIRouter instance.
    """
    from fastapi import Depends  # noqa: PLC0415

    from .auth import require_authenticated  # noqa: PLC0415

    actual_prefix = prefix if prefix is not None else f"/{module_tag}"
    tags = [module_tag, API_TAG_AUTHENTICATED] + (extra_tags or [])
    dependencies = [Depends(require_authenticated)] + (extra_dependencies or [])
    return cast("APIRouter", VersionedAPIRouter(version, prefix=actual_prefix, tags=tags, dependencies=dependencies))


def create_admin_router(
    module_tag: str,
    *,
    version: str = "v1",
    prefix: str | None = None,
    extra_tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Create an admin API router (requires admin role).

    Args:
        module_tag: The module tag used for prefix and tags (e.g., "hello-world").
        version: API version (default: "v1").
        prefix: URL prefix (default: "/{module_tag}").
        extra_tags: Additional tags to add to the router.
        extra_dependencies: Additional dependencies to add to the router.

    Returns:
        A configured APIRouter instance.
    """
    from fastapi import Depends  # noqa: PLC0415

    from .auth import require_admin  # noqa: PLC0415

    actual_prefix = prefix if prefix is not None else f"/{module_tag}"
    tags = [module_tag, API_TAG_ADMIN] + (extra_tags or [])
    dependencies = [Depends(require_admin)] + (extra_dependencies or [])
    return cast("APIRouter", VersionedAPIRouter(version, prefix=actual_prefix, tags=tags, dependencies=dependencies))


def create_internal_router(
    module_tag: str,
    *,
    version: str = "v1",
    prefix: str | None = None,
    extra_tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Create an internal API router (requires internal org membership).

    Args:
        module_tag: The module tag used for prefix and tags (e.g., "hello-world").
        version: API version (default: "v1").
        prefix: URL prefix (default: "/{module_tag}").
        extra_tags: Additional tags to add to the router.
        extra_dependencies: Additional dependencies to add to the router.

    Returns:
        A configured APIRouter instance.
    """
    from fastapi import Depends  # noqa: PLC0415

    from .auth import require_internal  # noqa: PLC0415

    actual_prefix = prefix if prefix is not None else f"/{module_tag}"
    tags = [module_tag, API_TAG_INTERNAL] + (extra_tags or [])
    dependencies = [Depends(require_internal)] + (extra_dependencies or [])
    return cast("APIRouter", VersionedAPIRouter(version, prefix=actual_prefix, tags=tags, dependencies=dependencies))


def create_internal_admin_router(
    module_tag: str,
    *,
    version: str = "v1",
    prefix: str | None = None,
    extra_tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Create an internal admin API router (requires internal org + admin role).

    Args:
        module_tag: The module tag used for prefix and tags (e.g., "hello-world").
        version: API version (default: "v1").
        prefix: URL prefix (default: "/{module_tag}").
        extra_tags: Additional tags to add to the router.
        extra_dependencies: Additional dependencies to add to the router.

    Returns:
        A configured APIRouter instance.
    """
    from fastapi import Depends  # noqa: PLC0415

    from .auth import require_internal_admin  # noqa: PLC0415

    actual_prefix = prefix if prefix is not None else f"/{module_tag}"
    tags = [module_tag, API_TAG_INTERNAL_ADMIN] + (extra_tags or [])
    dependencies = [Depends(require_internal_admin)] + (extra_dependencies or [])
    return cast("APIRouter", VersionedAPIRouter(version, prefix=actual_prefix, tags=tags, dependencies=dependencies))


def build_api_metadata(version: str | None = None, *, context: FoundryContext | None = None) -> dict[str, Any]:
    """Build a metadata dictionary suitable for passing to a FastAPI instance.

    All fields (title, description, author, URLs) are derived from *context*.

    Args:
        version: Optional API version string.
        context: Project context supplying the title, description, author, and URLs.
            When ``None``, the global context installed via
            :func:`aignostics_foundry_core.foundry.set_context` is used.

    Returns:
        Dictionary containing FastAPI metadata keys.
    """
    ctx = context or get_context()
    metadata: dict[str, Any] = {
        "title": ctx.name,
        "description": ctx.metadata.description,
        "contact": {
            "name": ctx.metadata.author_name or "Unknown",
            "email": ctx.metadata.author_email or "",
            "url": ctx.metadata.repository_url,
        },
        "terms_of_service": ctx.metadata.documentation_url,
        "license_info": {
            "name": "Aignostics Commercial License",
            "url": f"{ctx.metadata.repository_url}/blob/main/LICENSE",
        },
    }
    if version is not None:
        metadata["version"] = version
    return metadata


def build_versioned_api_tags(version_name: str, *, context: FoundryContext | None = None) -> list[dict[str, Any]]:
    """Build ``openapi_tags`` for a versioned API instance.

    Args:
        version_name: The version name (e.g., "v1").
        context: Project context supplying the repository URL for the external docs link.
            When ``None``, the global context installed via
            :func:`aignostics_foundry_core.foundry.set_context` is used.

    Returns:
        List of OpenAPI tag dictionaries for the versioned API.
    """
    repository_url = (context or get_context()).metadata.repository_url
    return [
        {
            "name": version_name,
            "description": f"API version {version_name.lstrip('v')}",
            "externalDocs": {
                "description": "Reference Documentation",
                "url": f"{repository_url}/blob/main/API_REFERENCE_{version_name}.md",
            },
        }
    ]


def build_root_api_tags(base_url: str, versions: list[str]) -> list[dict[str, Any]]:
    """Build ``openapi_tags`` for the root API instance.

    Args:
        base_url: The base URL of the API service.
        versions: List of API version names (e.g., ``["v1", "v2"]``).

    Returns:
        List of OpenAPI tag dictionaries linking each version's documentation.
    """
    return [
        {
            "name": version,
            "description": f"For API version {version.lstrip('v')}, click link on the right",
            "externalDocs": {
                "description": f"{version} API Documentation",
                "url": f"{base_url.rstrip('/')}/api/{version}/docs",
            },
        }
        for version in versions
    ]


def get_versioned_api_instances(
    versions: list[str],
    *,
    context: FoundryContext | None = None,
) -> dict[str, FastAPI]:
    """Build per-version FastAPI instances and route registered routers to them.

    Loads all modules in the configured project package so that ``VersionedAPIRouter``
    instances created at module import time are registered.  Each router whose
    ``version`` attribute matches a name in *versions* is included in the corresponding
    FastAPI sub-application.

    Args:
        versions: Ordered list of API version names (e.g., ``["v1", "v2"]``).
        context: Project context supplying the package name, title, description, author,
            and URLs for each ``FastAPI`` instance.  When ``None``, the global context
            installed via :func:`aignostics_foundry_core.foundry.set_context` is used.

    Returns:
        Mapping from version name to its configured ``FastAPI`` instance.
    """
    from fastapi import FastAPI  # noqa: PLC0415

    ctx = context or get_context()
    load_modules(context=ctx)
    api_metadata = build_api_metadata(context=ctx)
    api_instances: dict[str, FastAPI] = {version: FastAPI(**api_metadata) for version in versions}

    for router in VersionedAPIRouter.get_instances():
        router_version: str = cast("Any", router).version
        if router_version in api_instances:
            api_instances[router_version].include_router(cast("APIRouter", router))
            for exc_class, handler in cast("Any", router).exception_handlers:
                api_instances[router_version].add_exception_handler(
                    exc_class_or_status_code=exc_class,
                    handler=handler,
                )

    return api_instances


def init_api(
    root_path: str = "",
    lifespan: Any | None = None,  # noqa: ANN401
    exception_handler_registrations: list[tuple[type[Exception], Any]] | None = None,
    versions: list[str] | None = None,
    **fastapi_kwargs: Any,  # noqa: ANN401
) -> FastAPI:
    """Initialise a FastAPI application with standard exception handlers.

    This is a generic factory that creates a ``FastAPI`` instance and registers
    the standard Foundry exception handlers.  When *versions* is supplied the
    function also creates versioned sub-applications via
    ``get_versioned_api_instances`` and mounts each sub-app at ``/{version}``
    on the root app.

    All exception handlers — both the custom ``exception_handler_registrations``
    entries and the 4 standard handlers (``ApiException``,
    ``RequestValidationError``, ``ValidationError``, ``Exception``) — are
    registered on the root app **and** on every versioned sub-app.  This is
    necessary because FastAPI mounted sub-apps handle exceptions independently;
    the root app's handlers never fire for requests matched inside a sub-app.

    Args:
        root_path: ASGI root path (useful for reverse-proxy setups).
        lifespan: Optional async context manager for application lifespan.
        exception_handler_registrations: Additional ``(exc_class, handler)`` pairs
            to register on all app instances before the standard handlers.
        versions: Optional list of API version names (e.g. ``["v1", "v2"]``).
            When provided, ``get_versioned_api_instances`` is called internally
            and each resulting sub-app is mounted at ``/{version}`` on the root
            app.
        **fastapi_kwargs: Extra keyword arguments forwarded to ``FastAPI()``.

    Returns:
        A configured ``FastAPI`` instance.
    """
    from fastapi import FastAPI  # noqa: PLC0415
    from fastapi.exceptions import RequestValidationError  # noqa: PLC0415
    from pydantic import ValidationError  # noqa: PLC0415

    api = FastAPI(root_path=root_path, lifespan=lifespan, **fastapi_kwargs)

    for exc_class, handler in exception_handler_registrations or []:
        api.add_exception_handler(exc_class_or_status_code=exc_class, handler=handler)
    api.add_exception_handler(  # type: ignore[arg-type]
        exc_class_or_status_code=ApiException,
        handler=api_exception_handler,  # pyright: ignore[reportArgumentType]
    )
    api.add_exception_handler(exc_class_or_status_code=RequestValidationError, handler=validation_exception_handler)
    api.add_exception_handler(exc_class_or_status_code=ValidationError, handler=validation_exception_handler)
    api.add_exception_handler(exc_class_or_status_code=Exception, handler=unhandled_exception_handler)

    if versions:
        versioned_apps = get_versioned_api_instances(versions)
        for version_name, version_app in versioned_apps.items():
            for exc_class, handler in exception_handler_registrations or []:
                version_app.add_exception_handler(exc_class_or_status_code=exc_class, handler=handler)
            version_app.add_exception_handler(  # type: ignore[arg-type]
                exc_class_or_status_code=ApiException,
                handler=api_exception_handler,  # pyright: ignore[reportArgumentType]
            )
            version_app.add_exception_handler(
                exc_class_or_status_code=RequestValidationError, handler=validation_exception_handler
            )
            version_app.add_exception_handler(
                exc_class_or_status_code=ValidationError, handler=validation_exception_handler
            )
            version_app.add_exception_handler(exc_class_or_status_code=Exception, handler=unhandled_exception_handler)
            api.mount(f"/{version_name}", version_app)

    return api
