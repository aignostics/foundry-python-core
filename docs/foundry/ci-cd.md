> [!NOTE]
> This file is maintained by the foundry-python template and will be updated when you run `mise run update_from_template`.

# CI/CD Workflows

## Main Workflows

| Workflow | Triggers | Purpose |
|----------|----------|---------|
| `ci-cd.yml` | PR, push to `main`, version tags | lint → audit → test → publish |
| `git-conventions.yml` | PR | Validates branch names, commit messages, and PR titles |
| `mise-lock-sync.yml` | PR (mise config changes) | Verifies `mise.lock` is up to date; fails with remediation instructions if not (no auto-commit) |
| `check-action-pins.yml` | PR (workflow file changes) | Ensures all action pins have SHA + version comment |
| `labels-sync.yml` | Push to main | Syncs GitHub labels from `.github/labels.yml` |
| `claude-code-automation-pr-review.yml` | PR with `claude` label | AI-powered PR review |
| `audit-scheduled.yml` | Daily 6 AM UTC | Security audit with BetterStack heartbeat |
| `codeql-scheduled.yml` | Weekly (Tue 3:22 AM UTC) | CodeQL security scanning |

## Reusable Workflows

| Workflow | Purpose |
|----------|---------|
| `_lint.yml` | Ruff, PyRight |
| `_test.yml` | Unit, integration, E2E tests with coverage |
| `_audit.yml` | Security scanning and SBOM generation |
| `_package-publish.yml` | Build, document, publish to Artifact Registry, Slack notification |
| `_codeql.yml` | CodeQL analysis (Python + Actions) |


## Skipping Tests in CI

Add to commit message or PR labels:

| Skip Marker | Effect |
|-------------|--------|
| `skip:test:unit` | Skip unit tests |
| `skip:test:integration` | Skip integration tests |
| `skip:test:e2e` | Skip E2E tests |
| `skip:test:all` | Skip all tests |

---

## Versioning & Releases

### Creating a Release

```shell
git switch main && git pull    # Ensure you're on latest main
mise run bump                  # Interactive: auto-detects bump type from commits
```

### Explicit Version Control

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

## Release Task Reference

| Task | Description |
|------|-------------|
| `mise run bump` | Interactive version bump (accepts [cz bump arguments](https://commitizen-tools.github.io/commitizen/bump/)) |
| `mise run update_from_template` | Update project from the latest foundry-python template |

---

## Keeping Updated

```shell
mise run update_from_template
```

This updates your project with the latest template improvements while preserving:
- `README.md`
- `CHANGELOG.md`
- `logo.png`
