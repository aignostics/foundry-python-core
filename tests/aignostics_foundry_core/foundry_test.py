"""Tests for the foundry module — FoundryContext, set_context, get_context."""

import importlib.metadata
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import ValidationError

from aignostics_foundry_core.foundry import FoundryContext, get_context, set_context

# Constants (SonarQube S1192)
PACKAGE_NAME = "aignostics_foundry_core"
STAGING = "staging"
ERROR_MSG_FRAGMENT = "set_context"
VCS_REF_VALUE = "abc123"
COMMIT_SHA_VALUE = "deadbeef"
CI_RUN_ID_VALUE = "99"
CI_RUN_NUMBER_VALUE = "42"
BUILD_DATE_VALUE = "2024-01-15"
BUILDER_UNKNOWN = "unknown"


@pytest.fixture(autouse=True)
def reset_context(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Reset global _context to None before and after every test.

    Yields:
        None
    """
    monkeypatch.setattr("aignostics_foundry_core.foundry._context", None)
    yield
    monkeypatch.setattr("aignostics_foundry_core.foundry._context", None)


# ---------------------------------------------------------------------------
# from_package — name and version
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_returns_correct_name() -> None:
    """from_package() sets .name to the package_name argument."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.name == PACKAGE_NAME


@pytest.mark.unit
def test_from_package_returns_version_from_metadata() -> None:
    """from_package() sets .version from importlib.metadata."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.version == importlib.metadata.version(PACKAGE_NAME)


# ---------------------------------------------------------------------------
# from_package — environment derivation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_environment_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_package() reads environment from the {NAME}_ENVIRONMENT env var."""
    monkeypatch.setenv(f"{PACKAGE_NAME.upper()}_ENVIRONMENT", STAGING)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.environment == STAGING


@pytest.mark.unit
def test_from_package_environment_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_package() defaults environment to 'local' when no env var is set."""
    for var in [f"{PACKAGE_NAME.upper()}_ENVIRONMENT", "ENV", "VERCEL_ENV", "RAILWAY_ENVIRONMENT"]:
        monkeypatch.delenv(var, raising=False)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.environment == "local"


# ---------------------------------------------------------------------------
# from_package — version_full build metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_version_full_equals_version_when_no_build_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full equals version when all build metadata env vars are absent or 'unknown'.

    BUILDER defaults to 'uv', so it must be explicitly set to 'unknown' to
    make the any() guard False and skip the version_full enrichment block.
    """
    monkeypatch.setenv("BUILDER", BUILDER_UNKNOWN)
    for var in ["VCS_REF", "COMMIT_SHA", "BUILD_DATE", "CI_RUN_ID", "CI_RUN_NUMBER"]:
        monkeypatch.delenv(var, raising=False)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.version_full == ctx.version


@pytest.mark.unit
def test_from_package_version_full_includes_vcs_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full contains VCS_REF and starts with '{version}+' when VCS_REF is set."""
    monkeypatch.setenv("VCS_REF", VCS_REF_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.version_full.startswith(ctx.version + "+")
    assert VCS_REF_VALUE in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_includes_commit_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full contains COMMIT_SHA when COMMIT_SHA is set."""
    monkeypatch.setenv("COMMIT_SHA", COMMIT_SHA_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert COMMIT_SHA_VALUE in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_joins_vcs_ref_and_commit_sha_with_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full joins VCS_REF and COMMIT_SHA with '-' when both are set."""
    monkeypatch.setenv("VCS_REF", VCS_REF_VALUE)
    monkeypatch.setenv("COMMIT_SHA", COMMIT_SHA_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert f"{VCS_REF_VALUE}-{COMMIT_SHA_VALUE}" in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_includes_ci_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full contains 'run.{CI_RUN_ID}' when CI_RUN_ID is set."""
    monkeypatch.setenv("CI_RUN_ID", CI_RUN_ID_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert f"run.{CI_RUN_ID_VALUE}" in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_includes_ci_run_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full contains 'build.{CI_RUN_NUMBER}' when CI_RUN_NUMBER is set."""
    monkeypatch.setenv("CI_RUN_NUMBER", CI_RUN_NUMBER_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert f"build.{CI_RUN_NUMBER_VALUE}" in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_includes_build_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """version_full contains 'built.{BUILD_DATE}' when BUILD_DATE is set."""
    monkeypatch.setenv("BUILD_DATE", BUILD_DATE_VALUE)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert f"built.{BUILD_DATE_VALUE}" in ctx.version_full


@pytest.mark.unit
def test_from_package_version_full_omits_builder_and_extra_when_all_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """version_full has no 'builder.' label and no '---' separator when BUILDER is 'unknown'.

    Applies when no CI metadata vars are set, even though VCS_REF is present.
    """
    monkeypatch.setenv("VCS_REF", VCS_REF_VALUE)
    monkeypatch.setenv("BUILDER", BUILDER_UNKNOWN)
    for var in ["COMMIT_SHA", "CI_RUN_ID", "CI_RUN_NUMBER", "BUILD_DATE"]:
        monkeypatch.delenv(var, raising=False)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert "builder." not in ctx.version_full
    assert "---" not in ctx.version_full


# ---------------------------------------------------------------------------
# from_package — env_prefix
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_env_prefix_is_upper_name() -> None:
    """from_package() sets env_prefix to '{PACKAGE_NAME.upper()}_'."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.env_prefix == f"{PACKAGE_NAME.upper()}_"


# ---------------------------------------------------------------------------
# from_package — env_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_env_file_contains_home_dotfile() -> None:
    """from_package() includes ~/.{name}/.env as the first entry in env_file."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    expected = Path.home() / f".{PACKAGE_NAME}" / ".env"
    assert expected in ctx.env_file


@pytest.mark.unit
def test_from_package_custom_env_file_inserted_at_index_two(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When {NAME}_ENV_FILE is set, the custom path is inserted at index 2 of env_file."""
    custom = str(tmp_path / "custom.env")
    monkeypatch.setenv(f"{PACKAGE_NAME.upper()}_ENV_FILE", custom)
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.env_file[2] == Path(custom)


# ---------------------------------------------------------------------------
# from_package — runtime mode flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_package_is_test_when_pytest_running_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_test is True when pytest is in sys.modules and PYTEST_RUNNING_{NAME} is set."""
    monkeypatch.setenv(f"PYTEST_RUNNING_{PACKAGE_NAME.upper()}", "1")
    # pytest is already in sys.modules when tests run
    assert "pytest" in sys.modules
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    assert ctx.is_test is True


@pytest.mark.unit
def test_foundry_context_mode_flags_default_to_false() -> None:
    """FoundryContext constructed directly has all four mode flags as False."""
    ctx = FoundryContext(name="test", version="0.0.0", version_full="0.0.0", environment="test")
    assert ctx.is_container is False
    assert ctx.is_cli is False
    assert ctx.is_test is False
    assert ctx.is_library is False


# ---------------------------------------------------------------------------
# Model immutability
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_foundry_context_is_frozen() -> None:
    """Assigning a field on a frozen FoundryContext raises ValidationError."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    with pytest.raises(ValidationError):
        ctx.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# set_context / get_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_set_context_makes_context_accessible() -> None:
    """After set_context(ctx), get_context() returns the same ctx."""
    ctx = FoundryContext.from_package(PACKAGE_NAME)
    set_context(ctx)
    assert get_context() is ctx


@pytest.mark.unit
def test_context_raises_before_set_context() -> None:
    """get_context() before set_context() raises RuntimeError."""
    with pytest.raises(RuntimeError, match=ERROR_MSG_FRAGMENT):
        get_context()


@pytest.mark.unit
def test_set_context_replaces_previous_context() -> None:
    """Calling set_context() twice makes get_context() return the second context."""
    ctx1 = FoundryContext.from_package(PACKAGE_NAME)
    ctx2 = FoundryContext(name="other", version="0.0.0", version_full="0.0.0", environment="test")
    set_context(ctx1)
    set_context(ctx2)
    assert get_context() is ctx2
