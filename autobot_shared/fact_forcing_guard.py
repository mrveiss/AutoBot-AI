# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fact-forcing guard helpers (GH#11149 / GH#11178).

Pure, dependency-free "read before you write" detection: block the FIRST mutating
edit to an *existing* file until it has been investigated (read / grepped) in the
current turn. A blocked edit is self-clearing — once the agent reads the file the
retry proceeds. Creating a NEW file is never blocked (keys on ``exists_fn`` and
fails open on ambiguity, so it never wrongly blocks a create).

Lives in ``autobot_shared`` (not ``agent_loop``) so BOTH the agent loop
(``agent_loop.fact_forcing``) and the production tool-dispatch seam
(``chat_workflow.tool_handler``) reuse it without importing the heavy
``agent_loop`` package. Off by default; enable via ``AUTOBOT_FACT_FORCING=1``.
"""

import os

from autobot_shared.env_utils import env_flag
from autobot_shared.tool_args import path_from_tool_args

# Tools that count as investigating a path.
INVESTIGATION_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "read",
        "read_files",
        "grep_search",
        "grep",
        "search_files",
        "list_dir",
        "list_directory",
        "glob",
        "glob_file_search",
        "codebase_search",
    }
)

# Mutating edits to an existing file that the gate guards. Pure creators
# (create_file / write-new) are handled by the exists check, not by name.
EDIT_TOOLS: frozenset[str] = frozenset(
    {
        "edit_file",
        "write_file",
        "multi_edit",
        "apply_patch",
        "delete_file",
    }
)


def _norm(path: str) -> str:
    # realpath (not normpath) so a file read by relative path and edited by
    # absolute path — or via a symlink — normalize to the SAME key and the read
    # is credited (GH#11179). Resolves against the process CWD + symlinks.
    return os.path.realpath(path.strip())


# --- name+args core (production dispatch seam) -----------------------------


def record_investigation(tool_name: str, args: dict, investigated: set[str]) -> None:
    """Record *args*' path in *investigated* if *tool_name* is an investigation tool."""
    if str(tool_name).lower() not in INVESTIGATION_TOOLS:
        return
    path = path_from_tool_args(args)
    if path:
        investigated.add(_norm(path))


def uninvestigated_edit_path(
    tool_name: str,
    args: dict,
    investigated: set[str],
    exists_fn=os.path.exists,
) -> str | None:
    """Return the target path if (name, args) edits an existing, uninvestigated file.

    New files (``not exists_fn(path)``) and existence errors return None (fail
    open — never block a create).
    """
    if str(tool_name).lower() not in EDIT_TOOLS:
        return None
    path = path_from_tool_args(args)
    if not path:
        return None
    if _norm(path) in investigated:
        return None
    try:
        if not exists_fn(_norm(path)):
            return None
    except OSError:
        return None
    return path


# --- dict-shaped wrappers (agent loop backward compat) ----------------------


def record_investigations(tools: list[dict], investigated: set[str]) -> None:
    """Add the normalized paths of any investigation tools in *tools* to *investigated*."""
    for tool in tools:
        args = tool.get("args") or tool.get("arguments") or tool.get("parameters") or {}
        record_investigation(tool.get("tool_name", ""), args, investigated)


def first_uninvestigated_edit(
    tool: dict,
    investigated: set[str],
    exists_fn=os.path.exists,
) -> str | None:
    """Return the target path if *tool* edits an existing, uninvestigated file, else None."""
    args = tool.get("args") or tool.get("arguments") or tool.get("parameters") or {}
    return uninvestigated_edit_path(tool.get("tool_name", ""), args, investigated, exists_fn)


def fact_forcing_env_enabled() -> bool:
    """True when ``AUTOBOT_FACT_FORCING`` enables the gate."""
    return env_flag("AUTOBOT_FACT_FORCING")
