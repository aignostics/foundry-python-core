"""Tests for aignostics_foundry_core.gui.*."""

import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aignostics_foundry_core.gui.core import (
    BROWSER_RECONNECT_TIMEOUT,
    RESPONSE_TIMEOUT,
    WINDOW_SIZE,
    BasePageBuilder,
    gui_register_pages,
    gui_run,
)
from aignostics_foundry_core.gui.nav import (
    BaseNavBuilder,
    NavGroup,
    NavItem,
    gui_get_nav_groups,
)

_PATCH_GET_GUI_USER = "aignostics_foundry_core.gui.auth.get_gui_user"
_PATCH_GET_AUTH_CLIENT = "aignostics_foundry_core.gui.auth.get_auth_client"
_PATCH_SET_SENTRY_USER = "aignostics_foundry_core.sentry.set_sentry_user"
_PATCH_LOAD_SETTINGS = "aignostics_foundry_core.gui.auth.load_settings"
_PATH_NAV_LOCATE = "aignostics_foundry_core.gui.nav.locate_subclasses"
_PATH_CORE_LOCATE = "aignostics_foundry_core.gui.core.locate_subclasses"

_TEST_PATH = "/test-page"
_INTERNAL_ORG = "org_internal"
_OTHER_ORG = "org_other"
_ROLE_CLAIM = "https://example.com/role"
_PROJECT_NAME = "myproject"
_FIXED_PORT = 9000


# ---------------------------------------------------------------------------
# NavItem
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNavItem:
    """Tests for NavItem dataclass behaviour."""

    def test_marker_auto_generated_from_label(self) -> None:
        """NavItem auto-generates a SCREAMING_SNAKE_CASE marker prefixed with LINK_."""
        item = NavItem(icon="home", label="Hello World", target="/hello")
        assert item.marker == "LINK_HELLO_WORLD"

    def test_marker_strips_parentheses_from_label(self) -> None:
        """Parentheses in the label are removed when auto-generating the marker."""
        item = NavItem(icon="info", label="About (Beta)", target="/about")
        assert item.marker == "LINK_ABOUT_BETA"

    def test_explicit_marker_is_preserved(self) -> None:
        """When a marker is supplied explicitly, __post_init__ must not overwrite it."""
        item = NavItem(icon="home", label="Home", target="/", marker="MY_CUSTOM_MARKER")
        assert item.marker == "MY_CUSTOM_MARKER"

    def test_new_tab_defaults_to_false(self) -> None:
        """new_tab defaults to False (same-tab navigation)."""
        item = NavItem(icon="link", label="Link", target="/link")
        assert item.new_tab is False


# ---------------------------------------------------------------------------
# NavGroup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNavGroup:
    """Tests for NavGroup dataclass defaults."""

    def test_position_default(self) -> None:
        """Default position is 1000 (lowest priority)."""
        group = NavGroup(name="My Module")
        assert group.position == 1000

    def test_icon_default(self) -> None:
        """Default icon is 'folder'."""
        group = NavGroup(name="My Module")
        assert group.icon == "folder"

    def test_use_expansion_default(self) -> None:
        """Default use_expansion is True."""
        group = NavGroup(name="My Module")
        assert group.use_expansion is True

    def test_items_default_empty(self) -> None:
        """Default items list is empty."""
        group = NavGroup(name="My Module")
        assert group.items == []


