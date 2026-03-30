"""Sentry integration for application monitoring."""

import re
import urllib.parse
from importlib.util import find_spec
from typing import TYPE_CHECKING, Annotated, Any, Literal

from loguru import logger
from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer, SecretStr
from pydantic_settings import SettingsConfigDict

from aignostics_foundry_core.foundry import get_context
from aignostics_foundry_core.settings import OpaqueSettings, strip_to_none_before_validator

if TYPE_CHECKING:
    from sentry_sdk.integrations import Integration

    from aignostics_foundry_core.foundry import FoundryContext

_ERR_MSG_MISSING_SCHEME = "Sentry DSN is missing URL scheme (protocol)"
_ERR_MSG_MISSING_NETLOC = "Sentry DSN is missing network location (domain)"
_ERR_MSG_NON_HTTPS = "Sentry DSN must use HTTPS protocol for security"
_ERR_MSG_INVALID_DOMAIN = "Sentry DSN must use a valid Sentry domain (ingest.us.sentry.io or ingest.de.sentry.io)"
_ERR_MSG_INVALID_FORMAT = "Invalid Sentry DSN format"
_VALID_SENTRY_DOMAIN_PATTERN = r"^[a-f0-9]+@o\d+\.ingest\.(us|de)\.sentry\.io$"


def _validate_url_scheme(parsed_url: urllib.parse.ParseResult) -> None:
    """Validate that the URL has a scheme.

    Args:
        parsed_url: The parsed URL to validate

    Raises:
        ValueError: If URL is missing scheme
    """
    if not parsed_url.scheme:
        raise ValueError(_ERR_MSG_MISSING_SCHEME)


def _validate_url_netloc(parsed_url: urllib.parse.ParseResult) -> None:
    """Validate that the URL has a network location.

    Args:
        parsed_url: The parsed URL to validate

    Raises:
        ValueError: If URL is missing network location
    """
    if not parsed_url.netloc:
        raise ValueError(_ERR_MSG_MISSING_NETLOC)


def _validate_https_scheme(parsed_url: urllib.parse.ParseResult) -> None:
    """Validate that the URL uses HTTPS scheme.

    Args:
        parsed_url: The parsed URL to validate

    Raises:
        ValueError: If URL doesn't use HTTPS scheme
    """
    if parsed_url.scheme != "https":
        raise ValueError(_ERR_MSG_NON_HTTPS)


def _validate_sentry_domain(netloc_with_auth: str) -> None:
    """Validate that the URL uses a valid Sentry domain.

    Args:
        netloc_with_auth: The network location with auth part

    Raises:
        ValueError: If URL doesn't use a valid Sentry domain
    """
    if "@" not in netloc_with_auth:
        raise ValueError(_ERR_MSG_INVALID_DOMAIN)

    user_pass, domain = netloc_with_auth.split("@", 1)
    full_auth = f"{user_pass}@{domain}"
    if not re.match(_VALID_SENTRY_DOMAIN_PATTERN, full_auth):
        raise ValueError(_ERR_MSG_INVALID_DOMAIN)


def _validate_https_dsn(value: SecretStr | None) -> SecretStr | None:
    """Validate that the Sentry DSN is a valid HTTPS URL.

    Args:
        value: The DSN value to validate

    Returns:
        SecretStr | None: The validated DSN value

    Raises:
        ValueError: If DSN isn't a valid HTTPS URL with specific error details
    """
    if value is None:
        return value

    dsn = value.get_secret_value()
    try:
        parsed_url = urllib.parse.urlparse(dsn)

        _validate_url_scheme(parsed_url)
        _validate_url_netloc(parsed_url)
        _validate_https_scheme(parsed_url)
        _validate_sentry_domain(parsed_url.netloc)

    except ValueError as exc:
        raise exc from None
    except Exception as exc:
        error_message = _ERR_MSG_INVALID_FORMAT
        raise ValueError(error_message) from exc

    return value


class SentrySettings(OpaqueSettings):
    """Configuration settings for Sentry integration.

    Reads from environment variables with the ``FOUNDRY_SENTRY_`` prefix by
    default. Callers can supply a project-specific prefix or env file at
    instantiation time using Pydantic Settings v2 constructor kwargs::

        settings = SentrySettings(_env_prefix="BRIDGE_SENTRY_", _env_file=".env")
    """

    model_config = SettingsConfigDict(
        env_prefix="FOUNDRY_SENTRY_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: Annotated[
        bool,
        Field(
            description="Enable remote error and profile collection via Sentry",
            default=False,
        ),
    ]

    dsn: Annotated[
        SecretStr | None,
        BeforeValidator(strip_to_none_before_validator),
        AfterValidator(_validate_https_dsn),
        PlainSerializer(func=OpaqueSettings.serialize_sensitive_info, return_type=str, when_used="always"),
        Field(description="Sentry DSN", examples=["https://SECRET@SECRET.ingest.de.sentry.io/SECRET"], default=None),
    ]

    debug: Annotated[
        bool,
        Field(description="Debug (https://docs.sentry.io/platforms/python/configuration/options/)", default=False),
    ]

    send_default_pii: Annotated[
        bool,
        Field(
            description="Send default personal identifiable information (https://docs.sentry.io/platforms/python/configuration/options/)",
            default=False,
        ),
    ]

    max_breadcrumbs: Annotated[
        int,
        Field(
            description="Max breadcrumbs (https://docs.sentry.io/platforms/python/configuration/options/#max_breadcrumbs)",
            ge=0,
            default=50,
        ),
    ]

    sample_rate: Annotated[
        float,
        Field(
            ge=0.0,
            description="Sample Rate (https://docs.sentry.io/platforms/python/configuration/sampling/#sampling-error-events)",
            default=1.0,
        ),
    ]

    traces_sample_rate: Annotated[
        float,
        Field(
            ge=0.0,
            description="Traces Sample Rate (https://docs.sentry.io/platforms/python/configuration/sampling/#configuring-the-transaction-sample-rate)",
            default=0.1,
        ),
    ]

    profiles_sample_rate: Annotated[
        float,
        Field(
            ge=0.0,
            description="Profiles Sample Rate (https://docs.sentry.io/platforms/python/tracing/#configure)",
            default=0.1,
        ),
    ]

    profile_session_sample_rate: Annotated[
        float,
        Field(
            ge=0.0,
            description="Profile Session Sample Rate (https://docs.sentry.io/platforms/python/tracing/#configure)",
            default=0.1,
        ),
    ]

    profile_lifecycle: Annotated[
        Literal["manual", "trace"],
        Field(
            description="Profile Lifecycle (https://docs.sentry.io/platforms/python/tracing/#configure)",
            default="trace",
        ),
    ]

    enable_logs: Annotated[
        bool,
        Field(
            description="Enable Sentry log integration (https://docs.sentry.io/platforms/python/logging/)",
            default=True,
        ),
    ]


