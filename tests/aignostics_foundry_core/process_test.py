"""Tests for aignostics_foundry_core.process module."""

import os
from pathlib import Path

import pytest

from aignostics_foundry_core.process import get_process_info
from tests.conftest import make_context


@pytest.mark.unit
def test_get_process_info_returns_current_process() -> None:
    """get_process_info() returns info for the currently running process."""
    ctx = make_context()
    info = get_process_info(context=ctx)
    assert info.pid == os.getpid()


@pytest.mark.unit
def test_process_info_has_parent() -> None:
    """ProcessInfo.parent has a non-empty name and positive pid."""
    ctx = make_context()
    info = get_process_info(context=ctx)
    assert info.parent.name is not None
    assert len(info.parent.name) > 0
    assert info.parent.pid is not None
    assert info.parent.pid > 0


@pytest.mark.unit
def test_get_process_info_project_root_from_context(tmp_path: Path) -> None:
    """project_root equals str(ctx.project_path) when project_path is set."""
    ctx = make_context(project_path=tmp_path)
    info = get_process_info(context=ctx)
    assert info.project_root == str(tmp_path)


@pytest.mark.unit
def test_get_process_info_project_root_none_when_path_not_set() -> None:
    """project_root is None when context has project_path=None."""
    ctx = make_context(project_path=None)
    info = get_process_info(context=ctx)
    assert info.project_root is None
