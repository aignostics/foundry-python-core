> [!NOTE]
> This file is maintained by the foundry-python template and will be updated when you run `mise run update_from_template`.
> For project-specific documentation, use README.md instead.

# Foundry Project Guide

This guide provides comprehensive documentation for your Foundry-scaffolded project.

## Table of Contents

- [Toolchain Overview](#toolchain-overview)
- [Quick Start](#quick-start)
- [Service Connections](#service-connections)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [CI/CD Workflows](#cicd-workflows)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Task Reference](#task-reference)
- [Versioning & Releases](#versioning--releases)
- [Keeping Updated](#keeping-updated)
- [Troubleshooting](#troubleshooting)
- [Feedback](#feedback)
- [Further Reading](#further-reading)

---

## Toolchain Overview

This project was scaffolded using [foundry-python](https://github.com/aignostics/foundry-python) with [Copier](https://copier.readthedocs.io/), applying enterprise-grade operational excellence practices:

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

## Quick Start

### 1. Configure Service Connections

> **IMPORTANT**: **ALL** service connections **MUST** be configured before proceeding. GitHub workflows will fail without them.

Complete the entire [Service Connections](#service-connections) section now.

### 2. Verify Installation

```shell
mise run install
mise run test
```

All tests should pass. If not, run `mise run install` first.

### 3. Create Initial Commit

```shell
git add .
git commit -m "chore: initial commit"
```

### 4. Push to GitHub

> **Prerequisite**: Create an empty repository at github.com/aignostics/foundry-python-core

```shell
git remote add origin git@github.com:aignostics/foundry-python-core.git
git push -u origin main
```

---

## Service Connections

| Service | Purpose |
|---------|---------|
| [GitHub Settings](#github-repository-settings) | Security alerts, Dependabot |
| [Google Artifact Registry](#google-artifact-registry) | Package publishing |
| [SonarCloud](#sonarcloud) | Code quality analysis |
| [Renovate](#renovate) | Dependency updates |
| [CodeCov](#codecov) | Coverage reporting |
| [Sentry](#sentry) | Error monitoring |
| [Ox Security](#ox-security) | Supply chain security |
| [CodeQL](#codeql) | Security scanning |
| [Claude Code CI](#claude-code-in-ci) | AI PR reviews |
| [Slack](#slack-release-notifications) | Release notifications |

### GitHub Repository Settings

**Why**: Ensures dependency vulnerability scanning is active.

Dependabot alerts and security updates are managed at the GitHub Enterprise level and enabled by default for all repositories. No manual configuration is needed.

1. Go to https://github.com/aignostics/foundry-python-core/settings/security_analysis
2. Verify **Dependabot alerts** is enabled (should be on by default via enterprise policy)
3. Verify **Dependabot security updates** is enabled (should be on by default via enterprise policy)
4. Do **NOT** enable Dependabot version updates (Renovate handles this)
5. (Public repos only) Enable **Private vulnerability reporting** to allow external security researchers to report vulnerabilities privately

**Verify**: Security tab shows "Dependabot alerts enabled"

### Google Artifact Registry

**Why**: Allows CI to publish Python packages.

1. Add your repository to the `github_repositories` list in [this file](https://gitlab.aignostics.com/aignx/infrastructure/-/blob/main/terragrunt/projects/shared-tools/regions/global/workload-identity-federation/aignx-python-library-repos-github-oidc-pool/terragrunt.hcl); follow the [usual process](https://gitlab.aignostics.com/aignx/infrastructure/-/blob/main/CONTRIBUTING.md) to apply the Terragrunt changes
    * Example MR [here](https://gitlab.aignostics.com/aignx/infrastructure/-/merge_requests/2311)
2. Go to https://github.com/aignostics/foundry-python-core/settings/secrets/actions/new and create a new repository secret called `GCP_WORKLOAD_IDENTITY_PROVIDER` with value `projects/359433074524/locations/global/workloadIdentityPools/github-python-library-repos/providers/github-provider`

**Verify**: CI publish job succeeds on version tags

### SonarCloud

**Why**: Automated code quality and security analysis.

> **Note**: Requires SonarCloud admin access. Ask your team lead if needed.

1. Go to https://sonarcloud.io/projects/create, select your new repo and click "Set Up"
2. Select Previous Code when prompted
3. Go to https://sonarcloud.io/project/settings?id=aignostics_foundry-python-core and select "Administration > Analysis Method" in the left menu; disable Automatic Analysis
4. To fix badges for private repositories:
    * Go to https://sonarcloud.io/project/information?id=aignostics_foundry-python-core, scroll to the bottom of the "Badges" and select the `token` value in the URL; replace `SONAR_BADGE_TOKEN` in your README.md with the generated token

**Verify**: Quality Gate badge shows status in README after CI runs

### Renovate

**Why**: Automated dependency updates with smart grouping.

| Tool | Responsibility |
|------|----------------|
| [Renovate](https://github.com/apps/renovate) | Version updates (Python, GitHub Actions), lock file maintenance |
| [Dependabot](https://docs.github.com/en/code-security/dependabot) | Security alerts and updates (including transitive dependencies) |

This separation ensures we get Renovate's superior update grouping and scheduling while retaining Dependabot's ability to detect and fix vulnerabilities in transitive dependencies.

1. Go to https://developer.mend.io and sign in with your GitHub account
2. Go to https://developer.mend.io/github/aignostics/foundry-python-core and click "Action > Run Renovate scan" to trigger the initial scan
3. Renovate creates a [Dependency Dashboard](https://github.com/aignostics/foundry-python-core/issues?q=is%3Aissue%20state%3Aopen%20Dependency%20Dashboard) as an issue in your repository

**Verify**: Dependency Dashboard issue appears in your repository

### CodeCov

**Why**: Code coverage tracking and PR comments.

CodeCov is automatically enabled for new repositories via organization-level configuration. No setup is required for coverage uploads.

**Badge setup** (for private repositories):

1. Go to https://app.codecov.io/gh/aignostics/foundry-python-core/config/badge
2. Under "Embed via API", copy the token value from the URL
3. In your `README.md`, replace `CODECOV_BADGE_TOKEN` with the copied token

**Verify**: Coverage badge shows percentage in README after CI runs

### Sentry

**Why**: Error monitoring and performance profiling.

Sentry automatically scans code changes when you open PRs if organization-wide integration is configured. No additional setup required for basic functionality.

For advanced setup (error tracking, profiling), configure the Sentry DSN in your application.

### Ox Security

**Why**: Supply chain security scanning.

Ox automatically scans code changes when you open PRs if organization-wide integration is configured. No additional setup required.

### CodeQL

**Why**: Static analysis for security vulnerabilities (SQL injection, XSS, path traversal, etc.).

CodeQL is configured automatically via the included workflow files. No manual setup is required.

**Schedule**: Runs weekly on Tuesdays at 3:22 AM UTC

**Verify**: After first scheduled run, check Security tab → Code scanning alerts

### Claude Code in CI

**Why**: AI-powered PR reviews.

1. Go to https://platform.claude.com/settings/keys
2. Click "Create Key" and give it a descriptive name (e.g., "github-foundry-python-core")
3. Copy the generated API key to your clipboard (you won't be able to see it again)
4. Go to https://github.com/aignostics/foundry-python-core/settings/secrets/actions/new and create a new repository secret called `ANTHROPIC_API_KEY`, pasting the key from your clipboard

**Verify**: Add the `claude` label to a PR to trigger AI review


### Repository Polish

**Why**: Better discoverability and branding.

1. Go to https://github.com/aignostics/foundry-python-core
2. Click on the cogs icon in the top right corner next to about
3. Copy the description from the pyproject.toml file into the description field
4. Copy up to 20 tags from the pyproject.toml file into the topics field
5. Go to https://github.com/aignostics/foundry-python-core/settings and upload a social media image (e.g. logo.png) into the "Social preview" field




---

## Testing

### Test Markers

Every test **MUST** have a category marker. Tests without markers won't run in CI.

| Marker | Command | Purpose |
|--------|---------|---------|
| `@pytest.mark.unit` | `mise run test_unit` | Isolated tests, all dependencies mocked, must pass offline |
| `@pytest.mark.integration` | `mise run test_integration` | Real local services (Docker), mocked external APIs |
| `@pytest.mark.e2e` | `mise run test_e2e` | Real external services, full workflows |
| `@pytest.mark.scheduled` | `mise run test_scheduled` | Tests run on schedule (also included in regular runs) |
| `@pytest.mark.sequential` | `mise run test_sequential` | Tests excluded from parallel execution |

### Running Tests

```shell
# By category
mise run test_unit              # Fast, isolated (serial execution)
mise run test_integration       # Real services (20% parallel)
mise run test_e2e               # Full parallel

# All tests
mise run test           # Runs unit → integration → e2e

# Specific test
pytest tests/path/to/test.py::test_function -v
```

### Test Parallelization

Controlled by `XDIST_WORKER_FACTOR` environment variable:

| Test Type | Factor | Behavior |
|-----------|--------|----------|
| Unit | 0.0 | Serial (parallelization overhead > benefit) |
| Integration | 0.2 | 20% of logical CPUs |
| E2E | 1.0 | 100% of logical CPUs (I/O bound) |

### Coverage

- **Goal**: 100%
- **Minimum**: 85%
- **Reports**: `reports/coverage.xml`, `reports/coverage.md`, `reports/coverage_html/`

### Finding Unmarked Tests

```shell
pytest --collect-only -m "not unit and not integration and not e2e" -q
```

---

## Code Quality

### Linting & Type Checking

```shell
mise run lint   # Runs Ruff + PyRight
```

| Tool | Mode | Purpose |
|------|------|---------|
| Ruff | Format + Lint | Code style, 120 char limit, Google-style docstrings |
| PyRight | Strict | Type checking (all code) |

### Security & Compliance

```shell
mise run audit   # Runs all security checks
```

| Tool | Purpose | Output |
|------|---------|--------|
| pip-audit | Vulnerability scanning | `reports/pip-audit.json` |
| pip-licenses | License compliance | `reports/licenses.csv`, `reports/licenses.json` |
| cyclonedx-py | CycloneDX SBOM | `reports/sbom.json` |
| trivy | SPDX SBOM + CVE scanning | `reports/trivy-sbom.spdx.json` |

---

## CI/CD Workflows

### Main Workflows

| Workflow | Triggers | Purpose |
|----------|----------|---------|
| `ci-cd.yml` | PR, push to main, version tags | Main pipeline: lint → audit → test → publish |
| `git-conventions.yml` | PR | Validates branch names, commit messages, and PR titles |
| `labels-sync.yml` | Push to main | Syncs GitHub labels from `.github/labels.yml` |
| `claude-code-automation-pr-review.yml` | PR with `claude` label | AI-powered PR review |
| `audit-scheduled.yml` | Daily 6 AM UTC | Security audit with BetterStack heartbeat |
| `codeql-scheduled.yml` | Weekly (Tue 3:22 AM UTC) | CodeQL security scanning |

### Reusable Workflows

| Workflow | Purpose |
|----------|---------|
| `_lint.yml` | Ruff, PyRight |
| `_test.yml` | Unit, integration, E2E tests with coverage |
| `_audit.yml` | Security scanning and SBOM generation |
| `_package-publish.yml` | Build, document, publish to Artifact Registry, Slack notification |
| `_codeql.yml` | CodeQL analysis (Python + Actions) |

### Scheduled Tests

| Workflow | Schedule | Environment |
|----------|----------|-------------|
| `test-scheduled-staging-hourly.yml` | Hourly | Staging |
| `test-scheduled-staging-daily.yml` | Daily 12 PM UTC | Staging |
| `test-scheduled-production-hourly.yml` | Hourly | Production |
| `test-scheduled-production-daily.yml` | Daily 12 PM UTC | Production |

### Skipping Tests in CI

Add to commit message or PR labels:

| Skip Marker | Effect |
|-------------|--------|
| `skip:test:unit` | Skip unit tests |
| `skip:test:integration` | Skip integration tests |
| `skip:test:e2e` | Skip E2E tests |
| `skip:test:all` | Skip all tests |

---

## Pre-commit Hooks

### Automatic Hooks (pre-commit stage)

| Hook | Purpose |
|------|---------|
| ruff | Format and lint code |
| pyright | Strict type checking |
| detect-secrets | Scan for exposed credentials |
| uv-lock | Keep uv.lock synchronized |
| check-toml, check-xml | Validate config file syntax |
| debug-statements | Find leftover debugger calls (pdb, breakpoint) |
| end-of-file-fixer | Ensure files end with newline |
| trailing-whitespace | Remove trailing whitespace |

### Pre-push Hooks

| Hook | Purpose |
|------|---------|
| docs | Generate ATTRIBUTIONS.md |
| test-unit | Run unit tests before push |

### Commit Message Validation

Uses Commitizen to enforce [conventional commits](https://www.conventionalcommits.org/):

```
type(scope): description

# Examples:
feat(api): add user authentication
fix(parser): handle edge case in date parsing
docs(readme): update installation instructions
chore(deps): update dependencies
```

### Manual Hook Execution

```shell
mise run pre_commit_run_all   # Run all hooks on entire codebase
```

---

## Task Reference

### Passing Arguments to Tasks

Some tasks accept arguments. Use `--` to separate mise options from task arguments:

```shell
mise run <task> -- <arguments>
```

For example, to see help for the bump task:

```shell
mise run bump -- --help
```

Tasks that accept arguments define them using mise's [usage field](https://mise.jdx.dev/tasks/task-arguments.html), which provides built-in help and validation.

### Setup & Installation

| Task | Description |
|------|-------------|
| `mise run install` | Sync all dependencies (`uv sync --all-extras`) + install pre-commit hooks |
| `mise run setup` | Post-generation environment setup |
| `mise run clean` | Remove all build artifacts and caches |

### Code Quality

| Task | Description |
|------|-------------|
| `mise run lint` | Run Ruff, PyRight |
| `mise run audit` | Security scanning + SBOM generation |
| `mise run docs` | Generate ATTRIBUTIONS.md |


### Testing

| Task | Description |
|------|-------------|
| `mise run test` | Run all tests (unit → integration → e2e) |
| `mise run test_unit` | Unit tests only (serial) |
| `mise run test_integration` | Integration tests (20% parallel) |
| `mise run test_e2e` | E2E tests (full parallel) |
| `mise run test_scheduled` | Scheduled tests only |
| `mise run test_sequential` | Non-parallelizable tests |
| `mise run test_coverage_reset` | Clear coverage data |

### Release Management

| Task | Description |
|------|-------------|
| `mise run bump` | Interactive version bump (accepts [cz bump arguments](https://commitizen-tools.github.io/commitizen/bump/)) |
| `mise run update_from_template` | Update from Foundry template |

### Utilities

| Task | Description |
|------|-------------|
| `mise run all` | Full validation: lint + test + docs + audit |
| `mise run act` | Run GitHub Actions locally with act |
| `mise run pre_commit_run_all` | Run all pre-commit hooks on all files |

---

## Versioning & Releases

### Creating a Release

```shell
git switch main && git pull    # Ensure you're on latest main
mise run docs                  # Regenerate documentation
mise run bump                  # Interactive: auto-detects bump type from commits
```

#### Explicit Version Control

Pass arguments to `cz bump` using `--`:

```shell
# Explicit increment type
mise run bump -- --increment patch
mise run bump -- --increment minor
mise run bump -- --increment major

# Pre-release versions
mise run bump -- --prerelease rc           # e.g., 1.0.0 → 1.0.1-rc.0
mise run bump -- --increment major --prerelease rc  # e.g., 1.0.0 → 2.0.0-rc.0

# Dry run (preview without changes)
mise run bump -- --dry-run

# See all options
mise run bump -- --help
```

The `mise run bump` command:
1. Bumps version using Commitizen
2. Updates CHANGELOG.md
3. Creates git tag
4. Pushes to remote (triggers publish workflow)

### Conventional Commits

Commits must follow the format for automatic changelog generation:

| Type | Version Bump | Example |
|------|--------------|---------|
| `feat:` | Minor | `feat(api): add user endpoint` |
| `fix:` | Patch | `fix(auth): handle expired tokens` |
| `feat!:` or `BREAKING CHANGE:` | Major | `feat!: redesign API response format` |
| `docs:`, `chore:`, `refactor:`, `test:` | None | `docs: update README` |

**Changelog inclusion**: The following commit types appear in the generated changelog: `feat`, `fix`, `refactor`, `perf`, `chore`, `docs`. Other types (`test`, `ci`, `style`, `build`) are excluded from the changelog but still valid for commits.

---

## Keeping Updated

```shell
mise run update_from_template
```

This updates your project with the latest template improvements while preserving:
- `README.md`
- `CHANGELOG.md`
- `ATTRIBUTIONS.md`
- `logo.png`

---

## Troubleshooting

### CI Fails After Initial Push

**Cause**: Required services not configured.

**Solution**: Complete all sections in [Service Connections](#service-connections).

### Missing Secret Errors

**Cause**: Repository secrets not configured.

**Solution**: Add required secrets at https://github.com/aignostics/foundry-python-core/settings/secrets/actions:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `SONAR_TOKEN`

### Tests Not Running in CI

**Cause**: Tests missing category marker.

**Solution**: Add `@pytest.mark.unit`, `@pytest.mark.integration`, or `@pytest.mark.e2e` to each test.

### Pre-commit Hook Failures

**Cause**: Code doesn't meet quality standards.

**Solution**: Many hooks auto-fix issues. Re-stage files and commit:
```shell
git add <fixed-files>
git commit
```

### Coverage Dropping

**Cause**: New code not covered by tests.

**Solution**: Add tests for new code, or verify new tests have category markers.

### Commit Message Rejected

**Cause**: Message doesn't follow conventional commit format.

**Solution**: Use format `type(scope): description`. Valid types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `ci`.

---

## Feedback

Happy to hear from you if you have any feedback on the DX/UX of using `foundry-python`.
Please reach out to us on [Slack](https://aignostics.slack.com/archives/C0AEY02UQD6).

---

## Further Reading

- [README.md](README.md) - Project documentation
- [CODE_STYLE.md](CODE_STYLE.md) - Code style guide
- [SECURITY.md](SECURITY.md) - Security policy
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