def sentry_initialize(
    integrations: "list[Integration] | None",
    *,
    context: "FoundryContext | None" = None,
) -> bool:
    """Initialize Sentry integration.

    All project-specific metadata is derived from *context* (or the global
    context installed via :func:`~aignostics_foundry_core.foundry.set_context`).

    Args:
        integrations: List of Sentry SDK integrations to register, or ``None``.
        context: :class:`~aignostics_foundry_core.foundry.FoundryContext` providing
            project name, version, environment, URLs, and runtime mode flags.
            Falls back to the global context set via
            :func:`~aignostics_foundry_core.foundry.set_context`.

    Returns:
        bool: ``True`` if Sentry was initialised successfully, ``False`` otherwise.
    """
    ctx = context or get_context()

    settings = SentrySettings(
        _env_prefix=f"{ctx.env_prefix}SENTRY_",  # pyright: ignore[reportCallIssue]
        _env_file=ctx.env_file,  # pyright: ignore[reportCallIssue]
    )

    if not find_spec("sentry_sdk") or not settings.enabled or settings.dsn is None:
        logger.trace("Sentry integration is disabled or sentry_sdk not found, initialization skipped.")
        return False

    import sentry_sdk  # noqa: PLC0415
    from sentry_sdk.integrations.logging import ignore_logger  # noqa: PLC0415

    sentry_sdk.init(
        release=f"{ctx.name}@{ctx.version_full}",
        environment=ctx.environment,
        dsn=settings.dsn.get_secret_value().strip(),
        max_breadcrumbs=settings.max_breadcrumbs,
        debug=settings.debug,
        send_default_pii=settings.send_default_pii,
        sample_rate=settings.sample_rate,
        traces_sample_rate=settings.traces_sample_rate,
        profiles_sample_rate=settings.profiles_sample_rate,
        profile_session_sample_rate=settings.profile_session_sample_rate,
        profile_lifecycle=settings.profile_lifecycle,
        enable_logs=settings.enable_logs,
        integrations=integrations if integrations is not None else [],
    )
    sentry_sdk.set_context(
        "aignx/base",
        {
            "project_name": ctx.name,
            "repository_url": ctx.repository_url,
            "documentation_url": ctx.documentation_url,
            "version_full": ctx.version_full,
            "in_container": ctx.is_container,
            "test_mode": ctx.is_test,
            "cli_mode": ctx.is_cli,
            "library_mode": ctx.is_library,
        },
    )

    ignore_logger("azure.storage.blob._shared.avro.schema")
    ignore_logger("PIL.PngImagePlugin")
    ignore_logger("matplotlib")
    ignore_logger("faker.factory")
    logger.trace("Sentry integration initialized.")

    return True


def set_sentry_user(user: dict[str, Any] | None, role_claim: str | None = None) -> None:
    """Set user context for Sentry error tracking.

    Safely sets user information in Sentry scope. Does nothing if:
    - sentry_sdk is not installed
    - user is None (clears user context)

    This function should be called after successful authentication
    to enrich error reports with user context.

    Args:
        user: User dict from Auth0 containing fields like 'sub' (user ID),
            'email', 'name', 'org_id', 'org_name', 'role', etc.
            Pass None to clear user context.
        role_claim: Optional custom claim name for the user's role.
            If not specified, the role field will not be extracted.

    Example:
        >>> set_sentry_user({"sub": "auth0|123", "email": "user@example.com", "org_id": "org123"})
        >>> set_sentry_user(None)  # Clear user context
    """
    if not find_spec("sentry_sdk"):
        return

    import sentry_sdk  # noqa: PLC0415

    if user is None:
        sentry_sdk.set_user(None)
        return

    # Direct mappings from Auth0 user claims to Sentry user context
    field_mappings: list[tuple[str, str]] = [
        ("sub", "id"),  # Auth0 user ID (e.g., "auth0|abc123")
        ("email", "email"),
        ("name", "name"),
        ("org_id", "org_id"),
        ("org_name", "org_name"),
        ("nickname", "nickname"),
        ("given_name", "given_name"),
        ("family_name", "family_name"),
        ("picture", "picture"),
        ("updated_at", "updated_at"),
    ]

    if role_claim:
        field_mappings.append((role_claim, "role"))

    sentry_user: dict[str, str] = {}
    for source_key, target_key in field_mappings:
        if value := user.get(source_key):
            sentry_user[target_key] = value

    if sentry_user:
        sentry_sdk.set_user(sentry_user)
