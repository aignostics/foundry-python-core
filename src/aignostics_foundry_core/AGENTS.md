# CLAUDE.md - Foundry Python Core Package Overview

This file provides an overview of all modules in `aignostics_foundry_core`, their features, and interactions.

## Module Index

<!-- Document your modules in a table format. Customize columns based on your architecture. -->

| Module | Purpose | Description |
|--------|---------|-------------|
| **models** | Shared output format enum | `OutputFormat` StrEnum with `YAML` and `JSON` values for use in CLI and API responses |
| **process** | Current process introspection | `ProcessInfo`, `ParentProcessInfo` Pydantic models and `get_process_info()` for runtime process metadata; `SUBPROCESS_CREATION_FLAGS` for subprocess creation |
| **api.exceptions** | API exception hierarchy and FastAPI handlers | `ApiException` (500), `NotFoundException` (404), `AccessDeniedException` (401); `api_exception_handler`, `unhandled_exception_handler`, `validation_exception_handler` for FastAPI registration |
| **api.auth** | Auth0 authentication FastAPI dependencies | `AuthSettings` (env-prefix configurable), `UnauthenticatedError`, `ForbiddenError` (403); `get_auth_client`, `get_user`, `require_authenticated`, `require_admin`, `require_internal`, `require_internal_admin` FastAPI dependencies; Auth0 cookie security schemes |
| **api.core** | Versioned API router and FastAPI factory | `VersionedAPIRouter` (tracks all created instances), `API_TAG_*` constants, `create_public/authenticated/admin/internal/internal_admin_router` factories, `build_api_metadata`, `build_versioned_api_tags`, `build_root_api_tags`, `get_versioned_api_instances(versions, build_metadata=None, *, context=None)`, `init_api()` |
| **api** | Consolidated API sub-package | Re-exports all public symbols from `api.exceptions`, `api.auth`, and `api.core`; import any API symbol directly from `aignostics_foundry_core.api` |
| **log** | Configurable loguru logging initialisation | `logging_initialize(filter_func=None, *, context=None)`, `LogSettings` (env-prefix configurable), `InterceptHandler` for stdlib-to-loguru bridging |
| **sentry** | Configurable Sentry integration | `sentry_initialize(integrations, *, context=None)`, `SentrySettings` (env-prefix configurable), `set_sentry_user(user, role_claim)` for Auth0 user context |
| **service** | FastAPI-injectable base service | `BaseService` ABC with `get_service()` (cached per-class FastAPI `Depends` factory), `key()`, and abstract `health()` / `info()` methods; concrete subclasses implement health checks and module info |
| **database** | Async SQLAlchemy session management | `init_engine(db_url, pool_size, max_overflow, pool_timeout)`, `dispose_engine()`, `get_db_session()` (FastAPI dependency), `execute_with_session(func, …)`, `cli_run_with_db(func, …, db_url)`, `cli_run_with_engine(func, …, db_url)`, `with_engine(db_url)` decorator factory; auto-resets engine after `fork()` |
| **cli** | Typer CLI preparation utilities | `prepare_cli(cli, epilog, *, context=None)` — discovers and registers subcommands via `locate_implementations`, sets epilog recursively, installs `no_args_is_help` workaround; `no_args_is_help_workaround(ctx)` — raises `typer.Exit` when no subcommand is invoked |
| **boot** | Application / library boot sequence | `boot(context, sentry_integrations, log_filter, show_cmdline)` — runs once per process: parses `--env` CLI args, initialises logging and Sentry, amends the SSL trust chain via *truststore* and *certifi*, and logs boot/shutdown messages |
| **user_agent** | Parameterised HTTP user-agent string builder | `user_agent(project_name, version, repository_url)` — builds `{project_name}-python-sdk/{version} (…)` string including platform info, current test, and GitHub Actions run URL |
| **gui** | NiceGUI page helpers, auth decorators, and nav builder | `GUINamespace` (configurable page decorator namespace), `gui` (default singleton), `page_public/authenticated/admin/internal/internal_admin` decorators, `get_gui_user`, `require_gui_user`, `BaseNavBuilder`, `NavItem`, `NavGroup`, `gui_get_nav_groups(*, context=None)`, `BasePageBuilder`, `gui_register_pages(*, context=None)`, `gui_run(*, context=None, …)`; constants `WINDOW_SIZE`, `BROWSER_RECONNECT_TIMEOUT`, `RESPONSE_TIMEOUT` |
| **console** | Themed terminal output | Module-level `console` object (Rich `Console`) with colour theme and `_get_console()` factory |
| **foundry** | Project context injection | `FoundryContext`, `FoundryContext.from_package()`, `set_context()`, `get_context()` — centralised project-specific values (name, version, environment, env files, URLs, `python_version`, runtime mode flags `is_container`, `is_cli`, `is_test`, `is_library`) derived from package metadata and environment variables |
| **di** | Dependency injection | `locate_subclasses(cls, *, context=None)`, `locate_implementations(cls, *, context=None)`, `load_modules(*, context=None)`, `discover_plugin_packages`, `clear_caches`, `PLUGIN_ENTRY_POINT_GROUP` for plugin and subclass discovery |
| **health** | Service health checks | `Health` model and `HealthStatus` enum for tree-structured health status |
| **settings** | Pydantic settings loading | `OpaqueSettings`, `load_settings`, `strip_to_none_before_validator`, `UNHIDE_SENSITIVE_INFO` for env-based settings with secret masking and user-friendly validation errors |

