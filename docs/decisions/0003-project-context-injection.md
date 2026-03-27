# 3. Project context injection

Date: 2026-03-26

## Status

Open

## Context

`aignostics_foundry_core` is used as a shared library across multiple projects (API servers, CLI tools). Several library functions need project-specific information to work correctly; for example:

- `locate_subclasses()` needs the project name to scope its module walk
- `boot()` needs the project name, version, and environment
- `sentry_initialize()` needs project metadata plus runtime mode flags (`is_cli`, `is_container`, etc.)

In Bridge, this is solved by `_constants.py`: a module that computes all of these values at import time using `__name__.split(".")[0]` to derive the project name, `importlib.metadata` for version, and environment variables for the rest. This works because `_constants.py` lives inside the `bridge` package, but cannot be reused as-is in the library, since e.g. `__name__.split(".")[0]` would return `"aignostics_foundry_core"` instead of the calling project's name.

### Requirements

1. Library functions must receive project-specific values (project name, version, environment, mode flags, etc.)
2. The logic for deriving these values (currently in `_constants.py`) should not be duplicated across every project that uses the library.
3. Derived values (e.g. `version_full`) must be readable by projects, not just passed into library functions — since they're referenced in many places (API metadata, user-agent strings, etc.).
4. The solution must work for both long-lived API servers and short-lived CLI tools.

## Options

**#1 Explicit parameterization**

Each library function receives the values it needs as arguments. The caller is responsible for computing them — effectively re-implementing `_constants.py` in every project.

```python
sentry_initialize(
    project_name="bridge",
    version=__version_with_vcs_ref__,
    environment=__env__,
    is_container=__is_running_in_container__,
    ...
)
```

* Pros: fully explicit, no hidden state
* Cons: violates requirement #2 — every project must maintain its own `_constants.py` equivalent; long call signatures

**#2 Environment variables**

Projects set `FOUNDRY_CORE_PROJECT_NAME`, `FOUNDRY_CORE_VERSION`, etc.; the library reads them. The caller is still responsible for computing and exporting all derived values (requirement #2 violated in the same way as #1).

```python
project_name = os.getenv("FOUNDRY_CORE_PROJECT_NAME")
```

* Pros: zero code coupling; works naturally in containerised deployments
* Cons: stringly typed; CLI tools are invoked locally where env vars are less reliable; doesn't satisfy requirement #3 (no typed accessor for derived values)

**#3 Library-level `configure()` init pattern**

A one-time call at startup sets global library state; all functions then read from it. This is similar to configuration/init pattern used by logging libraries and the Sentry SDK.

```python
foundry.configure(project_name="bridge", version=__version__, ...)
locate_subclasses(BaseService)  # reads from global state

def locate_subclasses(_class):
    project_name = foundry.config.project_name
    ...
```

* Pros: clean call sites; no threading of values
* Cons: caller still computes the values (requirement #2 violated); global mutable state; harder to test

**#4 `ProjectConfig` dataclass + `from_package()` classmethod**

The library owns the derivation logic in `ProjectConfig.from_package(project_name)`, which reads from `importlib.metadata`, `sys.argv`, CI env vars, etc. Projects construct a config and pass it at call sites.

```python
config = ProjectConfig.from_package("bridge")
locate_subclasses(BaseService, config=config)
```

* Pros: requirements #1 and #2 satisfied; typed; derivation logic lives once in the library
* Cons: requirement #3 only partially satisfied — projects must hold and thread their own `config` reference to read derived values, which doesn't fully eliminate `_constants.py`

**#5 `ProjectConfig.from_package()` + `configure()` + `foundry.config` accessor (combination of #3 and #4)**

Extends #4 with a `configure()` call that stores the config as library-level state, exposed back to callers via `foundry.config`. Library functions fall back to the configured default but accept an explicit `config` override for testing.

```python
# at startup — replaces _constants.py entirely
foundry.configure(ProjectConfig.from_package("bridge"))

# library functions use the configured default
locate_subclasses(BaseService)

def locate_subclasses(_class: type, config: ProjectConfig | None = None) -> list:
    config = config or foundry.config
    ...

# projects read derived values back from the library
print(foundry.config.user_agent)

# in tests — explicit override, no global state touched
locate_subclasses(BaseService, config=ProjectConfig(name="test-project", ...))
```

* Pros: all four requirements satisfied; `_constants.py` can be deleted outright; ergonomic for production; testable without resetting global state
* Cons: global mutable state, though contained — tests pass config explicitly and never need to reset it

## Decision

I suggest we use **#5**.

`ProjectConfig` holds project identity and build metadata. Runtime mode flags (`is_container`, `is_cli`, `is_test`, `is_library`) are only consumed by `sentry_initialize()`, so they live in a nested `SentryContext` rather than on `ProjectConfig` directly:

```python
@dataclass
class SentryContext:
    is_container: bool
    is_cli: bool
    is_test: bool
    is_library: bool


@dataclass
class ProjectConfig:
    name: str
    version: str
    version_full: str
    environment: str
    env_file: list[Path]
    repository_url: str = ""
    documentation_url: str = ""
    sentry: SentryContext = field(default_factory=SentryContext)
```

Each project calls `configure()` once at startup. This single line replaces `_constants.py` entirely:

```python
foundry.configure(ProjectConfig.from_package("bridge"))
```

The configured `ProjectConfig` is accessible anywhere via `foundry.config`:

```python
# before: from bridge.utils._constants import __version_full__, __project_name__
# after:
foundry.config.version_full
foundry.config.name
```

All public library functions fall back to `foundry.config` but accept an explicit override:

```python
def locate_subclasses(_class: type, config: ProjectConfig | None = None) -> list:
    config = config or foundry.config
    ...
```

`SentryContext` is kept separate from `SentrySettings` (which holds SDK configuration loaded from env vars). `SentryContext` is runtime-computed; `SentrySettings` is env-based.

## Consequences

- `_constants.py` is eliminated entirely across all projects; derivation logic lives once in the library and derived values are read back via `foundry.config`.
- New projects (API servers and CLI tools alike) require a single `configure()` call and no boilerplate.
- Production call sites are clean — no config threading.
- Tests can pass a `ProjectConfig` directly without touching or resetting global state.
- `SentryContext` nesting makes it clear that the mode flags are Sentry-specific and not general-purpose project metadata.
