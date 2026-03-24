"""Tests for health models and status definitions."""

import pytest

from aignostics_foundry_core.health import Health, HealthStatus

# Test constants
DB_FAILURE = "DB failure"
SLOW_QUERIES = "Slow queries"
PARTIAL_OUTAGE = "Partial outage"
CACHE_FAILURE = "Cache failure"
ORIGINAL_FAILURE = "Original failure"
AUTH_ERROR = "Auth error"
DEEP_FAILURE = "Deep failure"
SERVICE_UNAVAILABLE = "Service unavailable"


class TestHealth:
    """Test cases for the Health model and HealthStatus enum."""

    @pytest.mark.unit
    def test_degraded_status_requires_reason(self) -> None:
        """Test that DEGRADED status requires a reason."""
        health = Health(status=HealthStatus.DEGRADED, reason=PARTIAL_OUTAGE)
        assert health.status == HealthStatus.DEGRADED
        assert health.reason == PARTIAL_OUTAGE

        with pytest.raises(ValueError, match="Health DEGRADED must have a reason"):
            Health(status=HealthStatus.DEGRADED)

    @pytest.mark.unit
    def test_down_status_requires_reason(self) -> None:
        """Test that DOWN status requires a reason."""
        health = Health(status=HealthStatus.DOWN, reason="Database connection failed")
        assert health.status == HealthStatus.DOWN
        assert health.reason == "Database connection failed"

        with pytest.raises(ValueError, match="Health DOWN must have a reason"):
            Health(status=HealthStatus.DOWN)

    @pytest.mark.unit
    def test_up_status_must_not_have_reason(self) -> None:
        """Test that UP status cannot have a reason."""
        with pytest.raises(ValueError, match="Health UP must not have reason"):
            Health(status=HealthStatus.UP, reason="This should not be allowed")

    @pytest.mark.unit
    def test_str_up(self) -> None:
        """Test string representation of UP health status."""
        health = Health(status=HealthStatus.UP)
        assert str(health) == "UP"

    @pytest.mark.unit
    def test_str_degraded(self) -> None:
        """Test string representation of DEGRADED health status."""
        health = Health(status=HealthStatus.DEGRADED, reason="Some issues")
        assert str(health) == "DEGRADED: Some issues"

    @pytest.mark.unit
    def test_str_down(self) -> None:
        """Test string representation of DOWN health status."""
        health = Health(status=HealthStatus.DOWN, reason=SERVICE_UNAVAILABLE)
        assert str(health) == f"DOWN: {SERVICE_UNAVAILABLE}"

    @pytest.mark.unit
    def test_bool_up_is_true(self) -> None:
        """Test that UP health status evaluates to True."""
        health = Health(status=HealthStatus.UP)
        assert bool(health) is True

    @pytest.mark.unit
    def test_bool_down_is_false(self) -> None:
        """Test that DOWN health status evaluates to False."""
        health = Health(status=HealthStatus.DOWN, reason=SERVICE_UNAVAILABLE)
        assert bool(health) is False

    @pytest.mark.unit
    def test_compute_no_components_unchanged(self) -> None:
        """Test that health status is unchanged when there are no components."""
        health = Health(status=HealthStatus.UP)
        result = health.compute_health_from_components()

        assert result.status == HealthStatus.UP
        assert result.reason is None
        assert result is health

    @pytest.mark.unit
    def test_compute_single_degraded_component(self) -> None:
        """Test that health becomes DEGRADED when a single component is DEGRADED."""
        health = Health(status=HealthStatus.UP)
        health.components = {
            "database": Health(status=HealthStatus.DEGRADED, reason=SLOW_QUERIES),
            "cache": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DEGRADED
        assert result.reason == f"Component 'database' is DEGRADED ({SLOW_QUERIES})"
        assert result is health

    @pytest.mark.unit
    def test_compute_multiple_degraded_components(self) -> None:
        """Test that health becomes DEGRADED with correct reason when multiple components are DEGRADED."""
        health = Health(status=HealthStatus.UP)
        health.components = {
            "database": Health(status=HealthStatus.DEGRADED, reason=SLOW_QUERIES),
            "cache": Health(status=HealthStatus.DEGRADED, reason="Eviction lag"),
            "api": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DEGRADED
        assert result.reason is not None
        assert "Components 'database' (Slow queries), 'cache' (Eviction lag) are DEGRADED" in result.reason
        assert result is health

    @pytest.mark.unit
    def test_compute_single_down_component(self) -> None:
        """Test that health becomes DOWN when a single component is DOWN."""
        health = Health(status=HealthStatus.UP)
        health.components = {
            "database": Health(status=HealthStatus.DOWN, reason=DB_FAILURE),
            "cache": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DOWN
        assert result.reason == f"Component 'database' is DOWN ({DB_FAILURE})"
        assert result is health

    @pytest.mark.unit
    def test_compute_multiple_down_components(self) -> None:
        """Test that health becomes DOWN with correct reason when multiple components are DOWN."""
        health = Health(status=HealthStatus.UP)
        health.components = {
            "database": Health(status=HealthStatus.DOWN, reason=DB_FAILURE),
            "cache": Health(status=HealthStatus.DOWN, reason=CACHE_FAILURE),
            "api": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DOWN
        assert result.reason is not None
        assert "Components '" in result.reason
        assert "database" in result.reason
        assert "cache" in result.reason
        assert "are DOWN" in result.reason
        assert result is health

    @pytest.mark.unit
    def test_compute_down_trumps_degraded(self) -> None:
        """Test that DOWN status takes precedence over DEGRADED in health aggregation."""
        health = Health(status=HealthStatus.UP)
        health.components = {
            "database": Health(status=HealthStatus.DEGRADED, reason=SLOW_QUERIES),
            "cache": Health(status=HealthStatus.DOWN, reason=CACHE_FAILURE),
            "api": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DOWN
        assert result.reason is not None
        assert "Component 'cache' is DOWN" in result.reason
        assert result is health

    @pytest.mark.unit
    def test_compute_already_down_preserved(self) -> None:
        """Test that pre-existing DOWN reason is not overwritten when already DOWN."""
        health = Health(status=HealthStatus.DOWN, reason=ORIGINAL_FAILURE)
        health.components = {
            "database": Health(status=HealthStatus.DOWN, reason=DB_FAILURE),
            "cache": Health(status=HealthStatus.UP),
        }

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DOWN
        assert result.reason == ORIGINAL_FAILURE
        assert result is health

    @pytest.mark.unit
    def test_compute_recursive(self) -> None:
        """Test that DOWN propagates recursively through a multi-level component tree."""
        deep_component = Health(status=HealthStatus.DOWN, reason=DEEP_FAILURE)
        mid_component = Health(
            status=HealthStatus.UP,
            components={"deep": deep_component},
        )
        health = Health(
            status=HealthStatus.UP,
            components={"mid": mid_component, "other": Health(status=HealthStatus.UP)},
        )

        result = health.compute_health_from_components()

        assert result.status == HealthStatus.DOWN
        assert result.reason is not None
        assert "Component 'mid' is DOWN" in result.reason
        assert health.components["mid"].status == HealthStatus.DOWN
        assert health.components["mid"].reason is not None
        assert "Component 'deep' is DOWN" in health.components["mid"].reason
        assert health.components["other"].status == HealthStatus.UP

    @pytest.mark.unit
    def test_validate_integration(self) -> None:
        """Test that DOWN propagates automatically through a complex tree on construction."""
        health = Health(
            status=HealthStatus.UP,
            components={
                "database": Health(status=HealthStatus.UP),
                "services": Health(
                    status=HealthStatus.UP,
                    components={
                        "auth": Health(status=HealthStatus.DOWN, reason=AUTH_ERROR),
                        "storage": Health(status=HealthStatus.UP),
                    },
                ),
                "monitoring": Health(status=HealthStatus.UP),
            },
        )

        assert health.status == HealthStatus.DOWN
        assert health.reason is not None
        assert "Component 'services' is DOWN" in health.reason

        assert health.components["services"].status == HealthStatus.DOWN
        assert health.components["services"].reason is not None
        assert "Component 'auth' is DOWN" in health.components["services"].reason

        assert health.components["database"].status == HealthStatus.UP
        assert health.components["monitoring"].status == HealthStatus.UP

    @pytest.mark.unit
    def test_component_without_reason_raises(self) -> None:
        """Test that constructing a DOWN or DEGRADED component without a reason raises ValueError."""
        with pytest.raises(ValueError, match="Health DOWN must have a reason"):
            Health(status=HealthStatus.DOWN)

        with pytest.raises(ValueError, match="Health DEGRADED must have a reason"):
            Health(status=HealthStatus.DEGRADED)
