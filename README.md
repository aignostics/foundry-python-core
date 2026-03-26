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

> [!NOTE]
> This is your project README - please feel free to update as you see fit.
> For first steps after scaffolding, check out [FOUNDRY_README.md](FOUNDRY_README.md).

---

Foundational infrastructure for Foundry components.

## Prerequisites

Install [mise](https://mise.jdx.dev/) (task runner and dev tool manager):

```shell
brew install mise
```

Or follow the [installation guide](https://mise.jdx.dev/getting-started.html) for other methods. Then [activate mise](https://mise.jdx.dev/getting-started.html#activate-mise) in your shell profile.

## Usage

```python
from aignostics_foundry_core.health import Health, HealthStatus

health = Health(status=HealthStatus.UP)
```

## Further Reading

- [Foundry Project Guide](FOUNDRY_README.md) - Complete toolchain, testing, CI/CD, and project setup guide
- [Security policy](SECURITY.md) - Documentation of security checks, tools, and principles
- [Release notes](https://github.com/aignostics/foundry-python-core/releases) - Complete log of improvements and changes
- [Attributions](ATTRIBUTIONS.md) - Open source projects this project builds upon