## Module Descriptions

<!-- For each module, document its purpose, features, dependencies, and usage. -->

### foundry

**Project context injection — single startup call replaces all per-project `_constants.py` files**

- **Purpose**: Provides `FoundryContext` — a frozen Pydantic model that owns all derivation logic for
  project-specific values. One `set_context(FoundryContext.from_package("myproject"))` call at
  application startup makes the context available everywhere in the library without threading values
  through call sites. Tests pass an explicit context override and never touch global state.
- **Key Features**:
  - `FoundryContext(BaseModel)` — frozen; fields: `name`, `version`, `version_full`, `environment`,
    `env_file: list[Path]`, `repository_url`, `documentation_url`, `python_version` (Python runtime
    version string, e.g. `"3.11.9"`), plus four runtime mode bool flags: `is_container`, `is_cli`,
    `is_test`, `is_library` (all default `False`).
  - `FoundryContext.from_package(package_name)` — classmethod that derives all values from
    `importlib.metadata` and environment variables (`{NAME}_ENVIRONMENT`, `VCS_REF`, `COMMIT_SHA`,
    `BUILDER`, `BUILD_DATE`, `CI_RUN_ID`, `CI_RUN_NUMBER`, `{NAME}_ENV_FILE`,
    `{NAME}_RUNNING_IN_CONTAINER`, `PYTEST_RUNNING_{NAME}`). Environment fallback chain:
    `{NAME}_ENVIRONMENT` → `ENV` → `VERCEL_ENV` → `RAILWAY_ENVIRONMENT` → `"local"`.
  - `set_context(ctx)` — installs *ctx* as the process-level singleton.
  - `get_context()` — returns the installed context or raises `RuntimeError` with a helpful message
    if `set_context()` has not been called.
- **Location**: `aignostics_foundry_core/foundry.py`
- **Dependencies**: `pydantic>=2`, Python stdlib (`importlib.metadata`, `os`, `sys`, `pathlib`)
- **Import**:
  ```python
  from aignostics_foundry_core.foundry import FoundryContext, set_context, get_context
  ```
- **Usage example**:
  ```python
  # Application startup (e.g. main.py or boot.py):
  from aignostics_foundry_core.foundry import FoundryContext, set_context, get_context

  set_context(FoundryContext.from_package("myproject"))

  # Library code — no threading of values through parameters:
  ctx = get_context()  # raises RuntimeError if startup omitted set_context()
  logger.info(f"Starting {ctx.name} {ctx.version} in {ctx.environment}")

  # Tests — pass context explicitly, do not call set_context():
  ctx = FoundryContext(name="test", version="0.0.0", version_full="0.0.0", environment="test")
  result = my_library_function(context=ctx)
  ```

