"""Tests for aignostics_foundry_core.cli."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from aignostics_foundry_core.cli import no_args_is_help_workaround, prepare_cli
from tests.conftest import make_context

_LOCATE_IMPLEMENTATIONS_PATH = "aignostics_foundry_core.cli.locate_implementations"
_PROJECT_NAME = "myproj"
_MY_EPILOG = "My epilog"


@pytest.mark.unit
class TestNoArgsIsHelpWorkaround:
    """Tests for no_args_is_help_workaround."""

    def test_raises_exit_when_no_subcommand_invoked(self) -> None:
        """Raises typer.Exit when ctx.invoked_subcommand is None."""
        ctx = MagicMock(spec=typer.Context)
        ctx.invoked_subcommand = None
        ctx.get_help.return_value = "help text"

        with pytest.raises(typer.Exit):
            no_args_is_help_workaround(ctx)

    def test_does_not_raise_when_subcommand_present(self) -> None:
        """Does not raise when a subcommand is being invoked."""
        ctx = MagicMock(spec=typer.Context)
        ctx.invoked_subcommand = "some-command"

        # Should not raise
        no_args_is_help_workaround(ctx)


@pytest.mark.unit
class TestPrepareCli:
    """Tests for prepare_cli."""

    def test_sets_epilog(self) -> None:
        """prepare_cli sets the epilog on the CLI app."""
        cli = typer.Typer()
        prepare_cli(cli, _MY_EPILOG, context=make_context(_PROJECT_NAME))

        assert cli.info.epilog == _MY_EPILOG

    def test_adds_no_args_is_help_callback(self) -> None:
        """prepare_cli installs the no_args_is_help workaround callback."""
        cli = typer.Typer()
        prepare_cli(cli, _MY_EPILOG, context=make_context(_PROJECT_NAME))

        assert hasattr(cli, "no_args_callback_added")
        assert cli.no_args_callback_added is True  # type: ignore[attr-defined]

    def test_prepare_cli_propagates_epilog_to_sub_typer(self) -> None:
        """prepare_cli propagates epilog to pre-registered sub-typers."""
        cli = typer.Typer()
        sub = typer.Typer()
        cli.add_typer(sub)
        with patch(_LOCATE_IMPLEMENTATIONS_PATH, return_value=[]):
            prepare_cli(cli, _MY_EPILOG, context=make_context(_PROJECT_NAME))

        assert sub.info.epilog == _MY_EPILOG

    def test_prepare_cli_installs_callback_on_sub_typer(self) -> None:
        """prepare_cli installs the no_args_is_help callback on sub-typers."""
        cli = typer.Typer()
        sub = typer.Typer()
        cli.add_typer(sub)
        with patch(_LOCATE_IMPLEMENTATIONS_PATH, return_value=[]):
            prepare_cli(cli, _MY_EPILOG, context=make_context(_PROJECT_NAME))

        assert hasattr(sub, "no_args_callback_added")

    def test_prepare_cli_adds_discovered_subcommands(self) -> None:
        """prepare_cli adds discovered sub-typers to cli."""
        cli = typer.Typer()
        sub_cli = typer.Typer()
        with patch(_LOCATE_IMPLEMENTATIONS_PATH, return_value=[sub_cli]):
            prepare_cli(cli, "epilog", context=make_context(_PROJECT_NAME))

        registered = [g.typer_instance for g in cli.registered_groups]
        assert sub_cli in registered

    def test_prepare_cli_skips_self_in_discovery(self) -> None:
        """prepare_cli does not add cli to itself when it appears in discovered results."""
        cli = typer.Typer()
        with patch(_LOCATE_IMPLEMENTATIONS_PATH, return_value=[cli]):
            prepare_cli(cli, "epilog", context=make_context(_PROJECT_NAME))

        registered = [g.typer_instance for g in cli.registered_groups]
        assert cli not in registered
