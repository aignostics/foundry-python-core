"""Tests for service module — BaseService behaviour."""

from typing import Any

import pytest
from pydantic_settings import BaseSettings

from aignostics_foundry_core.health import Health, HealthStatus
from aignostics_foundry_core.service import BaseService


class _MinimalSettings(BaseSettings):
    """Minimal settings class with no required fields for testing."""


class _ConcreteService(BaseService):
    """Minimal concrete subclass for testing."""

    async def health(self) -> Health:
        return Health(status=HealthStatus.UP)

    async def info(self, mask_secrets: bool = True) -> dict[str, Any]:
        return {}


class _AnotherService(BaseService):
    """Second concrete subclass to verify per-class isolation."""

    async def health(self) -> Health:
        return Health(status=HealthStatus.UP)

    async def info(self, mask_secrets: bool = True) -> dict[str, Any]:
        return {}


class TestGetService:
    """Tests for BaseService.get_service() factory."""

    @pytest.mark.unit
    def test_get_service_returns_callable(self) -> None:
        """get_service() returns a callable dependency."""
        dep = _ConcreteService.get_service()
        assert callable(dep)

    @pytest.mark.unit
    def test_get_service_is_cached_per_class(self) -> None:
        """Two calls to get_service() on the same class return the identical object."""
        dep_first = _ConcreteService.get_service()
        dep_second = _ConcreteService.get_service()
        assert dep_first is dep_second

    @pytest.mark.unit
    def test_get_service_different_classes_return_different_callables(self) -> None:
        """Two distinct subclasses get distinct dependency callables."""
        dep_a = _ConcreteService.get_service()
        dep_b = _AnotherService.get_service()
        assert dep_a is not dep_b

    @pytest.mark.unit
    def test_get_service_dependency_yields_service_instance(self) -> None:
        """The returned callable, when called, yields an instance of the subclass."""
        dep = _ConcreteService.get_service()
        gen = dep()
        instance = next(gen)
        assert isinstance(instance, _ConcreteService)


class TestKey:
    """Tests for BaseService.key()."""

    @pytest.mark.unit
    def test_service_key_returns_module_component(self) -> None:
        """key() returns a component of __module__ — the second-to-last segment."""
        service = _ConcreteService()
        # Module is something like "tests.aignostics_foundry_core.service_test"
        # key() returns the second-to-last segment
        expected = service.__module__.split(".")[-2]
        assert service.key() == expected
        assert len(service.key()) > 0


class TestSettings:
    """Tests for BaseService settings injection and accessor."""

    @pytest.mark.unit
    def test_service_with_settings_class_loads_settings(self) -> None:
        """settings() returns a BaseSettings instance when settings_class is provided."""

        class _ServiceWithSettings(BaseService):
            def __init__(self) -> None:
                super().__init__(settings_class=_MinimalSettings)

            async def health(self) -> Health:
                return Health(status=HealthStatus.UP)

            async def info(self, mask_secrets: bool = True) -> dict[str, Any]:
                return {}

        service = _ServiceWithSettings()
        result = service.settings()
        assert isinstance(result, BaseSettings)


class TestAbstractEnforcement:
    """Tests that BaseService enforces abstract method contracts."""

    @pytest.mark.unit
    def test_health_and_info_are_abstract(self) -> None:
        """Cannot instantiate BaseService directly — raises TypeError."""
        with pytest.raises(TypeError):
            BaseService()  # type: ignore[abstract]
