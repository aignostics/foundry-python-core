"""Tests for aignostics_foundry_core.cli."""

from unittest.mock import MagicMock

import pytest
import typer

from aignostics_foundry_core.cli import no_args_is_help_workaround, prepare_cli


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
        prepare_cli(cli, "My epilog", "myproj")

        assert cli.info.epilog == "My epilog"

    def test_adds_no_args_is_help_callback(self) -> None:
        """prepare_cli installs the no_args_is_help workaround callback."""
        cli = typer.Typer()
        prepare_cli(cli, "My epilog", "myproj")

        assert hasattr(cli, "no_args_callback_added")
        assert cli.no_args_callback_added is True  # type: ignore[attr-defined]
