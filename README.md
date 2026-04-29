# 🏭 Foundry Python Core

[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/aignostics/foundry-python-core/blob/main/LICENSE)
[![CI](https://github.com/aignostics/foundry-python-core/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/aignostics/foundry-python-core/actions/workflows/ci-cd.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=aignostics_foundry-python-core&metric=alert_status&token=a2fcb508f6d22af0c9d0a38728a7f5ee22d5b2ab)](https://sonarcloud.io/summary/new_code?id=aignostics_foundry-python-core)
[![Security](https://sonarcloud.io/api/project_badges/measure?project=aignostics_foundry-python-core&metric=security_rating&token=a2fcb508f6d22af0c9d0a38728a7f5ee22d5b2ab)](https://sonarcloud.io/summary/new_code?id=aignostics_foundry-python-core)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=aignostics_foundry-python-core&metric=sqale_rating&token=a2fcb508f6d22af0c9d0a38728a7f5ee22d5b2ab)](https://sonarcloud.io/summary/new_code?id=aignostics_foundry-python-core)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=aignostics_foundry-python-core&metric=sqale_index&token=a2fcb508f6d22af0c9d0a38728a7f5ee22d5b2ab)](https://sonarcloud.io/summary/new_code?id=aignostics_foundry-python-core)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=aignostics_foundry-python-core&metric=code_smells&token=a2fcb508f6d22af0c9d0a38728a7f5ee22d5b2ab)](https://sonarcloud.io/summary/new_code?id=aignostics_foundry-python-core)
[![Dependabot](https://img.shields.io/badge/dependabot-active-brightgreen?style=flat-square&logo=dependabot)](https://github.com/aignostics/foundry-python-core/security/dependabot)
[![Renovate enabled](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://github.com/aignostics/foundry-python-core/issues?q=is%3Aissue%20state%3Aopen%20Dependency%20Dashboard)
[![Coverage](https://codecov.io/gh/aignostics/foundry-python-core/graph/badge.svg?token=MXmzYbXguM)](https://codecov.io/gh/aignostics/foundry-python-core)
[![Ruff](https://img.shields.io/badge/style-Ruff-blue?color=D6FF65)](https://github.com/aignostics/foundry-python-core/blob/main/noxfile.py)
[![Pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/aignostics/foundry-python)

Foundational infrastructure for Foundry components.

## Prerequisites

Install [mise](https://mise.jdx.dev/) (task runner and dev tool manager):

```shell
brew install mise
```

Or follow the [installation guide](https://mise.jdx.dev/getting-started.html) for other methods. Then [activate mise](https://mise.jdx.dev/getting-started.html#activate-mise) in your shell profile.

## Usage

### Quickstart

`FoundryContext` is the single source of truth for all project-specific values. One call at
application startup makes everything available library-wide — logging, Sentry, database settings,
and more all derive from it automatically.

#### Initialise and boot

```python
# main.py
from aignostics_foundry_core.foundry import FoundryContext, set_context
from aignostics_foundry_core.boot import boot

set_context(FoundryContext.from_package("myproject"))
boot()
```

`FoundryContext.from_package("myproject")` reads package metadata and environment variables to
populate every field:

- `name`, `version`, `version_full` — from `importlib.metadata`
- `environment` — resolved from env vars in priority order (see [Configuration reference](#configuration-reference) below)
- `env_prefix` (`"MYPROJECT_"`) — used by every settings class; all env vars for this project share this prefix
- `is_container`, `is_cli`, `is_test`, `is_library` — detected automatically

`boot()` initialises logging (loguru), amends the SSL trust chain (truststore + certifi), and
optionally starts Sentry — all in one call.

#### Env file search order

Settings are loaded from the environment **and** from env files. Highest priority first:

1. `.env.{environment}`
2. `.env`
3. `{MYPROJECT_ENV_FILE}` (optional extra file; when the variable is set)
4. `~/.myproject/.env.{environment}`
5. `~/.myproject/.env`

#### Access the context from any module

```python
from aignostics_foundry_core.foundry import get_context

ctx = get_context()
print(f"Running {ctx.name} v{ctx.version_full} in {ctx.environment}")
# → Running myproject v1.2.3+main-abc1234---run.12345---build.42 in staging
```

`get_context()` raises `RuntimeError` with a clear message if `set_context()` was never called.

#### Testing pattern

Never call `set_context()` in tests. Pass a `FoundryContext` directly to functions via their
optional `context` parameter:

```python
from aignostics_foundry_core.foundry import FoundryContext
from aignostics_foundry_core.log import logging_initialize

ctx = FoundryContext(name="myproject", version="0.0.0", version_full="0.0.0", environment="test")
logging_initialize(context=ctx)
```

All public library functions (`logging_initialize`, `sentry_initialize`, `boot`, `load_modules`,
etc.) accept an optional `context` keyword argument and fall back to `get_context()` when it is
`None`.

---

### Configuration reference

All settings classes read from environment variables prefixed with `{PREFIX}` where
`{PREFIX}` = `MYPROJECT_` for a package named `myproject`.

#### Context & deployment environment

Read directly by `FoundryContext.from_package()` — no settings class.

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}ENVIRONMENT` | `"local"` | Deployment environment name. Highest priority. |
| `ENV` | — | Fallback environment (lower priority than `{PREFIX}ENVIRONMENT`). |
| `VERCEL_ENV` | — | Vercel deployment environment (lower priority). |
| `RAILWAY_ENVIRONMENT` | — | Railway deployment environment (lower priority). |
| `{PREFIX}RUNNING_IN_CONTAINER` | unset | Set to any non-empty value to mark `is_container = True`. |
| `{PREFIX}ENV_FILE` | unset | Path to an additional env file, inserted between the home-dir files and the local `.env`. |

#### Build metadata

Read by `FoundryContext.from_package()` to build `version_full` and `version_with_vcs_ref`. All
optional; most useful in CI.

| Variable | Default | Description |
|---|---|---|
| `VCS_REF` | read from `.git/HEAD` | Branch name or commit SHA. Falls back to reading `.git/HEAD` when project path is found. |
| `COMMIT_SHA` | `"unknown"` | Full commit SHA; first 7 chars used. |
| `BUILD_DATE` | `"unknown"` | Build date string. |
| `CI_RUN_ID` | `"unknown"` | CI system run ID. |
| `CI_RUN_NUMBER` | `"unknown"` | CI system build number. |
| `BUILDER` | `"uv"` | Build tool name. |

When any of these variables is set, `version_full` gains a `+…` suffix, e.g.
`1.2.3+main-abc1234---run.12345---build.42`.

#### Logging (`{PREFIX}LOG_`)

Settings class: `LogSettings`

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}LOG_LEVEL` | `INFO` | Log level: `CRITICAL`, `ERROR`, `WARNING`, `SUCCESS`, `INFO`, `DEBUG`, or `TRACE`. |
| `{PREFIX}LOG_STDERR_ENABLED` | `true` | Enable logging to stderr. |
| `{PREFIX}LOG_FILE_ENABLED` | `false` | Enable logging to a file. |
| `{PREFIX}LOG_FILE_NAME` | platform log dir | Path to the log file (validated on startup when `FILE_ENABLED` is true). |
| `{PREFIX}LOG_REDIRECT_LOGGING` | `true` | Redirect stdlib `logging` to loguru via `InterceptHandler`. |

#### Sentry (`{PREFIX}SENTRY_`)

Settings class: `SentrySettings`. Sentry is only initialised when `ENABLED=true` **and** `DSN` is
set.

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}SENTRY_ENABLED` | `false` | Enable Sentry error and performance monitoring. |
| `{PREFIX}SENTRY_DSN` | unset | Sentry DSN (must be an HTTPS URL with a valid `ingest.*.sentry.io` domain). |
| `{PREFIX}SENTRY_DEBUG` | `false` | Enable Sentry SDK debug mode. |
| `{PREFIX}SENTRY_SEND_DEFAULT_PII` | `false` | Include personally-identifiable information in events. |
| `{PREFIX}SENTRY_MAX_BREADCRUMBS` | `50` | Maximum breadcrumbs stored per event. |
| `{PREFIX}SENTRY_SAMPLE_RATE` | `1.0` | Error event sample rate (0.0–1.0). |
| `{PREFIX}SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Transaction/trace sample rate. |
| `{PREFIX}SENTRY_PROFILES_SAMPLE_RATE` | `0.1` | Profiler sample rate. |
| `{PREFIX}SENTRY_PROFILE_SESSION_SAMPLE_RATE` | `0.1` | Profile session sample rate. |
| `{PREFIX}SENTRY_PROFILE_LIFECYCLE` | `"trace"` | Profile lifecycle mode: `"trace"` or `"manual"`. |
| `{PREFIX}SENTRY_ENABLE_LOGS` | `true` | Forward log records to Sentry. |

#### Database (`{PREFIX}DB_`)

Settings class: `DatabaseSettings`. Database configuration is only activated when `{PREFIX}DB_URL`
is present (in the environment or in an env file).

| Variable | Required | Default | Description |
|---|---|---|---|
| `{PREFIX}DB_URL` | to activate | — | Full async database connection URL (e.g. `postgresql+asyncpg://user:pass@host/db`). Always access via `DatabaseSettings.get_url()`. |
| `{PREFIX}DB_POOL_SIZE` | no | `10` | SQLAlchemy connection pool size. |
| `{PREFIX}DB_POOL_MAX_OVERFLOW` | no | `10` | Max connections above pool size. |
| `{PREFIX}DB_POOL_TIMEOUT` | no | `30.0` | Seconds to wait for a pool connection. |
| `{PREFIX}DB_NAME` | no | unset | Override the database name in the URL path at runtime. |

Once a context is configured via `set_context()`, all database functions work with no arguments —
the URL and pool settings are read from the context:

```python
from aignostics_foundry_core.database import init_engine, cli_run_with_db, with_engine

# Zero-arg engine init — reads MYPROJECT_DB_URL, _DB_POOL_SIZE, etc. from env
init_engine()

# CLI helper — initialises engine, runs coroutine, disposes engine
cli_run_with_db(my_async_func)


# Background job decorator — engine initialised before each invocation
@with_engine
async def my_job(): ...


# Override for a secondary database
@with_engine(db_url="postgresql+asyncpg://user:pass@host/secondary")
async def my_other_job(): ...
```

In tests, construct `DatabaseSettings` directly instead of setting env vars:

```python
from aignostics_foundry_core.database import DatabaseSettings
from tests.conftest import make_context

ctx = make_context(database=DatabaseSettings(_env_prefix="TEST_DB_", url="sqlite+aiosqlite:///test.db"))
```

#### Authentication (`{PREFIX}AUTH_`)

Settings class: `AuthSettings`. All fields are optional with defaults unless `enabled=True`, which
activates several cross-field requirements. Only needed when using
`aignostics_foundry_core.api.auth` dependencies.

| Variable | Required | Default | Description |
|---|---|---|---|
| `{PREFIX}AUTH_ENABLED` | no | `false` | Enable Auth0 authentication. When `true`, several other fields become required. |
| `{PREFIX}AUTH_SESSION_ENABLED` | when enabled | `false` | Enable session cookies. Required when `AUTH_ENABLED=true`. |
| `{PREFIX}AUTH_SESSION_SECRET` | when session enabled | `""` | Secret to sign session cookies. Required when `AUTH_SESSION_ENABLED=true`. |
| `{PREFIX}AUTH_SESSION_EXPIRATION` | no | `86400` | Session cookie expiration in seconds (range: 61–31536000). |
| `{PREFIX}AUTH_DOMAIN` | when enabled | `""` | Auth0 domain (e.g. `myapp.eu.auth0.com`). Required when `AUTH_ENABLED=true`. |
| `{PREFIX}AUTH_CLIENT_ID` | when enabled | `""` | Auth0 client ID (max 32 chars). Required when `AUTH_ENABLED=true`. |
| `{PREFIX}AUTH_CLIENT_SECRET` | when enabled | `""` | Auth0 client secret (64 chars). Required when `AUTH_ENABLED=true`. |
| `{PREFIX}AUTH_INTERNAL_ORG_ID` | when enabled | `""` | Auth0 organization ID identifying the internal org (used by `require_internal`). Required when `AUTH_ENABLED=true`. |
| `{PREFIX}AUTH_ROLE_CLAIM` | when enabled | `""` | JWT claim name containing the user's role (e.g. `https://myapp.example.com/roles`). Required when `AUTH_ENABLED=true`. |

#### Console

Read directly from the environment — no settings class.

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}CONSOLE_WIDTH` | auto-detect | Override Rich console width (integer, characters). Defaults to terminal width or 80 in non-TTY environments. |

## Further Reading

- [Foundry Project Guide](FOUNDRY_README.md) - Complete toolchain, testing, CI/CD, and project setup guide
- [Security policy](SECURITY.md) - Documentation of security checks, tools, and principles
- [Release notes](https://github.com/aignostics/foundry-python-core/releases) - Complete log of improvements and changes
- [Attributions](ATTRIBUTIONS.md) - Open source projects this project builds upon
