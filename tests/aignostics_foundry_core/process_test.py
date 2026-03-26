"""Tests for aignostics_foundry_core.process module."""

import os
from pathlib import Path

import pytest

from aignostics_foundry_core.process import get_process_info


@pytest.mark.unit
def test_get_process_info_returns_current_process() -> None:
    """get_process_info() returns info for the currently running process."""
    info = get_process_info()
    assert info.pid == os.getpid()


@pytest.mark.unit
def test_process_info_has_parent() -> None:
    """ProcessInfo.parent has a non-empty name and positive pid."""
    info = get_process_info()
    assert info.parent.name is not None
    assert len(info.parent.name) > 0
    assert info.parent.pid is not None
    assert info.parent.pid > 0


@pytest.mark.unit
def test_process_info_project_root_is_directory() -> None:
    """ProcessInfo.project_root is an existing directory."""
    info = get_process_info()
    project_root = Path(info.project_root)
    assert project_root.is_dir()
