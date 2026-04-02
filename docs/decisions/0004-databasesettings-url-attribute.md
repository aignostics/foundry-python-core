# 4. DatabaseSettings URL attribute

Date: 2026-04-02

## Status

Accepted

## Context

The functionality of the `DatabaseSettings` class is inherited from Bridge. It has:
- A `url` field to store the full database connection URL, including a driver prefix and database name
- A `name` field to store just the database name for substitution (used for feature environments)
- A `get_url()` method that processes the raw URL (optionally replacing the driver and database name) and is the
intended API for consumers

This is confusing: it's not clear that the URL should contain a database name, nor that the driver in the URL might be
replaced at runtime, nor that the `name` field is used for substitution. Additionally, callers might easily reach
for `settings.url` instead of `settings.get_url()`, skipping the processing logic and causing subtle bugs.

### Alternatives

- Rename `url` to `_url` with `Field(alias="url")`: this would make it clear that it's an internal field,
but is **not supported by Pydantic >= 2.1.0**. We therefore reject this option.
- Refactor the class to have a `host`, `db_name` and optional `driver` attributes and always construct the URL at runtime.
This is the preferred design, but is a more significant change which would delay delivery of the service template.
We therefore reject this option **for now**.
- **`raw_url: SecretStr = Field(alias="url")`**: pydantic-settings applies the dynamic
  `_env_prefix` only to field names, not to aliases. With prefix `TEST_DB_` and
  `Field(alias="url")`, pydantic-settings looks for the bare env var `URL` rather than
  `TEST_DB_URL`, breaking the env-var contract entirely. `validate_by_name=True` adds a lookup
  for `TEST_DB_RAW_URL` but never for `TEST_DB_URL`. `PrivateAttr` was also evaluated: it
  supports underscore names but cannot be populated from env vars by pydantic-settings, requiring
  a bridge field that still leaves the raw URL accessible.

## Decision

Keep `url: SecretStr` as the field name. Rely on docstrings, the class API design, and this
decision record to guide callers toward `get_url()`.

## Consequences

- `get_url()` is the only correct way to consume the URL; `settings.url` remains accessible but
  is clearly documented as internal and unprocessed.
- The `raw_url` rename and `_url` alias approaches are ruled out; this document records the
  constraints for future reference.
- A long-term redesign (separate `host`, `db_name`, optional `driver` fields) remains the preferred
  direction but is deferred.
