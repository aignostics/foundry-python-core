"""Authentication decorators for NiceGUI pages.

This module provides:
- get_gui_user: Get authenticated user from Auth0 session
- require_gui_user: Require authentication, redirect to login if not authenticated
- Page actualize functions (private): _actualize_public, _actualize_authenticated,
  _actualize_admin, _actualize_internal, _actualize_internal_admin
- Page registry decorators: page_public, page_authenticated, page_admin, page_internal,
  page_internal_admin
- clear_page_registry: Clear the global page registry (for test isolation)
- GUINamespace: Configurable namespace for page decorators
- gui: Default GUINamespace singleton (no frame)

References:
    docs/decisions/0005-gui-page-registration.md

Example (registry-based, new style)::

    from aignostics_foundry_core.gui import page_authenticated, gui_run


    @page_authenticated("/dashboard")
    def dashboard(user: dict) -> None:
        ui.label(f"Hello, {user['name']}")


    # Later, in main:
    gui_run(frame_func=my_frame)  # Actualizes all registered pages

Example (namespace-based, legacy style)::

    from aignostics_foundry_core.gui import GUINamespace

    gui = GUINamespace(frame_func=my_frame)


    @gui.authenticated("/dashboard")
    def dashboard(user: dict) -> None:
        ui.label(f"Hello, {user['name']}")
"""

import contextlib
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import Request
from loguru import logger

from aignostics_foundry_core.api.auth import AUTH0_ROLE_ADMIN, AuthSettings, get_auth_client
from aignostics_foundry_core.sentry import set_sentry_user
from aignostics_foundry_core.settings import load_settings

from .core import RESPONSE_TIMEOUT

CLASS_FORBIDDEN_ERROR = "text-red-500 text-2xl"
MSG_403_FORBIDDEN = "403 Forbidden"

# FrameFunc is an optional callable that returns a context manager.
# Call signature: frame_func(title, user=user)
# Example: contextlib.contextmanager-decorated function.
FrameFunc = Callable[..., Any] | None


