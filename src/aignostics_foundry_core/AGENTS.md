# CLAUDE.md - Foundry Python Core Package Overview

This file provides an overview of all modules in `aignostics_foundry_core`, their features, and interactions.

## Module Index

<!-- Document your modules in a table format. Customize columns based on your architecture. -->

| Module | Purpose | Description |
|--------|---------|-------------|
| **greet** | Example module | Provides greeting functionality |

## Module Descriptions

<!-- For each module, document its purpose, features, dependencies, and usage. -->

### greet

**Greeting functionality for Foundry Python Core**

- **Purpose**: Provides greeting utilities
- **Key Features**: Simple greeting with logging
- **Location**: `aignostics_foundry_core/greet.py`

<!-- Add descriptions for additional modules as you develop them -->

## Architecture

<!-- Document your package's architecture here. Consider including:
- Module dependency diagrams
- Data flow patterns
- Key abstractions and interfaces
- Integration points
-->

```text
<!-- Example architecture diagram (customize for your project):

┌─────────────────────────────┐
│     Your Application        │
└──────────────┬──────────────┘
               │
┌──────────────┴──────────────┐
│      aignostics_foundry_core      │
├─────────────────────────────┤
│  module_a  │  module_b  │   │
└─────────────────────────────┘
-->
```

## Usage Examples

<!-- Document common usage patterns for your package -->

```python
from aignostics_foundry_core import greet

# Example usage
result = greet("World")
print(result)  # Hello, World!
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
