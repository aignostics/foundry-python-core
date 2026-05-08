> [!NOTE]
> This file is maintained by the foundry-python template and will be updated when you run `mise run update_from_template`.

# Code Quality

## Linting & Type Checking

```shell
mise run lint   # Runs Ruff + PyRight
```

| Tool | Mode | Purpose |
|------|------|---------|
| Ruff | Format + Lint | Code style, 120 char limit, Google-style docstrings |
| PyRight | Strict | Type checking (all code) |

## Security & Compliance

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
| `mise run attributions` | Generate `reports/ATTRIBUTIONS.md` (also uploaded as CI artifact) |



### Attribution Generation

`mise run attributions` generates `reports/ATTRIBUTIONS.md` — a list of all third-party open source packages used by this project, with their licenses. This file is not committed to the repository; it is generated in CI as part of the audit and uploaded as a build artifact.

To generate it locally:

```shell
mise run attributions
# Output: reports/ATTRIBUTIONS.md
```

### Utilities

| Task | Description |
|------|-------------|
| `mise run all` | Full validation: lint + test + attributions + audit |
| `mise run act` | Run GitHub Actions locally with act |
| `mise run pre_commit_run_all` | Run all pre-commit hooks on all files |

### Passing Arguments to Tasks

Some tasks accept arguments. Use `--` to separate mise options from task arguments:

```shell
mise run <task> -- <arguments>
```

For example, to preview a version bump without making changes:

```shell
mise run bump -- --dry-run
```