# ---------------------------------------------------------------------------
# BaseNavBuilder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseNavBuilder:
    """Tests for BaseNavBuilder abstractness."""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseNavBuilder is abstract; direct instantiation raises TypeError."""
        with pytest.raises(TypeError):
            BaseNavBuilder()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# gui_get_nav_groups
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGuiGetNavGroups:
    """Tests for gui_get_nav_groups behaviour."""

    def test_returns_empty_list_when_no_builders(self) -> None:
        """gui_get_nav_groups returns [] when no NavBuilders are discovered."""
        with patch(_PATH_NAV_LOCATE, return_value=[]):
            result = gui_get_nav_groups("myproject")
        assert result == []

    def test_collects_group_from_single_builder(self) -> None:
        """gui_get_nav_groups wraps each builder's items in a NavGroup."""
        items = [NavItem(icon="home", label="Home", target="/")]

        class FakeBuilder(BaseNavBuilder):
            @staticmethod
            def get_nav_name() -> str:
                return "Fake"

            @staticmethod
            def get_nav_items() -> list[NavItem]:
                return items

        with patch(_PATH_NAV_LOCATE, return_value=[FakeBuilder]):
            result = gui_get_nav_groups("myproject")

        assert len(result) == 1
        assert result[0].name == "Fake"
        assert result[0].items == items

    def test_groups_sorted_by_position(self) -> None:
        """gui_get_nav_groups returns groups ordered by ascending position."""

        class LowPriority(BaseNavBuilder):
            @staticmethod
            def get_nav_name() -> str:
                return "Low"

            @staticmethod
            def get_nav_items() -> list[NavItem]:
                return [NavItem(icon="x", label="X", target="/x")]

            @staticmethod
            def get_nav_position() -> int:
                return 900

        class HighPriority(BaseNavBuilder):
            @staticmethod
            def get_nav_name() -> str:
                return "High"

            @staticmethod
            def get_nav_items() -> list[NavItem]:
                return [NavItem(icon="y", label="Y", target="/y")]

            @staticmethod
            def get_nav_position() -> int:
                return 100

        with patch(_PATH_NAV_LOCATE, return_value=[LowPriority, HighPriority]):
            result = gui_get_nav_groups("myproject")

        assert [g.name for g in result] == ["High", "Low"]

    def test_skips_builders_with_empty_items(self) -> None:
        """Builders that return no items are excluded from the result."""

        class EmptyBuilder(BaseNavBuilder):
            @staticmethod
            def get_nav_name() -> str:
                return "Empty"

            @staticmethod
            def get_nav_items() -> list[NavItem]:
                return []

        with patch(_PATH_NAV_LOCATE, return_value=[EmptyBuilder]):
            result = gui_get_nav_groups("myproject")

        assert result == []


# ---------------------------------------------------------------------------
# BasePageBuilder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBasePageBuilder:
    """Tests for BasePageBuilder abstractness."""

    def test_cannot_instantiate_directly(self) -> None:
        """BasePageBuilder is abstract; direct instantiation raises TypeError."""
        with pytest.raises(TypeError):
            BasePageBuilder()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstants:
    """Tests for gui constants."""

    def test_response_timeout(self) -> None:
        """RESPONSE_TIMEOUT is 30 seconds."""
        assert RESPONSE_TIMEOUT == 30

    def test_window_size_tuple(self) -> None:
        """WINDOW_SIZE is a (width, height) tuple with positive dimensions."""
        w, h = WINDOW_SIZE
        assert w > 0
        assert h > 0

    def test_browser_reconnect_timeout_is_long(self) -> None:
        """BROWSER_RECONNECT_TIMEOUT is at least one day in seconds."""
        assert BROWSER_RECONNECT_TIMEOUT >= 60 * 60 * 24


# ---------------------------------------------------------------------------
# gui_register_pages
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGuiRegisterPages:
    """Tests for gui_register_pages behaviour."""

    def test_calls_register_pages_on_each_builder(self) -> None:
        """gui_register_pages calls register_pages() on every discovered builder."""
        builder_a = MagicMock(spec=BasePageBuilder)
        builder_b = MagicMock(spec=BasePageBuilder)

        with patch(_PATH_CORE_LOCATE, return_value=[builder_a, builder_b]):
            gui_register_pages("myproject")

        builder_a.register_pages.assert_called_once()
        builder_b.register_pages.assert_called_once()

    def test_no_error_when_no_builders_found(self) -> None:
        """gui_register_pages silently succeeds when no builders are discovered."""
        with patch(_PATH_CORE_LOCATE, return_value=[]):
            gui_register_pages(_PROJECT_NAME)  # must not raise


# ---------------------------------------------------------------------------
# gui_run
# ---------------------------------------------------------------------------


