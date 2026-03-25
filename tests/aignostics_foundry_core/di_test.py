"""Tests for the dependency injection module."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import MagicMock, Mock, patch

import pytest

from aignostics_foundry_core import di

# Constants to avoid duplication (SonarQube S1192)
MAIN_PKG = "my_project"
PLUGIN = "plugin"
MYMODULE = "mymodule"
PLUGIN_MYMODULE = f"{PLUGIN}.{MYMODULE}"
MAIN_PKG_MYMODULE = f"{MAIN_PKG}.{MYMODULE}"
PLUGIN_ONE = "plugin_one"
PLUGIN_TWO = "plugin_two"
CACHED_PLUGIN = "cached_plugin"


class _DummyBase:
    """Base class for DI discovery tests."""


def _mock_package() -> MagicMock:
    """Return a MagicMock that looks like an importable package (has __path__)."""
    pkg = MagicMock()
    pkg.__path__ = ["/fake/path"]
    return pkg


def _make_import_side_effect(
    mapping: dict[str, ModuleType | Exception],
    default: MagicMock | None = None,
) -> Callable[[str], ModuleType]:
    """Return an import side-effect callable driven by *mapping*.

    Args:
        mapping: Maps module name to the module to return or an exception to raise.
        default: Returned for any name not in *mapping*.  Defaults to a package
            with an empty ``__path__``.

    Returns:
        A callable suitable for use as ``importlib.import_module``'s side effect.
    """
    if default is None:
        default = _mock_package()
        default.__path__ = []

    def _side_effect(name: str) -> ModuleType:
        if name in mapping:
            result = mapping[name]
            if isinstance(result, BaseException):
                raise result
            return result  # type: ignore[return-value]
        return default  # type: ignore[return-value]

    return _side_effect


@contextmanager
def _broken_plugin_package_patches(
    main_pkg: MagicMock,
    main_mod: ModuleType,
) -> Generator[None, None, None]:
    """Yield patches where a plugin package itself raises ImportError.

    The plugin package raises ``ImportError`` on import.  The main project
    package and its ``MYMODULE`` submodule import normally.

    Args:
        main_pkg: Mock main package (has ``__path__``).
        main_mod: Module to return for the main ``MYMODULE`` import.
    """
    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: ImportError("broken"),
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        yield


@contextmanager
def _no_match_plugin_patches(
    plugin_pkg: MagicMock,
    main_pkg: MagicMock,
    main_mod: ModuleType,
) -> Generator[None, None, None]:
    """Yield patches where a plugin imports successfully but has no matching top-level members.

    The plugin package is importable but its top-level namespace contains no
    members that satisfy the discovery predicate.  The main project package and
    its ``MYMODULE`` submodule import normally and contain the expected member.

    Args:
        plugin_pkg: Mock plugin package (importable, no matching members).
        main_pkg: Mock main package (has ``__path__``).
        main_mod: Module to return for the main ``MYMODULE`` import.
    """
    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: plugin_pkg,
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        yield


@pytest.fixture
def clear_caches() -> Generator[None, None, None]:
    """Clear DI caches before and after each test."""
    di.clear_caches()
    yield
    di.clear_caches()


# ---------------------------------------------------------------------------
# discover_plugin_packages
# ---------------------------------------------------------------------------


@pytest.mark.unit
@patch("aignostics_foundry_core.di.entry_points")
def test_discover_plugin_packages_extracts_values_from_entry_points(
    mock_entry_points: Mock, clear_caches: None
) -> None:
    """Test that discover_plugin_packages extracts values from entry points."""
    mock_ep1, mock_ep2 = MagicMock(), MagicMock()
    mock_ep1.value = PLUGIN_ONE
    mock_ep2.value = PLUGIN_TWO
    mock_entry_points.return_value = [mock_ep1, mock_ep2]

    result = di.discover_plugin_packages()

    mock_entry_points.assert_called_once_with(group=di.PLUGIN_ENTRY_POINT_GROUP)
    assert result == (PLUGIN_ONE, PLUGIN_TWO)


@pytest.mark.unit
@patch("aignostics_foundry_core.di.entry_points")
def test_discover_plugin_packages_returns_empty_tuple_when_no_plugins(
    mock_entry_points: Mock, clear_caches: None
) -> None:
    """Test that discover_plugin_packages returns empty tuple when no plugins registered."""
    mock_entry_points.return_value = []
    assert di.discover_plugin_packages() == ()


@pytest.mark.unit
@patch("aignostics_foundry_core.di.entry_points")
def test_discover_plugin_packages_is_cached(mock_entry_points: Mock, clear_caches: None) -> None:
    """Test that discover_plugin_packages caches results (entry_points called once)."""
    mock_ep = MagicMock()
    mock_ep.value = CACHED_PLUGIN
    mock_entry_points.return_value = [mock_ep]

    result1 = di.discover_plugin_packages()
    result2 = di.discover_plugin_packages()

    assert mock_entry_points.call_count == 1
    assert result1 == result2 == (CACHED_PLUGIN,)


# ---------------------------------------------------------------------------
# load_modules
# ---------------------------------------------------------------------------

SUBMOD_A = "submod_a"
SUBMOD_B = "submod_b"


@pytest.mark.unit
def test_load_modules_imports_the_package_itself() -> None:
    """load_modules imports the top-level package before iterating submodules."""
    pkg = _mock_package()
    with (
        patch.object(di.importlib, "import_module", return_value=pkg) as mock_import,
        patch.object(di.pkgutil, "iter_modules", return_value=[]),
    ):
        di.load_modules(MAIN_PKG)

    mock_import.assert_any_call(MAIN_PKG)


@pytest.mark.unit
def test_load_modules_imports_each_top_level_submodule() -> None:
    """load_modules imports each submodule returned by pkgutil.iter_modules."""
    pkg = _mock_package()
    with (
        patch.object(di.importlib, "import_module", return_value=pkg) as mock_import,
        patch.object(
            di.pkgutil,
            "iter_modules",
            return_value=[("", SUBMOD_A, False), ("", SUBMOD_B, False)],
        ),
    ):
        di.load_modules(MAIN_PKG)

    mock_import.assert_any_call(f"{MAIN_PKG}.{SUBMOD_A}")
    mock_import.assert_any_call(f"{MAIN_PKG}.{SUBMOD_B}")


# ---------------------------------------------------------------------------
# locate_implementations — plugin discovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_locate_implementations_searches_plugins(clear_caches: None) -> None:
    """Test that locate_implementations finds instances exported by a plugin's top-level __init__.py."""
    plugin_instance = _DummyBase()
    plugin_pkg = _mock_package()
    plugin_pkg.plugin_instance = plugin_instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({PLUGIN: plugin_pkg}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert plugin_instance in result


@pytest.mark.unit
def test_locate_implementations_only_finds_plugin_top_level_exports(clear_caches: None) -> None:
    """Plugin submodule instances are not discovered; only top-level __init__.py exports are found."""
    top_instance = _DummyBase()
    sub_instance = _DummyBase()

    plugin_pkg = _mock_package()
    plugin_pkg.top_instance = top_instance  # type: ignore[attr-defined]

    plugin_submod = ModuleType(f"{PLUGIN}.submod")
    plugin_submod.sub_instance = sub_instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: plugin_pkg,
                f"{PLUGIN}.submod": plugin_submod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert top_instance in result
    assert sub_instance not in result


@pytest.mark.unit
def test_locate_implementations_handles_broken_plugin_package(clear_caches: None) -> None:
    """Test that a plugin package raising ImportError on import is skipped; main package still searched."""
    main_instance = _DummyBase()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.main_instance = main_instance  # type: ignore[attr-defined]

    with _broken_plugin_package_patches(main_pkg, main_mod):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert main_instance in result


@pytest.mark.unit
def test_locate_implementations_handles_plugin_with_no_matching_top_level_members(clear_caches: None) -> None:
    """Test that a plugin with no matching top-level exports is skipped; main package still searched."""
    main_instance = _DummyBase()
    plugin_pkg = _mock_package()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.main_instance = main_instance  # type: ignore[attr-defined]

    with _no_match_plugin_patches(plugin_pkg, main_pkg, main_mod):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert main_instance in result


@pytest.mark.unit
def test_locate_implementations_deep_scans_main_package(clear_caches: None) -> None:
    """Main package submodule instances are found via deep scan even when a plugin is present."""
    main_instance = _DummyBase()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.main_instance = main_instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert main_instance in result


# ---------------------------------------------------------------------------
# locate_subclasses — plugin discovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_locate_subclasses_searches_plugins(clear_caches: None) -> None:
    """Test that locate_subclasses finds subclasses exported by a plugin's top-level __init__.py."""

    class PluginSub(_DummyBase):
        pass

    plugin_pkg = _mock_package()
    plugin_pkg.PluginSub = PluginSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({PLUGIN: plugin_pkg}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert PluginSub in result


@pytest.mark.unit
def test_locate_subclasses_only_finds_plugin_top_level_exports(clear_caches: None) -> None:
    """Plugin subclasses only in submodules are not discovered; only top-level __init__.py exports are found."""

    class TopSub(_DummyBase):
        pass

    class SubSub(_DummyBase):
        pass

    plugin_pkg = _mock_package()
    plugin_pkg.TopSub = TopSub  # type: ignore[attr-defined]

    plugin_submod = ModuleType(f"{PLUGIN}.submod")
    plugin_submod.SubSub = SubSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: plugin_pkg,
                f"{PLUGIN}.submod": plugin_submod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert TopSub in result
    assert SubSub not in result


@pytest.mark.unit
def test_locate_subclasses_handles_broken_plugin_package(clear_caches: None) -> None:
    """Test that a plugin package raising ImportError on import is skipped; main package still searched."""

    class MainSub(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.MainSub = MainSub  # type: ignore[attr-defined]

    with _broken_plugin_package_patches(main_pkg, main_mod):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert MainSub in result


@pytest.mark.unit
def test_locate_subclasses_handles_plugin_with_no_matching_top_level_members(clear_caches: None) -> None:
    """Test that a plugin with no matching top-level exports is skipped; main package still searched."""

    class MainSub(_DummyBase):
        pass

    plugin_pkg = _mock_package()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.MainSub = MainSub  # type: ignore[attr-defined]

    with _no_match_plugin_patches(plugin_pkg, main_pkg, main_mod):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert MainSub in result


@pytest.mark.unit
def test_locate_subclasses_deep_scans_main_package(clear_caches: None) -> None:
    """Main package subclasses in submodules are found via deep scan."""

    class MainSub(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.MainSub = MainSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert MainSub in result


# ---------------------------------------------------------------------------
# No-plugins backward-compatibility
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_locate_implementations_no_plugins_detects_main_package(clear_caches: None) -> None:
    """With no plugins, locate_implementations finds instances in the main package."""
    instance = _DummyBase()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.instance = instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert instance in result


@pytest.mark.unit
def test_locate_subclasses_no_plugins_detects_main_package(clear_caches: None) -> None:
    """With no plugins, locate_subclasses finds subclasses in the main package."""

    class LocalSub(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.LocalSub = LocalSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert LocalSub in result


# ---------------------------------------------------------------------------
# clear_caches
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clear_caches_resets_implementation_cache() -> None:
    """Calling clear_caches() causes locate_implementations to re-run discovery."""
    main_pkg = _mock_package()
    main_mod_v1 = ModuleType(MAIN_PKG_MYMODULE)
    instance_v1 = _DummyBase()
    main_mod_v1.instance = instance_v1  # type: ignore[attr-defined]

    # First call — populates cache
    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({MAIN_PKG: main_pkg, MAIN_PKG_MYMODULE: main_mod_v1}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_before = di.locate_implementations(_DummyBase, MAIN_PKG)
    assert instance_v1 in result_before

    di.clear_caches()

    # Second call after clear — different module, different instance
    main_mod_v2 = ModuleType(MAIN_PKG_MYMODULE)
    instance_v2 = _DummyBase()
    main_mod_v2.instance = instance_v2  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({MAIN_PKG: main_pkg, MAIN_PKG_MYMODULE: main_mod_v2}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_after = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert instance_v2 in result_after
    assert instance_v1 not in result_after


@pytest.mark.unit
def test_clear_caches_resets_subclass_cache() -> None:
    """Calling clear_caches() causes locate_subclasses to re-run discovery."""

    class SubV1(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod_v1 = ModuleType(MAIN_PKG_MYMODULE)
    main_mod_v1.SubV1 = SubV1  # type: ignore[attr-defined]

    # First call — populates cache
    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({MAIN_PKG: main_pkg, MAIN_PKG_MYMODULE: main_mod_v1}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_before = di.locate_subclasses(_DummyBase, MAIN_PKG)
    assert SubV1 in result_before

    di.clear_caches()

    class SubV2(_DummyBase):
        pass

    main_mod_v2 = ModuleType(MAIN_PKG_MYMODULE)
    main_mod_v2.SubV2 = SubV2  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({MAIN_PKG: main_pkg, MAIN_PKG_MYMODULE: main_mod_v2}),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_after = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert SubV2 in result_after
    assert SubV1 not in result_after


# ---------------------------------------------------------------------------
# Caching — locate_implementations and locate_subclasses
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_locate_implementations_caches_result_on_second_call(clear_caches: None) -> None:
    """locate_implementations returns cached result on second call without re-scanning."""
    instance = _DummyBase()
    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.instance = instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]) as mock_iter,
    ):
        di.locate_implementations(_DummyBase, MAIN_PKG)
        di.locate_implementations(_DummyBase, MAIN_PKG)

    assert mock_iter.call_count == 1


@pytest.mark.unit
def test_locate_subclasses_caches_result_on_second_call(clear_caches: None) -> None:
    """locate_subclasses returns cached result on second call without re-scanning."""

    class LocalSub(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.LocalSub = LocalSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]) as mock_iter,
    ):
        di.locate_subclasses(_DummyBase, MAIN_PKG)
        di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert mock_iter.call_count == 1


@pytest.mark.unit
@patch("aignostics_foundry_core.di.entry_points")
def test_clear_caches_resets_discover_plugin_packages_cache(mock_entry_points: Mock) -> None:
    """Calling clear_caches() causes discover_plugin_packages to call entry_points again."""
    mock_ep = MagicMock()
    mock_ep.value = CACHED_PLUGIN
    mock_entry_points.return_value = [mock_ep]

    # Warm the cache
    di.clear_caches()
    di.discover_plugin_packages()
    assert mock_entry_points.call_count == 1

    # After clear, entry_points is called again
    di.clear_caches()
    di.discover_plugin_packages()
    assert mock_entry_points.call_count == 2


# ---------------------------------------------------------------------------
# Edge cases and isolation
# ---------------------------------------------------------------------------

PROJ_A = "proj_a"
PROJ_B = "proj_b"


@pytest.mark.unit
def test_locate_subclasses_excludes_base_class_from_results(clear_caches: None) -> None:
    """locate_subclasses never includes the base class itself in results."""

    class LocalSub(_DummyBase):
        pass

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod._DummyBase = _DummyBase  # type: ignore[attr-defined]
    main_mod.LocalSub = LocalSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert LocalSub in result
    assert _DummyBase not in result


@pytest.mark.unit
def test_locate_implementations_handles_broken_main_package_submodule(clear_caches: None) -> None:
    """locate_implementations succeeds when a main-package submodule raises ImportError."""
    main_pkg = _mock_package()

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: ImportError("broken submodule"),
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert result == []


@pytest.mark.unit
def test_locate_subclasses_handles_broken_main_package_submodule(clear_caches: None) -> None:
    """locate_subclasses succeeds when a main-package submodule raises ImportError."""
    main_pkg = _mock_package()

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: ImportError("broken submodule"),
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert result == []


@pytest.mark.unit
def test_locate_implementations_combines_plugin_and_main_package_results(clear_caches: None) -> None:
    """locate_implementations returns instances from both plugin and main package."""
    plugin_instance = _DummyBase()
    main_instance = _DummyBase()

    plugin_pkg = _mock_package()
    plugin_pkg.plugin_instance = plugin_instance  # type: ignore[attr-defined]

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.main_instance = main_instance  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: plugin_pkg,
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_implementations(_DummyBase, MAIN_PKG)

    assert plugin_instance in result
    assert main_instance in result


@pytest.mark.unit
def test_locate_subclasses_combines_plugin_and_main_package_results(clear_caches: None) -> None:
    """locate_subclasses returns subclasses from both plugin and main package."""

    class PluginSub(_DummyBase):
        pass

    class MainSub(_DummyBase):
        pass

    plugin_pkg = _mock_package()
    plugin_pkg.PluginSub = PluginSub  # type: ignore[attr-defined]

    main_pkg = _mock_package()
    main_mod = ModuleType(MAIN_PKG_MYMODULE)
    main_mod.MainSub = MainSub  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=(PLUGIN,)),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PLUGIN: plugin_pkg,
                MAIN_PKG: main_pkg,
                MAIN_PKG_MYMODULE: main_mod,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result = di.locate_subclasses(_DummyBase, MAIN_PKG)

    assert PluginSub in result
    assert MainSub in result


@pytest.mark.unit
def test_locate_implementations_cache_isolated_by_project_name(clear_caches: None) -> None:
    """locate_implementations uses independent cache entries per project_name."""
    instance_a = _DummyBase()
    instance_b = _DummyBase()

    pkg_a = _mock_package()
    mod_a = ModuleType(f"{PROJ_A}.{MYMODULE}")
    mod_a.instance_a = instance_a  # type: ignore[attr-defined]

    pkg_b = _mock_package()
    mod_b = ModuleType(f"{PROJ_B}.{MYMODULE}")
    mod_b.instance_b = instance_b  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PROJ_A: pkg_a,
                f"{PROJ_A}.{MYMODULE}": mod_a,
                PROJ_B: pkg_b,
                f"{PROJ_B}.{MYMODULE}": mod_b,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_a = di.locate_implementations(_DummyBase, PROJ_A)
        result_b = di.locate_implementations(_DummyBase, PROJ_B)

    assert instance_a in result_a
    assert instance_b not in result_a
    assert instance_b in result_b
    assert instance_a not in result_b


@pytest.mark.unit
def test_locate_subclasses_cache_isolated_by_project_name(clear_caches: None) -> None:
    """locate_subclasses uses independent cache entries per project_name."""

    class SubA(_DummyBase):
        pass

    class SubB(_DummyBase):
        pass

    pkg_a = _mock_package()
    mod_a = ModuleType(f"{PROJ_A}.{MYMODULE}")
    mod_a.SubA = SubA  # type: ignore[attr-defined]

    pkg_b = _mock_package()
    mod_b = ModuleType(f"{PROJ_B}.{MYMODULE}")
    mod_b.SubB = SubB  # type: ignore[attr-defined]

    with (
        patch.object(di, "discover_plugin_packages", return_value=()),
        patch.object(
            di.importlib,
            "import_module",
            side_effect=_make_import_side_effect({
                PROJ_A: pkg_a,
                f"{PROJ_A}.{MYMODULE}": mod_a,
                PROJ_B: pkg_b,
                f"{PROJ_B}.{MYMODULE}": mod_b,
            }),
        ),
        patch.object(di.pkgutil, "iter_modules", return_value=[("", MYMODULE, False)]),
    ):
        result_a = di.locate_subclasses(_DummyBase, PROJ_A)
        result_b = di.locate_subclasses(_DummyBase, PROJ_B)

    assert SubA in result_a
    assert SubB not in result_a
    assert SubB in result_b
    assert SubA not in result_b
