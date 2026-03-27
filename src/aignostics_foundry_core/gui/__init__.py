"""GUI utilities for NiceGUI pages.

This module provides:
- Navigation infrastructure (NavItem, NavGroup, BaseNavBuilder, gui_get_nav_groups)
- Page decorators with authentication (GUINamespace, gui singleton)
- Core GUI functions (gui_run, gui_register_pages)
- Constants (WINDOW_SIZE, BROWSER_RECONNECT_TIMEOUT, RESPONSE_TIMEOUT)
"""

from .auth import (
    GUINamespace,
    get_gui_user,
    gui,
    page_admin,
    page_authenticated,
    page_internal,
    page_internal_admin,
    page_public,
    require_gui_user,
)
from .core import (
    BROWSER_RECONNECT_TIMEOUT,
    RESPONSE_TIMEOUT,
    WINDOW_SIZE,
    BasePageBuilder,
    gui_register_pages,
    gui_run,
)
from .nav import (
    BaseNavBuilder,
    NavGroup,
    NavItem,
    gui_get_nav_groups,
)

__all__ = [
    "BROWSER_RECONNECT_TIMEOUT",
    "RESPONSE_TIMEOUT",
    "WINDOW_SIZE",
    "BaseNavBuilder",
    "BasePageBuilder",
    "GUINamespace",
    "NavGroup",
    "NavItem",
    "get_gui_user",
    "gui",
    "gui_get_nav_groups",
    "gui_register_pages",
    "gui_run",
    "page_admin",
    "page_authenticated",
    "page_internal",
    "page_internal_admin",
    "page_public",
    "require_gui_user",
]