def _make_nicegui_app_mock() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (nicegui_mock, app_mock, ui_mock).

    Constructs a nicegui mock suitable for testing gui_run:
    - app_mock has routes=[] and a MagicMock state
    - ui_mock.run is a MagicMock
    - native_mock.find_open_port() returns _FIXED_PORT
    """
    app_mock = MagicMock()
    app_mock.routes = []

    ui_mock = MagicMock()

    native_mock = MagicMock()
    native_mock.find_open_port.return_value = _FIXED_PORT

    nicegui_mock = MagicMock()
    nicegui_mock.app = app_mock
    nicegui_mock.ui = ui_mock
    nicegui_mock.native = native_mock

    return nicegui_mock, app_mock, ui_mock


@pytest.mark.unit
class TestGuiRun:
    """Tests for gui_run behaviour."""

    def _call_gui_run(self, nicegui_mock: MagicMock, **kwargs: object) -> None:
        """Call gui_run(_PROJECT_NAME) with nicegui and locate_subclasses mocked."""
        with (
            patch.dict(sys.modules, {"nicegui": nicegui_mock, "starlette.responses": MagicMock()}),
            patch(_PATH_CORE_LOCATE, return_value=[]),
        ):
            gui_run(_PROJECT_NAME, **kwargs)  # type: ignore[arg-type]

    def test_ui_run_called_with_project_name_as_title(self) -> None:
        """When title is empty, ui.run receives project_name as title."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock, title="")
        assert ui_mock.run.call_args.kwargs["title"] == _PROJECT_NAME

    def test_ui_run_called_with_explicit_title(self) -> None:
        """Explicit title is passed through to ui.run."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock, title="My App")
        assert ui_mock.run.call_args.kwargs["title"] == "My App"

    def test_watch_flag_maps_to_reload_in_ui_run(self) -> None:
        """watch=True passes reload=True to ui.run."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock, watch=True)
        assert ui_mock.run.call_args.kwargs["reload"] is True

    def test_port_defaults_to_find_open_port(self) -> None:
        """When port=None, native.find_open_port() result is used for port in ui.run."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock)
        assert ui_mock.run.call_args.kwargs["port"] == _FIXED_PORT

    def test_explicit_port_passed_to_ui_run(self) -> None:
        """Explicit port is forwarded directly to ui.run."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock, port=8080)
        assert ui_mock.run.call_args.kwargs["port"] == 8080

    def test_reconnect_timeout_uses_constant(self) -> None:
        """ui.run receives reconnect_timeout=BROWSER_RECONNECT_TIMEOUT."""
        nicegui_mock, _, ui_mock = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock)
        assert ui_mock.run.call_args.kwargs["reconnect_timeout"] == BROWSER_RECONNECT_TIMEOUT

    def test_startup_callbacks_registered(self) -> None:
        """Each callable in startup_callbacks is passed to app.on_startup once."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        cb1, cb2 = MagicMock(), MagicMock()
        self._call_gui_run(nicegui_mock, startup_callbacks=[cb1, cb2])
        app_mock.on_startup.assert_any_call(cb1)
        app_mock.on_startup.assert_any_call(cb2)
        assert app_mock.on_startup.call_count == 2

    def test_shutdown_callbacks_registered(self) -> None:
        """Each callable in shutdown_callbacks is passed to app.on_shutdown once."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        cb1, cb2 = MagicMock(), MagicMock()
        self._call_gui_run(nicegui_mock, shutdown_callbacks=[cb1, cb2])
        app_mock.on_shutdown.assert_any_call(cb1)
        app_mock.on_shutdown.assert_any_call(cb2)
        assert app_mock.on_shutdown.call_count == 2

    def test_no_callbacks_does_not_error(self) -> None:
        """gui_run with no optional args completes without raising."""
        nicegui_mock, _, _ = _make_nicegui_app_mock()
        self._call_gui_run(nicegui_mock)  # must not raise

    def test_fastapi_app_mounted_at_api(self) -> None:
        """When fastapi_app is provided, app.mount('/api', fastapi_app) is called."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace()
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock)
        app_mock.mount.assert_called_once_with("/api", fastapi_mock)

    def test_auth_router_included_when_login_not_present(self) -> None:
        """When auth_router is provided and no /auth/login route exists, include_router is called."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace()
        auth_router_mock = MagicMock()
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock, auth_router=auth_router_mock)
        app_mock.include_router.assert_called_once_with(auth_router_mock)

    def test_auth_router_skipped_when_login_already_present(self) -> None:
        """When /auth/login route already exists, include_router is NOT called."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        login_route = MagicMock()
        login_route.path = "/auth/login"
        app_mock.routes = [login_route]
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace()
        auth_router_mock = MagicMock()
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock, auth_router=auth_router_mock)
        app_mock.include_router.assert_not_called()

    def test_docs_redirect_added_when_not_present(self) -> None:
        """When fastapi_app is provided and no /docs route exists, app.get('/docs', ...) is called."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace()
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock)
        docs_calls = [c for c in app_mock.get.call_args_list if c.args[0] == "/docs"]
        assert len(docs_calls) == 1

    def test_docs_redirect_skipped_when_already_present(self) -> None:
        """When /docs route already exists, app.get is NOT called for /docs."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        docs_route = MagicMock()
        docs_route.path = "/docs"
        app_mock.routes = [docs_route]
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace()
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock)
        docs_calls = [c for c in app_mock.get.call_args_list if c.args[0] == "/docs"]
        assert len(docs_calls) == 0

    def test_auth_client_state_copied(self) -> None:
        """When fastapi_app.state has auth_client, it is assigned to nicegui app.state.auth_client."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        auth_client = MagicMock()
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace(auth_client=auth_client)
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock)
        assert app_mock.state.auth_client is auth_client

    def test_config_state_copied(self) -> None:
        """When fastapi_app.state has config, it is assigned to nicegui app.state.config."""
        nicegui_mock, app_mock, _ = _make_nicegui_app_mock()
        config = MagicMock()
        fastapi_mock = MagicMock()
        fastapi_mock.state = SimpleNamespace(config=config)
        self._call_gui_run(nicegui_mock, fastapi_app=fastapi_mock)
        assert app_mock.state.config is config

    def test_gui_register_pages_called(self) -> None:
        """locate_subclasses is invoked with BasePageBuilder and the project name."""
        nicegui_mock, _, _ = _make_nicegui_app_mock()
        with (
            patch.dict(sys.modules, {"nicegui": nicegui_mock, "starlette.responses": MagicMock()}),
            patch(_PATH_CORE_LOCATE, return_value=[]) as locate_mock,
        ):
            gui_run(_PROJECT_NAME)
        locate_mock.assert_called_once_with(BasePageBuilder, _PROJECT_NAME)


