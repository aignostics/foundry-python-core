"""Navigation infrastructure for NiceGUI sidebar.

This module provides:
- NavItem: Individual navigation item dataclass
- NavGroup: Group of navigation items
- BaseNavBuilder: Abstract base class for module navigation builders
- gui_get_nav_groups: Collect and sort navigation groups from all NavBuilders
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aignostics_foundry_core.di import locate_subclasses
from aignostics_foundry_core.foundry import get_context

if TYPE_CHECKING:
    from aignostics_foundry_core.foundry import FoundryContext


@dataclass
class NavItem:
    """Navigation item for sidebar.

    Attributes:
        icon: Material icon name (e.g., 'waving_hand', 'settings').
        label: Display label for the navigation item.
        target: URL path or external URL for the link.
        marker: Test marker for the item. Auto-generated from label if None.
        new_tab: Whether to open the link in a new tab. Defaults to False (same tab).
    """

    icon: str
    label: str
    target: str
    marker: str | None = None
    new_tab: bool = False

    def __post_init__(self) -> None:
        """Auto-generate marker from label if not provided."""
        if self.marker is None:
            self.marker = "LINK_" + self.label.upper().replace(" ", "_").replace("(", "").replace(")", "")


@dataclass
class NavGroup:
    """Group of navigation items from a NavBuilder.

    Used internally for rendering navigation in the sidebar.

    Attributes:
        name: Display name for the navigation group.
        icon: Material icon name for the group. Defaults to 'folder'.
        items: Navigation items in this group.
        position: Sort position in sidebar (lower = higher). Defaults to 1000.
        use_expansion: Whether to render items in an expansion panel. Defaults to True.
    """

    name: str
    icon: str = "folder"
    items: list[NavItem] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    position: int = 1000
    use_expansion: bool = True


class BaseNavBuilder(ABC):
    """Base class for navigation builders.

    Each module should have ONE NavBuilder that defines its navigation items.
    NavBuilders are auto-discovered and used to populate the sidebar.

    Example:
        class NavBuilder(BaseNavBuilder):
            @staticmethod
            def get_nav_name() -> str:
                return "My Module"

            @staticmethod
            def get_nav_items() -> list[NavItem]:
                return [
                    NavItem(icon="home", label="Home", target="/my-module"),
                    NavItem(icon="settings", label="Settings", target="/my-module/settings"),
                ]

            @staticmethod
            def get_nav_position() -> int:
                return 200
    """

    @staticmethod
    @abstractmethod
    def get_nav_name() -> str:
        """Return the display name for this module's navigation group.

        Returns:
            Display name shown in sidebar (e.g., 'Hello World', 'System').
        """

    @staticmethod
    @abstractmethod
    def get_nav_items() -> list[NavItem]:
        """Return navigation items for the sidebar.

        Returns:
            Navigation items for this module.
        """

    @staticmethod
    def get_nav_position() -> int:
        """Return position in sidebar (lower = higher). Defaults to 1000.

        Returns:
            Position value.
        """
        return 1000

    @staticmethod
    def get_nav_icon() -> str:
        """Return the icon for the navigation group expansion panel. Defaults to 'folder'.

        Returns:
            Material icon name.
        """
        return "folder"

    @staticmethod
    def get_nav_use_expansion() -> bool:
        """Return whether to render items in an expansion panel. Defaults to True.

        Returns:
            True to render items in a collapsible expansion panel.
        """
        return True


def gui_get_nav_groups(*, context: FoundryContext | None = None) -> list[NavGroup]:
    """Collect navigation groups from all NavBuilders.

    Args:
        context: Project context used for NavBuilder discovery.  When ``None``,
            the global context installed via
            :func:`aignostics_foundry_core.foundry.set_context` is used.

    Returns:
        Navigation groups sorted by position (lower = higher in sidebar).
    """
    nav_builders = locate_subclasses(BaseNavBuilder, context=context or get_context())
    groups: list[NavGroup] = []

    for nav_builder in nav_builders:
        items: list[NavItem] = nav_builder.get_nav_items()  # pyright: ignore[reportUnknownMemberType]
        if items:
            groups.append(
                NavGroup(
                    name=nav_builder.get_nav_name(),
                    icon=nav_builder.get_nav_icon(),
                    items=items,
                    position=nav_builder.get_nav_position(),
                    use_expansion=nav_builder.get_nav_use_expansion(),
                )
            )

    return sorted(groups, key=lambda g: g.position)