class AccessLevel(StrEnum):
    """Access level for a registered NiceGUI page."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"
    INTERNAL = "internal"
    INTERNAL_ADMIN = "internal_admin"


@dataclass
class _PageEntry:
    """Registry entry for a deferred NiceGUI page registration."""

    access: AccessLevel
    path: str
    title: str
    func: Callable[..., Any]


# Module-level registry — NOT thread-safe. Tests MUST call clear_page_registry()
# in setup/teardown. Production code should only write during module import and
# read during gui_register_pages().
_registry: list[_PageEntry] = []


def clear_page_registry() -> None:
    """Clear the global page registry.

    Call in test teardown to ensure isolation between tests. Each test that
    exercises page registration should clear the registry before and after.
    """
    _registry.clear()


def process_page_registry(frame_func: FrameFunc = None) -> None:
    """Actualize all entries in the page registry and clear it.

    Iterates over every ``_PageEntry`` recorded by the ``page_*`` decorators,
    calls the matching ``_actualize_*`` function with the given ``frame_func``,
    then clears the registry.

    Called by ``gui_register_pages`` after all ``BasePageBuilder.register_pages()``
    methods have run.

    Args:
        frame_func: Optional frame callable injected into every registered page.
            Called as ``frame_func(title, user=user)`` inside the page wrapper.
            When ``None``, pages render without a frame.
    """
    actualize_map = {
        AccessLevel.PUBLIC: _actualize_public,
        AccessLevel.AUTHENTICATED: _actualize_authenticated,
        AccessLevel.ADMIN: _actualize_admin,
        AccessLevel.INTERNAL: _actualize_internal,
        AccessLevel.INTERNAL_ADMIN: _actualize_internal_admin,
    }
    for entry in _registry:
        actualize_map[entry.access](entry.path, entry.title, frame_func=frame_func)(entry.func)
    _registry.clear()


async def _invoke_page_func(func: Callable[..., Any], user: dict[str, Any] | None) -> None:
    """Invoke a page function, awaiting it if it is a coroutine function."""
    if inspect.iscoroutinefunction(func):
        await func(user)
    else:
        func(user)


async def get_gui_user(request: Request) -> dict[str, Any] | None:
    """Get authenticated user from Auth0 session for NiceGUI pages.

    Extracts the authenticated user from the Auth0 session stored in cookies.
    Use this in NiceGUI page functions that accept a ``Request`` parameter to
    get the current user.

    Args:
        request: The incoming FastAPI/Starlette request.

    Returns:
        User dictionary from Auth0 session containing keys like ``name``,
        ``email``, ``picture``, etc. Returns ``None`` if not authenticated,
        session is missing, or the session has expired.
    """
    from fastapi import Response  # noqa: PLC0415

    auth_settings = load_settings(AuthSettings)

    try:
        auth_client = get_auth_client(request)
        session: dict[str, Any] = await auth_client.require_session(request, Response())  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    except Exception:  # noqa: BLE001
        msg = "No session found"
        logger.debug(msg)
        return None

    raw_user = session.get("user")
    if not raw_user or not isinstance(raw_user, dict):
        msg = "Failed to retrieve user information from session"
        logger.critical(msg)
        return None
    user: dict[str, Any] = raw_user  # pyright: ignore[reportUnknownVariableType]

    set_sentry_user(user, role_claim=auth_settings.auth0_role_claim)  # pyright: ignore[reportUnknownArgumentType]

    exp = user.get("exp")
    if not exp:
        msg = "User session is missing expiration claim"
        logger.critical(msg)
        return None

    if exp < int(time.time()):  # pyright: ignore[reportOperatorIssue]
        msg = "User session has expired"
        logger.debug(msg)
        return None

    return user


async def require_gui_user(request: Request, return_to: str | None = None) -> dict[str, Any] | None:
    """Require authenticated user for NiceGUI pages, redirecting to login if not authenticated.

    Checks if the user is authenticated and redirects to the login page if not.
    Use this for pages that require authentication.

    Args:
        request: The incoming FastAPI/Starlette request.
        return_to: URL to redirect back to after login. If ``None``, uses
            ``request.url.path``.

    Returns:
        User dictionary from Auth0 session if authenticated, ``None`` if
        redirecting to login.
    """
    from nicegui import ui  # noqa: PLC0415

    user = await get_gui_user(request)
    if not user:
        redirect_path = return_to or request.url.path
        login_url = f"/auth/login?returnTo={redirect_path}"
        ui.navigate.to(login_url)
        return None
    return user


# ---------------------------------------------------------------------------
# Private actualize functions — called immediately with a known frame_func.
# Used by GUINamespace methods and by gui_register_pages when processing the
# registry.
# ---------------------------------------------------------------------------


def _actualize_public(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Register a public NiceGUI page immediately with the given frame_func.

    Returns:
        A decorator that wraps the page function.
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await get_gui_user(request)
            with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                await _invoke_page_func(func, user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def _actualize_authenticated(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Register an authenticated NiceGUI page immediately with the given frame_func.

    Returns:
        A decorator that wraps the page function.
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await require_gui_user(request)
            if not user:
                return
            with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                await _invoke_page_func(func, user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def _actualize_admin(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Register an admin-only NiceGUI page immediately with the given frame_func.

    Returns:
        A decorator that wraps the page function.
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await require_gui_user(request)
            if not user:
                return

            auth_settings = load_settings(AuthSettings)
            role = user.get(auth_settings.auth0_role_claim)
            if role != AUTH0_ROLE_ADMIN:
                with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                    ui.label(f"{MSG_403_FORBIDDEN} - Admin access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                await _invoke_page_func(func, user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def _actualize_internal(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Register an internal-org-only NiceGUI page immediately with the given frame_func.

    Returns:
        A decorator that wraps the page function.
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await require_gui_user(request)
            if not user:
                return

            auth_settings = load_settings(AuthSettings)
            org_id = user.get("org_id")
            if org_id != auth_settings.internal_org_id:
                with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                    ui.label(f"{MSG_403_FORBIDDEN} - Internal access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                await _invoke_page_func(func, user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def _actualize_internal_admin(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Register an internal-org admin-only NiceGUI page immediately with the given frame_func.

    Returns:
        A decorator that wraps the page function.
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await require_gui_user(request)
            if not user:
                return

            auth_settings = load_settings(AuthSettings)
            org_id = user.get("org_id")
            role = user.get(auth_settings.auth0_role_claim)

            if org_id != auth_settings.internal_org_id or role != AUTH0_ROLE_ADMIN:
                with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                    ui.label(f"{MSG_403_FORBIDDEN} - Internal admin access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            with frame_func(title, user=user) if frame_func is not None else contextlib.nullcontext():
                await _invoke_page_func(func, user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Public registry decorators — write intent to _registry; frame_func is
# injected later by gui_register_pages(frame_func=...).
# ---------------------------------------------------------------------------


def page_public(path: str, title: str = "") -> Callable[..., Any]:
    """Decorator that registers a public page in the global registry.

    The route is NOT registered with NiceGUI immediately. Call
    ``gui_register_pages(frame_func=...)`` to actualize all registered pages
    with the appropriate frame.

    Args:
        path: The URL path for the page.
        title: The title passed to the frame function when the page is actualized.

    Returns:
        A decorator that records the page function in the registry and returns
        it unchanged.

    Example:
        @page_public("/")
        def home(user: dict[str, Any] | None) -> None:
            ui.label("Welcome!")
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _registry.append(_PageEntry(AccessLevel.PUBLIC, path, title, func))
        return func

    return decorator


