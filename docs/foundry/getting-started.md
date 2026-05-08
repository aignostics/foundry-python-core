> [!NOTE]
> This file is maintained by the [foundry-python](https://github.com/aignostics/foundry-python) template and will be updated when you run `mise run update_from_template`.

# Getting Started: Foundry Python Core

This getting started guide covers everything needed to get this project fully operational.

## Toolchain

This project was scaffolded using [foundry-python](https://github.com/aignostics/foundry-python):

| Category | Tools |
|----------|-------|
| **Code Quality** | [Ruff](https://github.com/astral-sh/ruff) (linting), [PyRight](https://github.com/microsoft/pyright) (type checking) |
| **Git Hooks** | [pre-commit](https://pre-commit.com/), [detect-secrets](https://github.com/Yelp/detect-secrets), [pygrep](https://github.com/pre-commit/pygrep-hooks), [Commitizen](https://commitizen-tools.github.io/commitizen/) |
| **Testing** | [pytest](https://docs.pytest.org/) (parallel execution), [Nox](https://nox.thea.codes/) (matrix testing), [Codecov](https://codecov.io/) (coverage) |
| **CI/CD** | [GitHub Actions](https://github.com/features/actions) (workflows), [act](https://github.com/nektos/act) (local testing) |
| **Security** | [SonarQube](https://www.sonarsource.com/products/sonarcloud), [pip-audit](https://pypi.org/project/pip-audit/), [trivy](https://trivy.dev/), [Dependabot](https://docs.github.com/en/code-security/getting-started/dependabot-quickstart-guide) |
| **Dependencies** | [Renovate](https://github.com/renovatebot/renovate) (updates), [pip-licenses](https://pypi.org/project/pip-licenses/) (compliance) |
| **Observability** | [Sentry](https://sentry.io/) (errors, tracing, profiling), [BetterStack](https://betterstack.com/) (uptime monitoring) |
| **Documentation** | SBOM generation ([CycloneDX](https://cyclonedx.org/), [SPDX](https://spdx.dev/)), auto-generated attributions, dynamic badges |
| **AI Assistance** | [GitHub Copilot](https://docs.github.com/en/copilot) (custom instructions), [Claude Code](https://docs.claude.com/en/docs/claude-code/github-actions) (PR reviews) |

---

## Verify Installation

Before configuring services, confirm the local environment is working:

```shell
mise run install
mise run test
```

All tests should pass. If not, run `mise run install` first.

---

## Service Connections

| Service | Purpose | Status |
|---------|---------|--------|
| [GitHub Repository Settings](#github-repository-settings) | Security alerts, Dependabot | |
| [Google Artifact Registry](#google-artifact-registry) | Package publishing | |
| [SonarCloud](#sonarcloud) | Code quality analysis | |
| [Renovate](#renovate) | Dependency updates | |
| [CodeCov Badge](#codecov-badge) | Coverage badge | |
| [Sentry](#sentry--advanced-setup) | Error monitoring | |
| [Repository Polish](#repository-polish) | Discoverability | |
| [Slack Release Notifications](#slack-release-notifications) | Release notifications | |
| [Background Worker](#background-worker) | Chancy job queue | |

---

## GitHub Repository Settings

**Why**: Ensures dependency vulnerability scanning is active.

1. Go to https://github.com/aignostics/foundry-python-core/settings/security_analysis
2. Verify **Dependabot alerts** is enabled (on by default via enterprise policy)
3. Verify **Dependabot security updates** is enabled (on by default via enterprise policy)
4. Do **NOT** enable Dependabot version updates — Renovate handles this
5. (Public repos only) Enable **Private vulnerability reporting**



### Google Artifact Registry

**Why**: Allows CI to access our private Python registry.

1. Add your repository to the `github_repositories` list in [this file](https://github.com/aignostics/infrastructure/blob/main/terragrunt/projects/shared-tools/regions/global/workload-identity-federation/aignx-python-library-repos-github-oidc-pool/terragrunt.hcl); follow the [usual process](https://github.com/aignostics/infrastructure/blob/main/CONTRIBUTING.md) to apply the Terragrunt changes
    * Example PR [here](https://github.com/aignostics/infrastructure/pull/2366)
2. Go to https://github.com/aignostics/foundry-python-core/settings/secrets/actions/new and create a new repository secret called `GCP_WORKLOAD_IDENTITY_PROVIDER` with value `projects/359433074524/locations/global/workloadIdentityPools/github-python-library-repos/providers/github-provider`

**Verify**: the `Setup Dev Environment` action succeeds in lint, test or audit workflow

---

### SonarCloud

> **Note**: Requires SonarCloud admin access. Your team lead should have admin access; if not, ask in [#topic-foundry](https://aignostics.slack.com/archives/C0AEY02UQD6).

1. Go to https://sonarcloud.io/projects/create, select your new repo and click "Set Up"
2. Select **Previous Code** when prompted
3. Go to https://sonarcloud.io/project/settings?id=aignostics_foundry-python-core → **Administration > Analysis Method** → disable **Automatic Analysis**
4. For private repositories — update the quality badge in `README.md`:
    * Go to https://sonarcloud.io/project/information?id=aignostics_foundry-python-core, scroll to **Badges**, copy the token from the URL, replace `SONAR_BADGE_TOKEN` in your `README.md`

### CodeCov Badge

For private repositories, the badge URL requires a token:

1. Go to https://app.codecov.io/gh/aignostics/foundry-python-core/config/badge
2. Under "Embed via API", copy the token value from the URL
3. In your `README.md`, replace `CODECOV_BADGE_TOKEN` with the copied token

---

## After Merging — Complete the Setup

The following do not block this PR. Complete them after merge to finish the project setup.

### Automated — No Action Required

These services are active automatically at the organisation level:

| Service | Purpose | Notes |
|---------|---------|-------|
| [SonarCloud](https://sonarcloud.io/project/overview?id=aignostics_foundry-python-core) | Code quality & security analysis | `SONAR_TOKEN` is org-wide; quality gate runs on every PR |
| [Sentry](https://sentry.io/) | Error monitoring | Org-level integration; scans PRs automatically |
| [Ox Security](https://app.ox.security/) | Supply chain security | Org-level integration; scans PRs automatically |
| [CodeQL](https://github.com/aignostics/foundry-python-core/security/code-scanning) | Static security analysis | Runs weekly (Tuesdays 3:22 AM UTC) via included workflow |
| [CodeCov](https://app.codecov.io/gh/aignostics/foundry-python-core) | Coverage tracking & PR comments | Org-level; coverage uploads automatic |
| [Dependabot](https://github.com/aignostics/foundry-python-core/settings/security_analysis) | Dependency vulnerability alerts | Enabled by default via enterprise policy |
| [Claude Code](https://github.com/aignostics/foundry-python-core/actions) | AI-powered PR reviews (`claude` label) | `ANTHROPIC_API_KEY` is org-wide; no setup required |

### Renovate

**Why**: Automated dependency updates with smart grouping and scheduling (complements Dependabot which handles security patches).

1. Go to https://developer.mend.io and sign in with your GitHub account
2. Go to https://developer.mend.io/github/aignostics/foundry-python-core and click **Action > Run Renovate scan**
3. Renovate creates a [Dependency Dashboard](https://github.com/aignostics/foundry-python-core/issues?q=is%3Aissue%20state%3Aopen%20Dependency%20Dashboard) issue in your repository

**Verify**: Dependency Dashboard issue appears in your repository

### Sentry — Advanced Setup

For error tracking, performance profiling, and release tracking, configure the Sentry DSN in your application code. Basic PR scanning is already active at the org level.

### Repository Polish

1. Go to https://github.com/aignostics/foundry-python-core
2. Click the cogs icon next to "About"
3. Copy the description from `pyproject.toml` into the description field
4. Copy up to 20 tags from `pyproject.toml` into the topics field
5. Go to https://github.com/aignostics/foundry-python-core/settings and upload a social preview image (e.g. `logo.png`)

### Slack Release Notifications

**Why**: Notifies [#announce-foundry](https://aignostics.slack.com) when a new version is published.

No secrets needed — the Slack webhook is configured at the org level. No action required; verify by publishing a release.


---

## Background Worker

This project includes a [Chancy](https://chancy.readthedocs.io/) background worker powered by PostgreSQL.

### What was scaffolded

- `src/foundry_python_core/scheduler/` — the scheduler module (service, CLI, API, settings)
- `src/foundry_python_core/hello_world/_jobs.py` and `src/foundry_python_core/system/_jobs.py` — example job definitions
- `migrations/versions/0002_add_scheduler_heartbeats.py` — database migration for the heartbeat table
- `deployment/cloudrun/service-worker.template.yaml` — Cloud Run worker service definition

### Run the worker locally

Start everything with Docker Compose (the worker service starts alongside the API and PostgreSQL):

```shell
docker compose up
```

Or run the worker directly:

```shell
# Apply the scheduler database migration first
uv run foundry-python-core scheduler db migrate

# Register job definitions
uv run foundry-python-core scheduler joblets register

# Start the worker
uv run foundry-python-core scheduler execute
```

The Chancy web UI is available at `http://127.0.0.1:8001` by default (configurable via `FOUNDRY_PYTHON_CORE_SCHEDULER_API_HOST` and `FOUNDRY_PYTHON_CORE_SCHEDULER_API_PORT`).

### Database migration

The scheduler requires its own migration to create the heartbeat table. This runs automatically at startup in production (see `deployment/cloudrun/service.template.yaml`). Locally, run:

```shell
uv run foundry-python-core scheduler db migrate
```

---

## Further Reading

- [docs/foundry/testing.md](testing.md) - Test markers, running tests, coverage
- [docs/foundry/ci-cd.md](ci-cd.md) - CI/CD workflows, releases, versioning
- [docs/foundry/code-quality.md](code-quality.md) - Linting, pre-commit hooks, task reference
- [docs/foundry/troubleshooting.md](troubleshooting.md) - Common issues and solutions
