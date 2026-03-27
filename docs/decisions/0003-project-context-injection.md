# 3. Project context injection

Date: 2026-03-26

## Status

Accepted

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

**#3 Library-level `set_context()` init pattern**

A one-time call at startup sets global library state; all functions then read from it. This is similar to configuration/init pattern used by logging libraries and the Sentry SDK.

```python
foundry.set_context(project_name="bridge", version=__version__, ...)
locate_subclasses(BaseService)  # reads from global state

def locate_subclasses(_class):
    project_name = foundry.context.name
    ...
```

* Pros: clean call sites; no threading of values
* Cons: caller still computes the values (requirement #2 violated); global mutable state; harder to test

**#4 `FoundryContext` Pydantic model + `from_package()` classmethod**

The library owns the derivation logic in `FoundryContext.from_package(project_name)`, which reads from `importlib.metadata`, `sys.argv`, CI env vars, etc. Projects construct a context and pass it at call sites.

**Why Pydantic:** a frozen Pydantic model provides an immutable, typed data structure with built-in validation and convenient construction from dicts. It also plays well with subclassing for projects that need extra fields. It is already installed as a dependency and is used for `SentrySettings`, so it fits well within the existing codebase.

```python
ctx = FoundryContext.from_package("bridge")
locate_subclasses(BaseService, context=ctx)
```

* Pros: requirements #1 and #2 satisfied; typed; derivation logic lives once in the library
* Cons: requirement #3 only partially satisfied — projects must hold and thread their own `context` reference to read derived values, which doesn't fully eliminate `_constants.py`

**#5 `FoundryContext.from_package()` + `set_context()` + `foundry.context` accessor (combination of #3 and #4)**

Extends #4 with a `set_context()` call that stores the context as library-level state, exposed back to callers via `foundry.context`. Library functions fall back to the configured default but accept an explicit `context` override for testing.

```python
# at startup — replaces _constants.py entirely
foundry.set_context(FoundryContext.from_package("bridge"))

# library functions use the configured default
locate_subclasses(BaseService)

def locate_subclasses(_class: type, context: FoundryContext | None = None) -> list:
    context = context or foundry.context
    ...

# projects read derived values back from the library
print(foundry.context.version_full)

# in tests — explicit override, no global state touched
locate_subclasses(BaseService, context=FoundryContext(name="test-project", ...))
```

* Pros: all four requirements satisfied; `_constants.py` can be deleted outright; ergonomic for production; testable without resetting global state
* Cons: global mutable state, though contained — tests pass context explicitly and never need to reset it

## Decision

We use **#5**.

### Naming

The central type is named `FoundryContext` (not `ProjectConfig` or `ProjectContext`). Rationale:

- "Config" was rejected because it implies values loaded from env vars or files; this object is derived at startup from `importlib.metadata`, `sys.argv`, and env vars — it is computed context, not configuration input. The existing `SentrySettings` type already uses the "settings/config" pattern for env-based values.
- "Project" prefix was considered but doesn't communicate which library owns the type. Since `FoundryContext` is specifically the library's handle on a project, naming it after the library makes the dependency explicit and aids discoverability.
- The name is consistent with `SentryContext` (also runtime-computed, also nested within the same design).

### Structure

`FoundryContext` is a frozen Pydantic model, making all instances immutable after construction. Runtime mode flags (`is_container`, `is_cli`, `is_test`, `is_library`) are only consumed by `sentry_initialize()`, so they live in a nested `SentryContext` rather than on `FoundryContext` directly:

```python
class SentryContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_container: bool
    is_cli: bool
    is_test: bool
    is_library: bool


class FoundryContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    version_full: str
    environment: str
    env_file: list[Path]
    repository_url: str = ""
    documentation_url: str = ""
    sentry: SentryContext = Field(default_factory=SentryContext)
```

Each project calls `set_context()` once at startup. This single line replaces `_constants.py` entirely:

```python
foundry.set_context(FoundryContext.from_package("bridge"))
```

The configured `FoundryContext` is accessible anywhere via `foundry.context`:

```python
# before: from bridge.utils._constants import __version_full__, __project_name__
# after:
foundry.context.version_full
foundry.context.name
```

All public library functions fall back to `foundry.context` but accept an explicit override:

```python
def locate_subclasses(_class: type, context: FoundryContext | None = None) -> list:
    context = context or foundry.context
    ...
```

`SentryContext` is kept separate from `SentrySettings` (which holds SDK configuration loaded from env vars). `SentryContext` is runtime-computed; `SentrySettings` is env-based.

### Extending FoundryContext

Projects that need additional context fields beyond the base set can subclass `FoundryContext`. The subclass overrides `from_package()` to compute its extra fields, using `model_dump()` to forward all base fields:

```python
class BridgeContext(FoundryContext):
    tenant_id: str = ""
    deployment_region: str = "eu-west-1"

    @classmethod
    def from_package(cls, package_name: str) -> "BridgeContext":
        base = super().from_package(package_name)
        return cls(
            **base.model_dump(),
            tenant_id=os.getenv("TENANT_ID", ""),
            deployment_region=os.getenv("REGION", "eu-west-1"),
        )
```

At startup the subclass instance is passed to `set_context()` as usual:

```python
foundry.set_context(BridgeContext.from_package("bridge"))
```

`foundry.context` is typed as `FoundryContext` — sufficient for all library functions. Project code that needs access to the extended fields keeps its own reference to the concrete instance:

```python
bridge_context = BridgeContext.from_package("bridge")
foundry.set_context(bridge_context)

# library uses foundry.context (FoundryContext) — no project-specific fields needed
# project code uses bridge_context directly for its own extended fields
bridge_context.tenant_id
```

This avoids module-level generics (which are awkward in Python) while keeping both the library and project code fully typed without casts.

## Consequences

- `_constants.py` is eliminated entirely across all projects; derivation logic lives once in the library and derived values are read back via `foundry.context`.
- New projects (API servers and CLI tools alike) require a single `set_context()` call and no boilerplate.
- Production call sites are clean — no context threading.
- Tests can pass a `FoundryContext` directly without touching or resetting global state.
- `SentryContext` nesting makes it clear that the mode flags are Sentry-specific and not general-purpose project metadata.
- Projects that need additional fields subclass `FoundryContext` and pass their subclass to `configure()`; they hold their own typed reference for project-specific access.