def page_authenticated(path: str, title: str = "") -> Callable[..., Any]:
    """Decorator that registers an authenticated page in the global registry.

    The route is NOT registered with NiceGUI immediately. Call
    ``gui_register_pages(frame_func=...)`` to actualize all registered pages
    with the appropriate frame.

    Args:
        path: The URL path for the page.
        title: The title passed to the frame function when the page is actualized.

    Returns:
        A decorator that records the page function in the registry and returns
        it unchanged.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _registry.append(_PageEntry(AccessLevel.AUTHENTICATED, path, title, func))
        return func

    return decorator


def page_admin(path: str, title: str = "") -> Callable[..., Any]:
    """Decorator that registers an admin-only page in the global registry.

    The route is NOT registered with NiceGUI immediately. Call
    ``gui_register_pages(frame_func=...)`` to actualize all registered pages
    with the appropriate frame.

    Args:
        path: The URL path for the page.
        title: The title passed to the frame function when the page is actualized.

    Returns:
        A decorator that records the page function in the registry and returns
        it unchanged.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _registry.append(_PageEntry(AccessLevel.ADMIN, path, title, func))
        return func

    return decorator


def page_internal(path: str, title: str = "") -> Callable[..., Any]:
    """Decorator that registers an internal-org-only page in the global registry.

    The route is NOT registered with NiceGUI immediately. Call
    ``gui_register_pages(frame_func=...)`` to actualize all registered pages
    with the appropriate frame.

    Args:
        path: The URL path for the page.
        title: The title passed to the frame function when the page is actualized.

    Returns:
        A decorator that records the page function in the registry and returns
        it unchanged.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _registry.append(_PageEntry(AccessLevel.INTERNAL, path, title, func))
        return func

    return decorator


def page_internal_admin(path: str, title: str = "") -> Callable[..., Any]:
    """Decorator that registers an internal-org admin-only page in the global registry.

    The route is NOT registered with NiceGUI immediately. Call
    ``gui_register_pages(frame_func=...)`` to actualize all registered pages
    with the appropriate frame.

    Args:
        path: The URL path for the page.
        title: The title passed to the frame function when the page is actualized.

    Returns:
        A decorator that records the page function in the registry and returns
        it unchanged.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _registry.append(_PageEntry(AccessLevel.INTERNAL_ADMIN, path, title, func))
        return func

    return decorator


class GUINamespace:
    """Namespace for NiceGUI page decorators with configurable frame function.

    Provides decorators for creating pages with automatic frame rendering
    and user injection at various access levels. Unlike the standalone
    ``page_*`` registry decorators, ``GUINamespace`` methods actualize the
    route immediately (bypassing the registry) using the frame function
    supplied at construction time.

    Args:
        frame_func: Optional callable returning a context manager for page
            framing. Called as ``frame_func(title, user=user)``.

    References:
        docs/decisions/0005-gui-page-registration.md

    Example:
        from aignostics_foundry_core.gui import gui

        @gui.public("/public-page")
        async def public_page(user: dict[str, Any] | None) -> None:
            ui.label(f"Hello, {user.get('name') if user else 'guest'}!")

        @gui.authenticated("/protected-page")
        async def protected_page(user: dict[str, Any]) -> None:
            ui.label(f"Hello, {user.get('name')}")
    """

    def __init__(self, frame_func: FrameFunc = None) -> None:
        """Initialize GUINamespace.

        Args:
            frame_func: Optional callable returning a context manager for page
                framing. Called as ``frame_func(title, user=user)``.
        """
        self._frame_func = frame_func

    def public(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for public NiceGUI pages.

        Registers the route immediately via ``_actualize_public``, bypassing
        the global registry.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return _actualize_public(path, title, frame_func=self._frame_func)

    def authenticated(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for authenticated NiceGUI pages.

        Registers the route immediately via ``_actualize_authenticated``,
        bypassing the global registry.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return _actualize_authenticated(path, title, frame_func=self._frame_func)

    def admin(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for admin-only NiceGUI pages.

        Registers the route immediately via ``_actualize_admin``, bypassing
        the global registry.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return _actualize_admin(path, title, frame_func=self._frame_func)

    def internal(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for internal-org-only NiceGUI pages.

        Registers the route immediately via ``_actualize_internal``, bypassing
        the global registry.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return _actualize_internal(path, title, frame_func=self._frame_func)

    def internal_admin(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for internal-org admin-only NiceGUI pages.

        Registers the route immediately via ``_actualize_internal_admin``,
        bypassing the global registry.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return _actualize_internal_admin(path, title, frame_func=self._frame_func)


gui = GUINamespace()
"""Default GUINamespace singleton without a frame function.

Bridge and other projects can create their own instance with a frame::

    from aignostics_foundry_core.gui.auth import GUINamespace
    gui = GUINamespace(frame_func=my_frame)
"""
