# 5. GUI page registration

Date: 2026-04-08

## Status

Accepted

## Context

Library consumers need to register NiceGUI pages with a frame that displays a consistent header,
navigation sidebar, and health status bar. The frame function is inherently tied to the service,
meaning it cannot be defined in a generic library like foundry-core.

The previous implementation relied on library consumers creating `gui = GUINamespace(frame_func=frame)` in
their service. Since this library replaces the foundational components for services, there is no natural
place to do this. In Bridge, this `GUINamespace` would be created in the system module and imported
into other modules, violating domain boundaries.

### Alternatives considered

**Option A — Deferred singleton in foundry-core**: Add `gui = GUINamespace()` to
`aignostics_foundry_core.gui` and a `configure(frame_func=...)` method. Feature modules import
`gui` from foundry-core; services call `gui.configure(frame_func=frame)` at startup.
Rejected: pollutes a generic library with a stateful singleton that must be mutated by the
application layer. Complicates testing (global state to reset). Philosophically wrong: the
singleton is specific to the service and should not live in a general-purpose library.

**Option B — New `gui` module in services**: Create a new module in each service as a neutral singleton
home. Feature modules import from that module.
Rejected: adds a thin wrapper module whose only content is a singleton. The module boundary
problem is merely moved, not eliminated. No architectural gain justifies the additional module.

**Option C (chosen) — Registry-based page decorators**: The standalone `page_*` decorators in
foundry-core (`page_authenticated`, `page_public`, etc.) write to a module-level `_registry`
instead of calling `@ui.page()` immediately. `gui_register_pages(frame_func=frame)` processes
the registry after all `BasePageBuilder.register_pages()` calls, actualizing each entry with
the correct `frame_func`. Feature modules import only from `aignostics_foundry_core.gui`.
Library consumers provide the `frame_func` to `gui_run()`, which flows it down to
`gui_register_pages`. The `gui` singleton in library consumers is deleted entirely.

## Decision

Implement Option C. The standalone `page_*` decorators become pure registration decorators
that record intent (path, title, access level, page function) to a module-level list. The
`gui_register_pages(frame_func)` function actualizes all entries using the private
`_actualize_*` functions. `GUINamespace` methods continue to call `_actualize_*` directly,
bypassing the registry (preserving the existing opt-in, frame-at-construction-time API for
any future consumers that prefer it).

`gui_run()` gains a `frame_func` parameter that is forwarded to `gui_register_pages`.
Library consumers passe `frame_func=frame` when calling `gui_run()`.

## Consequences

**Easier**:
- Feature modules have zero dependency on a `gui` module for page registration.
- Dependency graph is clean: feature modules → `aignostics_foundry_core.gui`; library consumers
  orchestrate and provide the frame.
- Adding a new page requires only `from aignostics_foundry_core.gui import page_authenticated`
  — no reference to any singleton or other service module.

**Harder / risks**:
- Page registration is now a two-phase process (write to registry, then actualize). Code that
  calls `page_authenticated(path)(func)` and expects the route to be live immediately (without
  subsequently calling `gui_register_pages`) will silently not register the route.
- `_registry` is module-level mutable state. Tests must call `clear_page_registry()` in
  teardown to avoid cross-test contamination.
- `GUINamespace` now calls a different set of internal functions (`_actualize_*`) than the
  public `page_*` API, which is a maintenance surface to keep in sync.
