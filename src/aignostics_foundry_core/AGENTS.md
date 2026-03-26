# CLAUDE.md - Foundry Python Core Package Overview

This file provides an overview of all modules in `aignostics_foundry_core`, their features, and interactions.

## Module Index

<!-- Document your modules in a table format. Customize columns based on your architecture. -->

| Module | Purpose | Description |
|--------|---------|-------------|
| **models** | Shared output format enum | `OutputFormat` StrEnum with `YAML` and `JSON` values for use in CLI and API responses |
| **process** | Current process introspection | `ProcessInfo`, `ParentProcessInfo` Pydantic models and `get_process_info()` for runtime process metadata; `SUBPROCESS_CREATION_FLAGS` for subprocess creation |
| **console** | Themed terminal output | Module-level `console` object (Rich `Console`) with colour theme and `_get_console()` factory |
| **di** | Dependency injection | `locate_subclasses`, `locate_implementations`, `load_modules`, `discover_plugin_packages`, `clear_caches`, `PLUGIN_ENTRY_POINT_GROUP` for plugin and subclass discovery |
| **health** | Service health checks | `Health` model and `HealthStatus` enum for tree-structured health status |
| **settings** | Pydantic settings loading | `OpaqueSettings`, `load_settings`, `strip_to_none_before_validator`, `UNHIDE_SENSITIVE_INFO` for env-based settings with secret masking and user-friendly validation errors |

## Module Descriptions

<!-- For each module, document its purpose, features, dependencies, and usage. -->

### models

**Shared output format enum for CLI and API responses**

- **Purpose**: Provides a single source of truth for supported output formats across all Foundry components
- **Key Features**:
  - `OutputFormat(StrEnum)` — `YAML = "yaml"`, `JSON = "json"`; each member is a plain `str` subtype, usable wherever a string format identifier is expected
- **Location**: `aignostics_foundry_core/models.py`
- **Dependencies**: Python stdlib only (`enum.StrEnum`, Python ≥ 3.11)

### process

**Current process introspection**

- **Purpose**: Provides runtime process metadata for observability, diagnostics, and user-agent generation
- **Key Features**:
  - `ParentProcessInfo(BaseModel)` — `name` and `pid` of the parent process
  - `ProcessInfo(BaseModel)` — `project_root`, `pid`, `parent`, and `cmdline` of the current process
  - `get_process_info()` — returns a `ProcessInfo` for the running process (uses `psutil` lazily)
  - `SUBPROCESS_CREATION_FLAGS` — platform-safe creation flags for `subprocess` calls (suppresses console window on Windows)
- **Location**: `aignostics_foundry_core/process.py`
- **Dependencies**: `psutil>=6` (mandatory)

### console

**Themed Rich console for structured terminal output**

- **Purpose**: Provides a module-level `console` object pre-configured with a colour theme for consistent, styled terminal output across all Foundry components
- **Key Features**:
  - `console` — module-level `Console` singleton, ready to use
  - Colour theme: `success` (green), `info` / `logging.level.info` (purple4), `warning` (yellow1), `error` (red1), `debug` (light_cyan3)
  - `AIGNOSTICS_CONSOLE_WIDTH` env var — overrides console width (defaults to Rich's auto-detect, 80 in non-TTY environments)
  - `legacy_windows=False` — modern Windows terminal support
- **Location**: `aignostics_foundry_core/console.py`
- **Dependencies**: `rich>=13`

### settings

**Pydantic settings loading with secret masking and user-friendly validation errors**

- **Purpose**: Provides reusable infrastructure for loading `pydantic-settings` classes from the environment, with secret masking and Rich-formatted validation error output
- **Key Features**:
  - `UNHIDE_SENSITIVE_INFO: str` — context key constant to reveal secrets in `model_dump()`
  - `strip_to_none_before_validator(v)` — before-validator that strips whitespace and converts empty strings to `None`
  - `OpaqueSettings(BaseSettings)` — base class with `serialize_sensitive_info` (masks `SecretStr` fields) and `serialize_path_resolve` (resolves `Path` fields to absolute strings)
  - `load_settings(settings_class)` — instantiates settings; on `ValidationError` prints a Rich `Panel` listing each invalid field and calls `sys.exit(78)`
- **Location**: `aignostics_foundry_core/settings.py`
- **Dependencies**: `pydantic>=2`, `pydantic-settings>=2`, `rich>=14`

### di

**Plugin and subclass discovery for dependency injection**

- **Purpose**: Provides reusable infrastructure for dynamically discovering plugin packages, class implementations, and subclasses across a project and its registered plugins
- **Key Features**:
  - `PLUGIN_ENTRY_POINT_GROUP: str` — `"aignostics.plugins"` entry-point group constant
  - `discover_plugin_packages()` — discovers plugin packages registered via `[project.entry-points."aignostics.plugins"]`; LRU-cached
  - `load_modules(project_name)` — imports all top-level submodules of the given package
  - `locate_implementations(_class, project_name)` — finds all instances of `_class` via shallow plugin scan + deep project scan; cached per `(_class, project_name)` to prevent cross-project pollution
  - `locate_subclasses(_class, project_name)` — finds all subclasses of `_class` via shallow plugin scan + deep project scan; cached per `(_class, project_name)`
  - `clear_caches()` — resets all module-level caches (`_implementation_cache`, `_subclass_cache`, `discover_plugin_packages` LRU cache)
  - Two internal scan helpers: `_scan_packages_shallow` (plugin top-level exports only) and `_scan_packages_deep` (full submodule walk for the main project)
- **Location**: `aignostics_foundry_core/di.py`
- **Dependencies**: Python stdlib only (`importlib`, `pkgutil`, `importlib.metadata`)

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
│           console           │
│           health            │
└─────────────────────────────┘
```

## Usage Examples

```python
from aignostics_foundry_core import console

# Print with theme styles
console.print("[success]Done![/success]")
console.print("[warning]Caution: retrying...[/warning]")
console.print("[error]Failed to connect.[/error]")
```

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