### api.exceptions

**API exception hierarchy and FastAPI exception handlers**

- **Purpose**: Provides standardised HTTP exceptions and matching FastAPI exception handlers so all API errors return a consistent `{"success": false, "error": {"code": …, "message": …}}` envelope
- **Key Features**:
  - `ApiException(Exception)` — base API error; class-level `status_code = 500`, `message = "Unhandled API exception"`; both overridable via constructor kwargs
  - `NotFoundException(ApiException)` — `status_code = 404`
  - `AccessDeniedException(ApiException)` — `status_code = 401`
  - `api_exception_handler(request, exc)` — maps `ApiException` to `JSONResponse` with `success: False` and structured error body
  - `unhandled_exception_handler(request, exc)` — catches any `Exception`, logs at CRITICAL via loguru, returns 500
  - `validation_exception_handler(request, exc)` — handles Pydantic `ValidationError` / FastAPI `RequestValidationError`; calls `.errors()` if available, returns 422
- **Location**: `aignostics_foundry_core/api/exceptions.py`
- **Dependencies**: `fastapi>=0.110,<1` (mandatory); `loguru` (used lazily inside `unhandled_exception_handler`)
- **Import**: `from aignostics_foundry_core.api.exceptions import ApiException, NotFoundException, AccessDeniedException, api_exception_handler, unhandled_exception_handler, validation_exception_handler`

### api.auth

**Auth0 authentication and authorization FastAPI dependencies**

- **Purpose**: Provides Auth0 cookie-based session authentication dependencies for FastAPI routes. All project-specific settings (org ID, role claim) are loaded from `AuthSettings` whose env prefix is configurable at instantiation.
- **Key Features**:
  - `AuthSettings(OpaqueSettings)` — uses the active FoundryContext.env_prefix to derive the env prefix (`{ctx.env_prefix}AUTH_`). Fields: `internal_org_id` (for internal org check), `auth0_role_claim` (JWT claim name for role)
  - `UnauthenticatedError(Exception)` — raised when a user session is missing or invalid
  - `ForbiddenError(ApiException)` — `status_code = 403`; raised when user lacks required role or org membership
  - `get_auth_client(request)` — retrieves `AuthClient` from `request.app.state.auth_client`; raises `RuntimeError` if not configured
  - `get_user(request, _cookie)` — async FastAPI dependency; returns user dict from Auth0 session or `None`; validates expiry; sets Sentry user context
  - `require_authenticated` — dependency: requires a valid session
  - `require_admin` — dependency: requires admin role
  - `require_internal` — dependency: requires internal organization membership
  - `require_internal_admin` — dependency: requires internal org membership AND admin role
  - Auth0 cookie security scheme constants: `AUTH0_SESSION_COOKIE_NAME`, `AUTH0_TRANSACTION_COOKIE_NAME`, `AUTH0_ROLE_ADMIN`, `DEFAULT_AUTH0_ROLE_CLAIM`
- **Location**: `aignostics_foundry_core/api/auth.py`
- **Dependencies**: `auth0-fastapi>=1.0.0b5,<2`, `fastapi>=0.110,<1`, `loguru>=0.7,<1` (all mandatory)
- **Import**: `from aignostics_foundry_core.api.auth import AuthSettings, ForbiddenError, UnauthenticatedError, get_auth_client, get_user, require_authenticated, require_admin, require_internal, require_internal_admin`

### api.core

**Versioned API router and FastAPI application factory**

