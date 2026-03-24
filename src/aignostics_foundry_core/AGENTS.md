# CLAUDE.md - Foundry Python Core Package Overview

This file provides an overview of all modules in `aignostics_foundry_core`, their features, and interactions.

## Module Index

<!-- Document your modules in a table format. Customize columns based on your architecture. -->

| Module | Purpose | Description |
|--------|---------|-------------|
| **health** | Service health checks | `Health` model and `HealthStatus` enum for tree-structured health status |

## Module Descriptions

<!-- For each module, document its purpose, features, dependencies, and usage. -->

### health

**Tree-structured health status for service health checks**

- **Purpose**: Provides `Health` and `HealthStatus` for modelling UP / DEGRADED / DOWN status across a tree of service components
- **Key Features**:
  - `HealthStatus(StrEnum)` — `UP`, `DEGRADED`, `DOWN` values
  - `Health(BaseModel)` — pydantic model with `status`, `reason`, `components`, `uptime_statistics`
  - `compute_health_from_components()` — recursively propagates DOWN/DEGRADED from children to parent (DOWN trumps DEGRADED)
  - `validate_health_state()` — model validator: DOWN/DEGRADED require a reason; UP must not have one
  - `__str__` — returns `"UP"`, `"DEGRADED: <reason>"`, or `"DOWN: <reason>"`
  - `__bool__` — `True` iff status is `UP`
  - `Health.Code` — `ClassVar` alias for `HealthStatus` (convenience)
- **Location**: `aignostics_foundry_core/health.py`
- **Dependencies**: `pydantic>=2`

## Architecture

<!-- Document your package's architecture here. Consider including:
- Module dependency diagrams
- Data flow patterns
- Key abstractions and interfaces
- Integration points
-->

```text
┌─────────────────────────────┐
│     Your Application        │
└──────────────┬──────────────┘
               │
┌──────────────┴──────────────┐
│    aignostics_foundry_core  │
├─────────────────────────────┤
│           health            │
└─────────────────────────────┘
```

## Usage Examples

```python
from aignostics_foundry_core.health import Health, HealthStatus

# Simple UP status
health = Health(status=HealthStatus.UP)
assert bool(health)  # True
assert str(health) == "UP"

# Composite health — DOWN propagates from components automatically
system = Health(
    status=HealthStatus.UP,
    components={
        "db": Health(status=HealthStatus.UP),
        "cache": Health(status=HealthStatus.DOWN, reason="Connection refused"),
    },
)
assert system.status == HealthStatus.DOWN
assert "cache" in system.reason
```

## Development Guidelines

### Adding New Modules

1. Create module in `src/aignostics_foundry_core/`
2. Export public API in `__init__.py`
3. Add tests in `tests/aignostics_foundry_core/`
4. Document in this file (add to Module Index and Module Descriptions)

### Module Documentation

Consider creating `CLAUDE.md` files in module subdirectories for detailed documentation of complex modules.

---

*Keep this documentation updated as the package evolves.*
