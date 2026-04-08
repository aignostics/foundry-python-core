"""Core GUI utilities for NiceGUI.

This module provides:
- BasePageBuilder: Abstract base class for page registration
- gui_register_pages: Auto-discover and register all PageBuilders
- gui_run: Start the NiceGUI application with optional API mounting
- Constants: WINDOW_SIZE, BROWSER_RECONNECT_TIMEOUT, RESPONSE_TIMEOUT
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from aignostics_foundry_core.di import locate_subclasses
from aignostics_foundry_core.foundry import get_context

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from fastapi.routing import APIRouter

    from aignostics_foundry_core.foundry import FoundryContext
    from aignostics_foundry_core.gui.auth import FrameFunc

WINDOW_SIZE = (1280, 768)
BROWSER_RECONNECT_TIMEOUT = 60 * 60 * 24 * 7  # 7 days
RESPONSE_TIMEOUT = 30


class BasePageBuilder(ABC):
    """Base class for all page builders.

    Modules extend this class to register NiceGUI pages.
    For navigation items, use BaseNavBuilder instead.

    Example:
        class PageBuilder(BasePageBuilder):
            @staticmethod
            def register_pages() -> None:
                @gui.public("/my-page")
                def my_page(user):
                    ui.label("Hello!")
    """

    @staticmethod
    @abstractmethod
    def register_pages() -> None:
        """Register NiceGUI pages."""


def gui_register_pages(*, context: FoundryContext | None = None, frame_func: FrameFunc = None) -> None:
    """Register pages from all discovered PageBuilders and actualize the registry.

    Discovers all ``BasePageBuilder`` subclasses for the configured project,
    calls ``register_pages()`` on each one (which populates ``_registry`` via
    the ``page_*`` decorators), then actualizes every registry entry with the
    given ``frame_func``. The registry is cleared after processing.

    Args:
        context: Project context used for PageBuilder discovery.  When ``None``,
            the global context installed via
            :func:`aignostics_foundry_core.foundry.set_context` is used.
        frame_func: Optional frame callable injected into every registered page.
            Called as ``frame_func(title, user=user)`` inside the page wrapper.
            When ``None``, pages render without a frame.
    """
    from .auth import process_page_registry  # noqa: PLC0415

    page_builders = locate_subclasses(BasePageBuilder, context=context or get_context())
    for page_builder in page_builders:
        page_builder: BasePageBuilder  # type: ignore[no-redef]
        page_builder.register_pages()

    process_page_registry(frame_func=frame_func)


def _register_callbacks(
    app: FastAPI,
    startup_callbacks: list[Callable[[], Any]] | None,
    shutdown_callbacks: list[Callable[[], Any]] | None,
) -> None:
    if startup_callbacks:
        for cb in startup_callbacks:
            app.on_startup(cb)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    if shutdown_callbacks:
        for cb in shutdown_callbacks:
            app.on_shutdown(cb)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


def _mount_fastapi_app(
    app: FastAPI,
    fastapi_app: FastAPI,
    auth_router: APIRouter | None,
) -> None:
    from starlette.responses import RedirectResponse  # noqa: PLC0415

    app.mount("/api", fastapi_app)

    if auth_router is not None:
        existing_paths = {getattr(r, "path", None) for r in app.routes}
        if "/auth/login" not in existing_paths:
            app.include_router(auth_router)

    existing_paths = {getattr(r, "path", None) for r in app.routes}
    if "/docs" not in existing_paths:

        @app.get("/docs", include_in_schema=False)
        def redirect_to_api_docs() -> RedirectResponse:  # pyright: ignore[reportUnusedFunction]
            """Redirect /docs to /api/docs.

            Returns:
                Redirect to the API documentation at /api/docs.
            """
            return RedirectResponse(url="/api/docs")

    if hasattr(fastapi_app.state, "auth_client"):
        app.state.auth_client = fastapi_app.state.auth_client
    if hasattr(fastapi_app.state, "config"):
        app.state.config = fastapi_app.state.config


def gui_run(  # noqa: PLR0913, PLR0917
    show: bool = False,
    host: str | None = None,
    port: int | None = None,
    title: str = "",
    watch: bool = False,
    fastapi_app: FastAPI | None = None,
    auth_router: APIRouter | None = None,
    startup_callbacks: list[Callable[[], Any]] | None = None,
    shutdown_callbacks: list[Callable[[], Any]] | None = None,
    *,
    context: FoundryContext | None = None,
    frame_func: FrameFunc = None,
) -> None:
    """Start the NiceGUI application.

    Args:
        show: Whether to open a browser window on startup.
        host: Host to bind to. Defaults to NiceGUI's default.
        port: Port to listen on. Defaults to an open port found automatically.
        title: Title shown in the browser tab. Defaults to the project name
            from *context*.
        watch: Whether to reload on source file changes.
        fastapi_app: Optional FastAPI application to mount at ``/api``. When
            provided, ``/docs`` is redirected to ``/api/docs``, and the
            ``auth_client`` state is shared with the NiceGUI app.
        auth_router: Optional FastAPI router with auth routes (e.g. Auth0
            ``/auth/login``, ``/auth/callback``, ``/auth/logout``). Included at
            the root level when ``fastapi_app`` is provided.
        startup_callbacks: Optional list of callables registered via
            ``app.on_startup``. Use this to initialise a database engine etc.
        shutdown_callbacks: Optional list of callables registered via
            ``app.on_shutdown``. Use this to dispose resources on shutdown.
        context: Project context used for page builder discovery and window
            title.  When ``None``, the global context installed via
            :func:`aignostics_foundry_core.foundry.set_context` is used.
        frame_func: Optional frame callable forwarded to ``gui_register_pages``.
            Injected into every page registered via the ``page_*`` registry
            decorators.  Called as ``frame_func(title, user=user)``.
    """
    from nicegui import app, ui  # noqa: PLC0415
    from nicegui import native as native_app  # noqa: PLC0415

    ctx = context or get_context()

    _register_callbacks(app, startup_callbacks, shutdown_callbacks)
    gui_register_pages(context=ctx, frame_func=frame_func)

    if fastapi_app is not None:
        _mount_fastapi_app(app, fastapi_app, auth_router)

    ui.run(  # pyright: ignore[reportUnknownMemberType]
        title=title or ctx.name,
        native=False,
        reload=watch,
        host=host,
        port=port or native_app.find_open_port(),
        show_welcome_message=False,
        show=show,
        reconnect_timeout=BROWSER_RECONNECT_TIMEOUT,
    )