- **Purpose**: Provides `VersionedAPIRouter` for building versioned FastAPI sub-applications, typed tag constants, convenience router factory functions, metadata helpers, and a generic `init_api()` factory that registers the standard exception handlers.
- **Key Features**:
  - `VersionedAPIRouter` — class-level `_instances` registry; `__new__` creates a real `fastapi.APIRouter` subclass at runtime (lazy import); `get_instances()` returns a copy of the registry
  - `API_TAG_PUBLIC`, `API_TAG_AUTHENTICATED`, `API_TAG_ADMIN`, `API_TAG_INTERNAL`, `API_TAG_INTERNAL_ADMIN` — string constants for OpenAPI tagging
  - `create_public_router(module_tag, *, version, prefix, …)` — public (unauthenticated) router
  - `create_authenticated_router`, `create_admin_router`, `create_internal_router`, `create_internal_admin_router` — router factories that inject the appropriate `require_*` dependency from `api.auth`
  - `build_api_metadata(title, description, author_name, author_email, repository_url, documentation_url, version)` — returns a `dict` suitable for `FastAPI(**metadata)`
  - `build_versioned_api_tags(version_name, repository_url)` — OpenAPI tags for a single versioned sub-app
  - `build_root_api_tags(base_url, versions)` — OpenAPI tags for the root app linking to each version's docs
  - `get_versioned_api_instances(versions, build_metadata=None, *, context=None)` — loads project modules (resolved via context), creates one `FastAPI` per version, routes registered `VersionedAPIRouter` instances to the matching version
  - `init_api(root_path, lifespan, exception_handler_registrations, versions=None, version_exception_handler_registrations=None, **fastapi_kwargs)` — creates a `FastAPI` with the standard Foundry exception handlers (`ApiException`, `RequestValidationError`, `ValidationError`, `Exception`) pre-registered; when *versions* is supplied, calls `get_versioned_api_instances` internally, optionally applies *version_exception_handler_registrations* to each sub-app, and mounts them at `/{version}` on the root app
- **Location**: `aignostics_foundry_core/api/core.py`
- **Dependencies**: `fastapi>=0.110,<1` (mandatory); `aignostics_foundry_core.di` (`load_modules`)
- **Import**: `from aignostics_foundry_core.api.core import VersionedAPIRouter, init_api, build_api_metadata, …` or `from aignostics_foundry_core.api import …`

### boot

**Application / library boot sequence**

- **Purpose**: Provides a single, idempotent `boot()` entry-point that initialises the full observability and SSL stack in the correct order. All project-specific metadata is injected as parameters so the function is reusable across any project.
- **Key Features**:
  - `boot(context, sentry_integrations, log_filter, show_cmdline)` — runs once per process; subsequent calls are silent no-ops
  - Parses `--env`/`-e KEY=VALUE` CLI arguments: vars matching `{PROJECT_NAME_UPPER}_*` are injected into `os.environ` and removed from `sys.argv`
  - Calls `logging_initialize` with project metadata
  - Calls `_amend_ssl_trust_chain`: injects *truststore* into the SSL context (if available) and sets `SSL_CERT_FILE` to the *certifi* bundle path when no system CA bundle is detected
  - Calls `sentry_initialize`; reads deployment environment from `{PROJECT_NAME_UPPER}_ENVIRONMENT` env var (default: `"production"`)
  - Logs a boot message (project, version, pid, parent process, optional cmdline) at DEBUG level
  - Registers an atexit handler that logs a shutdown trace (skipped inside pytest to avoid closed-stream errors)
- **Location**: `aignostics_foundry_core/boot.py`
- **Dependencies**: `loguru>=0.7,<1`, `certifi>=2024`, `truststore>=0.9,<1` (all mandatory); `aignostics_foundry_core.log`, `aignostics_foundry_core.sentry`, `aignostics_foundry_core.process`
- **Import**: `from aignostics_foundry_core.boot import boot`

### log

**Configurable loguru logging initialisation**

- **Purpose**: Bootstraps loguru as the primary logging framework, optionally redirecting stdlib `logging` via `InterceptHandler`. All project-specific constants are passed as parameters rather than hard-coded.
- **Key Features**:
  - `InterceptHandler(logging.Handler)` — redirects stdlib log records to loguru, preserving original module/function/line metadata
  - `LogSettings(BaseSettings)` — uses the active FoundryContext.env_prefix to derive the env prefix (`{ctx.env_prefix}LOG_`). Fields: `level`, `stderr_enabled`, `file_enabled`, `file_name`, `redirect_logging`
  - `logging_initialize(filter_func, *, context)` — removes all existing loguru handlers, then adds stderr/file handlers per settings; reads project name, version, and env file list from `context` (falls back to process-level context); embeds `project_name` and `version` in loguru `extra`; installs `InterceptHandler` for stdlib redirect; suppresses psycopg pool noise
