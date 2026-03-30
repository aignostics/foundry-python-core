"""Process related utilities."""

import subprocess

import psutil
from pydantic import BaseModel

from aignostics_foundry_core.foundry import FoundryContext, get_context

SUBPROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ParentProcessInfo(BaseModel):
    """Information about a parent process."""

    name: str | None = None
    pid: int | None = None


class ProcessInfo(BaseModel):
    """Information about the current process."""

    project_root: str | None
    pid: int
    parent: ParentProcessInfo
    cmdline: list[str]


def get_process_info(*, context: FoundryContext | None = None) -> ProcessInfo:
    """Get information about the current process and its parent.

    Args:
        context: Project context supplying the project path.  When ``None``,
            the global context installed via :func:`aignostics_foundry_core.foundry.set_context`
            is used.

    Returns:
        ProcessInfo: Object containing process information.
    """
    current_process = psutil.Process()
    parent = current_process.parent()
    ctx = context or get_context()
    project_root = str(ctx.project_path) if ctx.project_path else None

    return ProcessInfo(
        project_root=project_root,
        pid=current_process.pid,
        parent=ParentProcessInfo(
            name=parent.name() if parent else None,
            pid=parent.pid if parent else None,
        ),
        cmdline=current_process.cmdline(),
    )
