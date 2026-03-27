"""Dependency injection using dynamic import and discovery of implementations and subclasses."""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from importlib.metadata import entry_points
from inspect import isclass
from typing import TYPE_CHECKING, Any

from aignostics_foundry_core.foundry import get_context

if TYPE_CHECKING:
    from collections.abc import Callable

    from aignostics_foundry_core.foundry import FoundryContext

_implementation_cache: dict[tuple[Any, str], list[Any]] = {}
_subclass_cache: dict[tuple[Any, str], list[Any]] = {}

PLUGIN_ENTRY_POINT_GROUP = "aignostics.plugins"


@lru_cache(maxsize=1)
def discover_plugin_packages() -> tuple[str, ...]:
    """Discover plugin packages using entry points.

    Plugins register themselves in their pyproject.toml:

        [project.entry-points."aignostics.plugins"]
        my_plugin = "my_plugin"

    Results are cached after the first call.

    Returns:
        Tuple of discovered plugin package names.
    """
    eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
    return tuple(ep.value for ep in eps)


def load_modules(*, context: FoundryContext | None = None) -> None:
    """Import all top-level submodules of the configured project package.

    Args:
        context: Project context supplying the package name.  When ``None``,
            the global context installed via :func:`aignostics_foundry_core.foundry.set_context`
            is used; :func:`~aignostics_foundry_core.foundry.get_context` raises
            ``RuntimeError`` if no context has been configured.
    """
    ctx = context or get_context()
    package = importlib.import_module(ctx.name)
    for _, name, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{ctx.name}.{name}")


def _scan_packages_deep(
    package_name: str,
    predicate: Callable[[Any], bool],
) -> list[Any]:
    """Deep-scan a single package by walking all submodules via pkgutil.iter_modules.

    Used for the main project package. Imports each submodule discovered via
    ``pkgutil.iter_modules`` and examines every name in ``dir(module)`` against
    *predicate*. Silently skips submodules that raise ``ImportError``.

    Args:
        package_name: The package to scan (e.g. ``"bridge"``).
        predicate: Called with each member; members where this returns ``True``
            are included in the result.

    Returns:
        All members from submodules of *package_name* that satisfy *predicate*.
    """
    results: list[Any] = []
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        return results
    for _, name, _ in pkgutil.iter_modules(package.__path__):
        try:
            module = importlib.import_module(f"{package_name}.{name}")
            for member_name in dir(module):
                member = getattr(module, member_name)
                if predicate(member):
                    results.append(member)
        except ImportError:
            continue
    return results


def _scan_packages_shallow(
    package_names: tuple[str, ...],
    predicate: Callable[[Any], bool],
) -> list[Any]:
    """Shallow-scan the top-level exports of each plugin package.

    For each plugin package, imports only the top-level package and examines
    ``dir(package)`` for matches. Does **not** walk submodules via
    ``pkgutil.iter_modules``.

    This prevents nested objects from plugin submodules (e.g.
    ``stargate.demeter.cli``) from being discovered alongside the intended
    top-level export (``stargate.cli``). Only what the plugin's ``__init__.py``
    explicitly exports is considered.

    Silently skips packages that raise ``ImportError``.

    Args:
        package_names: Plugin package names to scan.
        predicate: Called with each member; members where this returns ``True``
            are included in the result.

    Returns:
        All members from the top-level namespace of each plugin that satisfy
        *predicate*.
    """
    results: list[Any] = []
    for package_name in package_names:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            continue
        for member_name in dir(package):
            member = getattr(package, member_name)
            if predicate(member):
                results.append(member)
    return results


def locate_implementations(_class: type[Any], *, context: FoundryContext | None = None) -> list[Any]:
    """Dynamically discover all instances of some class.

    Searches plugin top-level exports first (shallow scan), then deep-scans all
    submodules of the main project package. Plugins are registered via entry
    points; only their top-level ``__init__.py`` exports are examined (submodules
    are not walked). The main package retains full deep-scan behaviour.

    Cache keys include the context name to avoid cross-project cache pollution
    when multiple projects share this library.

    Args:
        _class: Class to search for.
        context: Project context supplying the package name.  When ``None``,
            the global context installed via :func:`aignostics_foundry_core.foundry.set_context`
            is used; :func:`~aignostics_foundry_core.foundry.get_context` raises
            ``RuntimeError`` if no context has been configured.

    Returns:
        List of discovered instances of the given class.
    """
    ctx = context or get_context()
    cache_key = (_class, ctx.name)
    if cache_key in _implementation_cache:
        return _implementation_cache[cache_key]

    def predicate(member: object) -> bool:
        return isinstance(member, _class)

    results = [
        *_scan_packages_shallow(discover_plugin_packages(), predicate),
        *_scan_packages_deep(ctx.name, predicate),
    ]
    _implementation_cache[cache_key] = results
    return results


def locate_subclasses(_class: type[Any], *, context: FoundryContext | None = None) -> list[Any]:
    """Dynamically discover all classes that are subclasses of some type.

    Searches plugin top-level exports first (shallow scan), then deep-scans all
    submodules of the main project package. Plugins are registered via entry
    points; only their top-level ``__init__.py`` exports are examined (submodules
    are not walked). The main package retains full deep-scan behaviour.

    Cache keys include the context name to avoid cross-project cache pollution
    when multiple projects share this library.

    Args:
        _class: Parent class of subclasses to search for.
        context: Project context supplying the package name.  When ``None``,
            the global context installed via :func:`aignostics_foundry_core.foundry.set_context`
            is used; :func:`~aignostics_foundry_core.foundry.get_context` raises
            ``RuntimeError`` if no context has been configured.

    Returns:
        List of discovered subclasses of the given class.
    """
    ctx = context or get_context()
    cache_key = (_class, ctx.name)
    if cache_key in _subclass_cache:
        return _subclass_cache[cache_key]

    def predicate(member: object) -> bool:
        return isclass(member) and issubclass(member, _class) and member != _class

    results = [
        *_scan_packages_shallow(discover_plugin_packages(), predicate),
        *_scan_packages_deep(ctx.name, predicate),
    ]
    _subclass_cache[cache_key] = results
    return results


def clear_caches() -> None:
    """Reset all module-level discovery caches.

    Clears ``_implementation_cache``, ``_subclass_cache``, and the
    ``discover_plugin_packages`` LRU cache so that subsequent calls to
    ``locate_implementations``, ``locate_subclasses``, and
    ``discover_plugin_packages`` perform fresh discovery.
    """
    _implementation_cache.clear()
    _subclass_cache.clear()
    discover_plugin_packages.cache_clear()