- **Location**: `aignostics_foundry_core/log.py`
- **Dependencies**: `loguru>=0.7,<1`, `platformdirs>=4,<5` (mandatory)
- **Import**: `from aignostics_foundry_core.log import logging_initialize, LogSettings, InterceptHandler`

### sentry

**Configurable Sentry integration for error tracking and performance monitoring**

- **Purpose**: Bootstraps Sentry SDK with all project-specific metadata supplied as explicit parameters, making the initialisation reusable across any project without hard-coded constants.
- **Key Features**:
  - `SentrySettings(OpaqueSettings)` — uses the active FoundryContext.env_prefix to derive the env prefix (`{ctx.env_prefix}SENTRY_`). Fields: `enabled`, `dsn` (validated HTTPS Sentry URL), `debug`, `send_default_pii`, `max_breadcrumbs`, `sample_rate`, `traces_sample_rate`, `profiles_sample_rate`, `profile_session_sample_rate`, `profile_lifecycle`, `enable_logs`
  - `sentry_initialize(integrations, *, context=None)` — derives all project-specific values (name, version, environment, URLs, runtime flags) from *context* (or the global context); env prefix and env file are read from `ctx.env_prefix` and `ctx.env_file`; initialises Sentry SDK when enabled and DSN present; sets `aignx/base` context; suppresses noisy loggers; returns `True` on success, `False` otherwise
  - `set_sentry_user(user, role_claim)` — maps Auth0 user claims (`sub` → `id`, `email`, `name`, …) into Sentry scope; pass `None` to clear context; no-op when `sentry_sdk` is absent
- **Location**: `aignostics_foundry_core/sentry.py`
- **Dependencies**: `sentry-sdk>=2,<3` (mandatory); `loguru>=0.7,<1`
- **Import**: `from aignostics_foundry_core.sentry import SentrySettings, sentry_initialize, set_sentry_user`

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
  - `load_modules(*, context=None)` — imports all top-level submodules of the package named by `context`; falls back to the global context set via `set_context()`; raises `RuntimeError` if neither is available
  - `locate_implementations(_class, *, context=None)` — finds all instances of `_class` via shallow plugin scan + deep project scan; cached per `(_class, context.name)` to prevent cross-project pollution; raises `RuntimeError` if no context configured
  - `locate_subclasses(_class, *, context=None)` — finds all subclasses of `_class` via shallow plugin scan + deep project scan; cached per `(_class, context.name)`; raises `RuntimeError` if no context configured
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

### service

**FastAPI-injectable base service class**

- **Purpose**: Provides a reusable `BaseService` ABC that all module services extend. Encapsulates the FastAPI dependency-injection pattern (`Depends(Service.get_service())`) and enforces a consistent `health()` / `info()` interface across all services.
- **Key Features**:
  - `BaseService(ABC)` — abstract base class; accepts an optional `settings_class` in `__init__` and loads it via `load_settings`
  - `get_service()` — class method that returns a per-class-cached generator callable suitable for `Depends()`; caching is required for `dependency_overrides` to work in tests
  - `key()` — returns the second-to-last component of `__module__` as a string identifier (e.g. `"mymodule"` from `"bridge.mymodule._service"`)
  - `health()` — abstract `async` method; subclasses return a `Health` instance
  - `info(mask_secrets)` — abstract `async` method; subclasses return a `dict[str, Any]`
  - `settings()` — returns the loaded `BaseSettings` instance
- **Location**: `aignostics_foundry_core/service.py`
- **Dependencies**: `fastapi>=0.110,<1` (for typing/DI); `pydantic-settings>=2`; `aignostics_foundry_core.health`, `aignostics_foundry_core.settings`
- **Import**: `from aignostics_foundry_core.service import BaseService`

### cli

**Typer CLI preparation utilities**

