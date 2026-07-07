# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fact-forcing gate for the agent loop (GH#11149).

Blocks the FIRST mutating edit to an *existing* file until that file has been
investigated (read / grepped) in the current task — the mechanical form of
"read before you write". A blocked edit is self-clearing: once the agent reads
the file, the retry proceeds.

Creating a NEW file is never blocked (there is nothing to investigate), so the
gate keys on ``exists_fn`` and fails open on existence ambiguity — it never
wrongly blocks a create.

Opt-in: off by default; enable via ``AgentLoopConfig.fact_forcing_enabled`` or
``AUTOBOT_FACT_FORCING=1``.
"""

import os

# Tools that count as investigating a path.
_INVESTIGATION_TOOLS: frozenset[str] = frozenset(
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
_EDIT_TOOLS: frozenset[str] = frozenset(
    {
        "edit_file",
        "write_file",
        "multi_edit",
        "apply_patch",
        "delete_file",
    }
)

_PATH_KEYS: tuple[str, ...] = ("file_path", "path", "directory", "target_file")


def _extract_path(tool: dict) -> str | None:
    args = tool.get("args") or tool.get("arguments") or tool.get("parameters") or {}
    if not isinstance(args, dict):
        return None
    for key in _PATH_KEYS:
        value = args.get(key)
        if value:
            return str(value)
    return None


def _norm(path: str) -> str:
    return os.path.normpath(path.strip())


def record_investigations(tools: list[dict], investigated: set[str]) -> None:
    """Add the normalized paths of any investigation tools in *tools* to *investigated*."""
    for tool in tools:
        if str(tool.get("tool_name", "")).lower() not in _INVESTIGATION_TOOLS:
            continue
        path = _extract_path(tool)
        if path:
            investigated.add(_norm(path))


def first_uninvestigated_edit(
    tool: dict,
    investigated: set[str],
    exists_fn=os.path.exists,
) -> str | None:
    """Return the target path if *tool* edits an existing, uninvestigated file, else None.

    New files (``not exists_fn(path)``) are allowed — there is nothing to read.
    """
    if str(tool.get("tool_name", "")).lower() not in _EDIT_TOOLS:
        return None
    path = _extract_path(tool)
    if not path:
        return None
    normalized = _norm(path)
    if normalized in investigated:
        return None
    try:
        if not exists_fn(normalized):
            return None  # new file → nothing to investigate
    except OSError:
        return None  # existence ambiguous → fail open (never block a create)
    return path


def fact_forcing_env_enabled() -> bool:
    """True when ``AUTOBOT_FACT_FORCING`` force-enables the gate regardless of config."""
    return os.environ.get("AUTOBOT_FACT_FORCING", "").strip().lower() in {"1", "true", "yes", "on"}
