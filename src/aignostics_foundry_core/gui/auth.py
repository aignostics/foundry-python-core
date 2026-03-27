"""Authentication decorators for NiceGUI pages.

This module provides:
- get_gui_user: Get authenticated user from Auth0 session
- require_gui_user: Require authentication, redirect to login if not authenticated
- Page decorators: page_public, page_authenticated, page_admin, page_internal,
  page_internal_admin
- GUINamespace: Configurable namespace for page decorators
- gui: Default GUINamespace singleton (no frame)
"""

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from loguru import logger

from aignostics_foundry_core.api.auth import AUTH0_ROLE_ADMIN, AuthSettings, get_auth_client
from aignostics_foundry_core.sentry import set_sentry_user
from aignostics_foundry_core.settings import load_settings

from .core import RESPONSE_TIMEOUT

CLASS_FORBIDDEN_ERROR = "text-red-500 text-2xl"

# FrameFunc is an optional callable that returns a context manager.
# Call signature: frame_func(title, user=user)
# Example: contextlib.contextmanager-decorated function.
FrameFunc = Callable[..., Any] | None


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


def page_public(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Decorator for public NiceGUI pages with optional frame.

    Creates a page that does not require authentication. The user (or ``None``
    if not authenticated) is passed to the decorated function. Supports both
    sync and async functions.

    Args:
        path: The URL path for the page.
        title: The title passed to ``frame_func`` (if provided).
        frame_func: Optional callable returning a context manager used to wrap
            the page content. Called as ``frame_func(title, user=user)``.

    Returns:
        A decorator that wraps the page function.

    Example:
        @page_public("/public-page")
        def public_page(user: dict[str, Any] | None) -> None:
            if user:
                ui.label(f"Hello, {user.get('name')}")
            else:
                ui.label("Hello, guest!")
    """
    from nicegui import ui  # noqa: PLC0415

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[[Request], Awaitable[None]]:
        @ui.page(path, response_timeout=RESPONSE_TIMEOUT)
        async def wrapper(request: Request) -> None:
            user = await get_gui_user(request)

            if frame_func is not None:
                with frame_func(title, user=user):
                    pass

            if inspect.iscoroutinefunction(func):
                await func(user)
            else:
                func(user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def page_authenticated(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Decorator for authenticated NiceGUI pages with optional frame.

    Creates a page that requires authentication. If the user is not
    authenticated, they are redirected to login with ``returnTo`` set to the
    current page. Supports both sync and async functions.

    Args:
        path: The URL path for the page.
        title: The title passed to ``frame_func`` (if provided).
        frame_func: Optional callable returning a context manager used to wrap
            the page content. Called as ``frame_func(title, user=user)``.

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

            if frame_func is not None:
                with frame_func(title, user=user):
                    pass

            if inspect.iscoroutinefunction(func):
                await func(user)
            else:
                func(user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def page_admin(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Decorator for admin-only NiceGUI pages with optional frame.

    Creates a page that requires authentication and admin role. If the user is
    not authenticated, they are redirected to login. If authenticated but not
    admin, a 403 error is shown. Supports both sync and async functions.

    Args:
        path: The URL path for the page.
        title: The title passed to ``frame_func`` (if provided).
        frame_func: Optional callable returning a context manager used to wrap
            the page content. Called as ``frame_func(title, user=user)``.

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
                if frame_func is not None:
                    with frame_func(title, user=user):
                        pass
                ui.label("403 Forbidden - Admin access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            if frame_func is not None:
                with frame_func(title, user=user):
                    pass

            if inspect.iscoroutinefunction(func):
                await func(user)
            else:
                func(user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def page_internal(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Decorator for internal-org-only NiceGUI pages with optional frame.

    Creates a page that requires authentication and internal org membership.
    If the user is not authenticated, they are redirected to login. If
    authenticated but not in the internal org, a 403 error is shown. Supports
    both sync and async functions.

    Args:
        path: The URL path for the page.
        title: The title passed to ``frame_func`` (if provided).
        frame_func: Optional callable returning a context manager used to wrap
            the page content. Called as ``frame_func(title, user=user)``.

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
                if frame_func is not None:
                    with frame_func(title, user=user):
                        pass
                ui.label("403 Forbidden - Internal access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            if frame_func is not None:
                with frame_func(title, user=user):
                    pass

            if inspect.iscoroutinefunction(func):
                await func(user)
            else:
                func(user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


def page_internal_admin(
    path: str,
    title: str = "",
    frame_func: FrameFunc = None,
) -> Callable[..., Callable[[Request], Awaitable[None]]]:
    """Decorator for internal-org admin-only NiceGUI pages with optional frame.

    Creates a page that requires authentication, internal org membership, AND
    admin role. Supports both sync and async functions.

    Args:
        path: The URL path for the page.
        title: The title passed to ``frame_func`` (if provided).
        frame_func: Optional callable returning a context manager used to wrap
            the page content. Called as ``frame_func(title, user=user)``.

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
                if frame_func is not None:
                    with frame_func(title, user=user):
                        pass
                ui.label("403 Forbidden - Internal admin access required").classes(CLASS_FORBIDDEN_ERROR)
                return

            if frame_func is not None:
                with frame_func(title, user=user):
                    pass

            if inspect.iscoroutinefunction(func):
                await func(user)
            else:
                func(user)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        return wrapper

    return decorator


class GUINamespace:
    """Namespace for NiceGUI page decorators with configurable frame function.

    Provides decorators for creating pages with automatic frame rendering
    and user injection at various access levels.

    Args:
        frame_func: Optional callable returning a context manager for page
            framing. Called as ``frame_func(title, user=user)``.

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

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return page_public(path, title, frame_func=self._frame_func)

    def authenticated(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for authenticated NiceGUI pages.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return page_authenticated(path, title, frame_func=self._frame_func)

    def admin(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for admin-only NiceGUI pages.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return page_admin(path, title, frame_func=self._frame_func)

    def internal(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for internal-org-only NiceGUI pages.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return page_internal(path, title, frame_func=self._frame_func)

    def internal_admin(
        self,
        path: str,
        title: str = "",
    ) -> Callable[..., Callable[[Request], Awaitable[None]]]:
        """Decorator for internal-org admin-only NiceGUI pages.

        Args:
            path: The URL path for the page.
            title: The title passed to the frame function (if configured).

        Returns:
            A decorator that wraps the page function.
        """
        return page_internal_admin(path, title, frame_func=self._frame_func)


gui = GUINamespace()
"""Default GUINamespace singleton without a frame function.

Bridge and other projects can create their own instance with a frame::

    from aignostics_foundry_core.gui.auth import GUINamespace
    gui = GUINamespace(frame_func=my_frame)
"""
