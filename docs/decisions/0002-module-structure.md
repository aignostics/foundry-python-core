# 2. Module structure

Date: 2026-03-24

## Status

Accepted

## Context

We need to decide how to structure the internal modules of `aignostics_foundry_core`. Three options were considered:

**#1 Private modules with package-level exports**
```
aignostics_foundry_core/
├── __init__.py   # exposes Health class
└── _health.py    # contains Health class
```
Import: `from aignostics_foundry_core import Health`
Pros: matches Bridge/Python SDK conventions.
Cons: top-level `__init__.py` exports grow very long; hard to know which submodule an object comes from.

**#2 Public modules**
```
aignostics_foundry_core/
├── __init__.py
└── health.py     # contains and exposes Health class
```
Import: `from aignostics_foundry_core.health import Health`
Pros: simple; can be migrated to #3 without breaking imports if needed.
Cons: modules cannot hide implementation details; everything in a module is public.

**#3 Public modules with module-level exports**
```
aignostics_foundry_core/
├── __init__.py
└── health/
    ├── __init__.py   # exposes Health class
    └── _health.py    # contains Health class
```
Import: `from aignostics_foundry_core.health import Health`
Pros: modules can control what they advertise.
Cons: overhead (one directory + one file per module); migration from #2 is non-breaking if needed.

## Decision

We will use **#2 (public modules)**. Each concept lives in a single public module file, and is imported directly from that module.

## Consequences

- Module structure is simple and easy to navigate.
- All symbols in a module file are implicitly public; internal helpers should be prefixed with `_` by convention.
- If a module later needs to hide implementation details (e.g. a complex subpackage), it can be migrated to option #3 without breaking existing imports, since the import path `from aignostics_foundry_core.health import Health` is stable across both structures.