# ---------------------------------------------------------------------------
# get_gui_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetGuiUser:
    """Tests for get_gui_user behaviour."""

    async def test_returns_none_when_auth_client_raises(self) -> None:
        """Returns None when get_auth_client raises (no auth configured)."""
        from aignostics_foundry_core.gui.auth import get_gui_user

        request = MagicMock()
        with patch(_PATCH_GET_AUTH_CLIENT, side_effect=RuntimeError("no auth")):
            result = await get_gui_user(request)

        assert result is None

    async def test_returns_none_for_expired_session(self) -> None:
        """Returns None when the session user's exp claim is in the past."""
        from aignostics_foundry_core.gui.auth import get_gui_user

        request = MagicMock()
        expired_user = {"sub": "auth0|x", "exp": int(time.time()) - 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": expired_user})

        with (
            patch(_PATCH_GET_AUTH_CLIENT, return_value=fake_client),
            patch(_PATCH_SET_SENTRY_USER),
        ):
            result = await get_gui_user(request)

        assert result is None

    async def test_returns_none_when_exp_claim_missing(self) -> None:
        """Returns None when the session user dict has no 'exp' claim."""
        from aignostics_foundry_core.gui.auth import get_gui_user

        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": {"sub": "auth0|x"}})

        with (
            patch(_PATCH_GET_AUTH_CLIENT, return_value=fake_client),
            patch(_PATCH_SET_SENTRY_USER),
        ):
            result = await get_gui_user(request)

        assert result is None

    async def test_returns_user_for_valid_session(self) -> None:
        """Returns the user dict when the session is valid and not expired."""
        from aignostics_foundry_core.gui.auth import get_gui_user

        request = MagicMock()
        user = {"sub": "auth0|x", "email": "x@x.com", "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})

        with (
            patch(_PATCH_GET_AUTH_CLIENT, return_value=fake_client),
            patch(_PATCH_SET_SENTRY_USER),
        ):
            result = await get_gui_user(request)

        assert result == user

    async def test_returns_none_when_session_has_no_user_key(self) -> None:
        """Returns None when the session dict contains no 'user' key."""
        from aignostics_foundry_core.gui.auth import get_gui_user

        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={})

        with patch(_PATCH_GET_AUTH_CLIENT, return_value=fake_client):
            result = await get_gui_user(request)

        assert result is None


# ---------------------------------------------------------------------------
# require_gui_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireGuiUser:
    """Tests for require_gui_user behaviour."""

    async def test_redirects_to_login_when_no_user(self) -> None:
        """Redirects to /auth/login when get_gui_user returns None."""
        from aignostics_foundry_core.gui.auth import require_gui_user

        request = MagicMock()
        request.url.path = "/protected"

        navigate_mock = MagicMock()
        nicegui_mock = MagicMock()
        nicegui_mock.ui.navigate.to = navigate_mock

        with (
            patch(_PATCH_GET_GUI_USER, new=AsyncMock(return_value=None)),
            patch.dict(sys.modules, {"nicegui": nicegui_mock}),
        ):
            result = await require_gui_user(request)

        assert result is None
        navigate_mock.assert_called_once()
        call_url: str = navigate_mock.call_args[0][0]
        assert call_url.startswith("/auth/login")

    async def test_returns_user_when_authenticated(self) -> None:
        """Returns the user dict when the session is valid."""
        from aignostics_foundry_core.gui.auth import require_gui_user

        request = MagicMock()
        user = {"sub": "auth0|x", "exp": int(time.time()) + 3600}

        with patch(_PATCH_GET_GUI_USER, new=AsyncMock(return_value=user)):
            result = await require_gui_user(request)

        assert result == user

    async def test_uses_return_to_override(self) -> None:
        """When return_to is specified it appears in the redirect URL."""
        from aignostics_foundry_core.gui.auth import require_gui_user

        request = MagicMock()
        request.url.path = "/original"

        navigate_mock = MagicMock()
        nicegui_mock = MagicMock()
        nicegui_mock.ui.navigate.to = navigate_mock

        with (
            patch(_PATCH_GET_GUI_USER, new=AsyncMock(return_value=None)),
            patch.dict(sys.modules, {"nicegui": nicegui_mock}),
        ):
            await require_gui_user(request, return_to="/custom-return")

        call_url: str = navigate_mock.call_args[0][0]
        assert "/custom-return" in call_url


# ---------------------------------------------------------------------------
# Page decorator registration
# ---------------------------------------------------------------------------


def _make_nicegui_mock() -> tuple[MagicMock, MagicMock]:
    """Return (nicegui_mock, page_call_recorder).

    ui.page(path, response_timeout=...) → identity decorator (no-op wrapper).
    """
    page_recorder = MagicMock()
    page_recorder.side_effect = lambda *a, **kw: lambda f: f  # pyright: ignore[reportUnknownLambdaType] # no-op decorator

    nicegui_mock = MagicMock()
    nicegui_mock.ui.page = page_recorder
    return nicegui_mock, page_recorder


@pytest.mark.unit
class TestPagePublicRegistration:
    """Tests for page_public route registration."""

    def test_registers_route_with_ui_page(self) -> None:
        """page_public calls ui.page with the supplied path and RESPONSE_TIMEOUT."""
        from aignostics_foundry_core.gui.auth import page_public

        nicegui_mock, page_recorder = _make_nicegui_mock()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            page_public(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)

    def test_preserves_function_name(self) -> None:
        """page_public preserves the decorated function's __name__."""
        from aignostics_foundry_core.gui.auth import page_public

        nicegui_mock, _ = _make_nicegui_mock()

        def my_named_page(user: object) -> None:
            pass

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            result = page_public(_TEST_PATH)(my_named_page)

        assert result.__name__ == "my_named_page"


@pytest.mark.unit
class TestPageAuthenticatedRegistration:
    """Tests for page_authenticated route registration."""

    def test_registers_route_with_ui_page(self) -> None:
        """page_authenticated calls ui.page with the supplied path."""
        from aignostics_foundry_core.gui.auth import page_authenticated

        nicegui_mock, page_recorder = _make_nicegui_mock()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            page_authenticated(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)


@pytest.mark.unit
class TestPageAdminRegistration:
    """Tests for page_admin route registration."""

    def test_registers_route_with_ui_page(self) -> None:
        """page_admin calls ui.page with the supplied path."""
        from aignostics_foundry_core.gui.auth import page_admin

        nicegui_mock, page_recorder = _make_nicegui_mock()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            page_admin(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)


@pytest.mark.unit
class TestPageInternalRegistration:
    """Tests for page_internal route registration."""

    def test_registers_route_with_ui_page(self) -> None:
        """page_internal calls ui.page with the supplied path."""
        from aignostics_foundry_core.gui.auth import page_internal

        nicegui_mock, page_recorder = _make_nicegui_mock()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            page_internal(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)


@pytest.mark.unit
class TestPageInternalAdminRegistration:
    """Tests for page_internal_admin route registration."""

    def test_registers_route_with_ui_page(self) -> None:
        """page_internal_admin calls ui.page with the supplied path."""
        from aignostics_foundry_core.gui.auth import page_internal_admin

        nicegui_mock, page_recorder = _make_nicegui_mock()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            page_internal_admin(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)


# ---------------------------------------------------------------------------
# GUINamespace
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGUINamespace:
    """Tests for GUINamespace and the gui singleton."""

    def test_gui_singleton_is_gui_namespace(self) -> None:
        """The module-level gui object is an instance of GUINamespace."""
        from aignostics_foundry_core.gui.auth import GUINamespace, gui

        assert isinstance(gui, GUINamespace)

    def test_public_method_delegates_to_page_public(self) -> None:
        """GUINamespace.public registers a route via ui.page."""
        from aignostics_foundry_core.gui.auth import GUINamespace

        nicegui_mock, page_recorder = _make_nicegui_mock()
        namespace = GUINamespace()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            namespace.public(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)

    def test_authenticated_method_delegates_to_page_authenticated(self) -> None:
        """GUINamespace.authenticated registers a route via ui.page."""
        from aignostics_foundry_core.gui.auth import GUINamespace

        nicegui_mock, page_recorder = _make_nicegui_mock()
        namespace = GUINamespace()

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            namespace.authenticated(_TEST_PATH)(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        page_recorder.assert_called_once_with(_TEST_PATH, response_timeout=RESPONSE_TIMEOUT)

    def test_frame_func_is_called_in_wrapper(self) -> None:
        """When frame_func is provided it is called inside the page wrapper."""
        import asyncio

        from aignostics_foundry_core.gui.auth import GUINamespace

        frame_entered: list[bool] = []

        @contextmanager
        def fake_frame(title: str, **_kw: object):  # type: ignore[misc]
            frame_entered.append(True)
            yield

        namespace = GUINamespace(frame_func=fake_frame)

        nicegui_mock = MagicMock()
        # Capture the async wrapper created by the decorator
        wrappers: list[object] = []
        nicegui_mock.ui.page.side_effect = (  # pyright: ignore[reportUnknownMemberType]
            lambda *a, **kw: lambda f: wrappers.append(f) or f  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        )

        with patch.dict(sys.modules, {"nicegui": nicegui_mock}):
            namespace.public("/framed")(lambda user: None)  # pyright: ignore[reportUnknownLambdaType]

        assert len(wrappers) == 1
        request = MagicMock()
        request.url.path = "/framed"

        with patch(_PATCH_GET_GUI_USER, new=AsyncMock(return_value=None)):
            asyncio.run(wrappers[0](request))  # type: ignore[arg-type]

        assert frame_entered == [True]