- **Purpose**: Provides helpers to bootstrap a Typer application with auto-discovered subcommands, recursive epilog propagation, and a workaround for the Typer `no_args_is_help` bug.
- **Key Features**:
  - `prepare_cli(cli, epilog, *, context=None)` — discovers all `typer.Typer` instances via `locate_implementations(typer.Typer, context=context)`, adds them as sub-typers (skipping `cli` itself), sets `cli.info.epilog`, propagates the epilog to all nested commands via `_add_epilog_recursively`, and installs `no_args_is_help_workaround` via `_no_args_is_help_recursively`. Pass a `FoundryContext` explicitly or rely on the global context set via `set_context()`.
  - `no_args_is_help_workaround(ctx)` — Typer callback that prints help and raises `typer.Exit` when `ctx.invoked_subcommand is None`; workaround for https://github.com/fastapi/typer/pull/1240.
- **Location**: `aignostics_foundry_core/cli.py`
- **Dependencies**: `typer>=0.14,<1` (mandatory); `aignostics_foundry_core.di`
- **Import**: `from aignostics_foundry_core.cli import prepare_cli, no_args_is_help_workaround`

### database

**Async SQLAlchemy session management**

- **Purpose**: Manages a process-level async database engine singleton, providing session injection for FastAPI routes, background jobs, and CLI commands. All Bridge-specific settings are replaced with explicit parameters.
- **Key Features**:
  - `init_engine(db_url, pool_size=10, max_overflow=10, pool_timeout=30)` — initialises the global `AsyncEngine` and `async_sessionmaker`; subsequent calls are silent no-ops. Pool parameters are omitted automatically for SQLite (which does not use `QueuePool`).
  - `dispose_engine()` — async; disposes the engine; called during application shutdown.
  - `get_db_session()` — async generator; yields an `AsyncSession`; raises `RuntimeError` if engine not initialised. Use as a FastAPI `Depends` target.
  - `execute_with_session(async_func, *args, **kwargs)` — async; runs `async_func` with a session injected as the `session` keyword argument. For background jobs and CLI helpers.
  - `cli_run_with_db(async_func, *args, db_url, pool_size, max_overflow, pool_timeout, **kwargs)` — synchronous wrapper: initialises engine, runs the coroutine, then disposes. For CLI commands.
  - `cli_run_with_engine(async_func, *args, db_url, pool_size, max_overflow, pool_timeout, **kwargs)` — like `cli_run_with_db` but does not inject a session; for jobs that manage sessions themselves.
  - `with_engine(db_url, pool_size, max_overflow, pool_timeout)` — decorator factory; wraps an async function to initialise the engine before execution. For long-lived workers; does **not** dispose after running.
  - Fork safety: `multiprocessing.util.register_after_fork` resets the engine in child processes automatically.
- **Location**: `aignostics_foundry_core/database.py`
- **Dependencies**: `sqlalchemy[asyncio]>=2,<3`, `asyncpg>=0.29,<1` (mandatory); `loguru` for structured logging
- **Import**: `from aignostics_foundry_core.database import init_engine, dispose_engine, get_db_session, execute_with_session, cli_run_with_db, cli_run_with_engine, with_engine`

### user_agent

**Parameterised HTTP user-agent string builder**

- **Purpose**: Generates a standard HTTP User-Agent header value for outgoing requests, embedding project identity, runtime platform info, and CI/test context
- **Key Features**:
  - `user_agent(project_name, version, repository_url)` — returns a string in the format `{project_name}-python-sdk/{version} ({platform}; +{repository_url}[; {PYTEST_CURRENT_TEST}][; +{github_run_url}])`
  - Automatically includes `PYTEST_CURRENT_TEST` env var when running under pytest
  - Automatically includes a `github.com/…/actions/runs/…` URL when `GITHUB_RUN_ID` and `GITHUB_REPOSITORY` env vars are set
  - No external dependencies (stdlib `os` and `platform` only)
- **Location**: `aignostics_foundry_core/user_agent.py`
- **Dependencies**: Python stdlib only
- **Import**: `from aignostics_foundry_core.user_agent import user_agent`

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
