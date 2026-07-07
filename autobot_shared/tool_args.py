# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared tool-call argument helpers for the guard modules (#11220).

``config_guard`` and ``fact_forcing_guard`` both need to find the filesystem
path a tool call targets and previously each defined its own ``PATH_KEYS`` +
extractor — which had *drifted* (config had ``destination``; fact-forcing had
``directory``), so each guard was blind to one key the other watched. This is
the single source of truth for both.
"""

# Superset of the arg keys a tool call may carry a filesystem path under —
# the union of the two guards' historical key sets so both inspect the same fields.
PATH_KEYS: tuple[str, ...] = ("file_path", "path", "destination", "directory", "target_file")


def path_from_tool_args(args: dict) -> str | None:
    """Return the first non-empty filesystem path among :data:`PATH_KEYS` in *args*, else None."""
    if not isinstance(args, dict):
        return None
    for key in PATH_KEYS:
        value = args.get(key)
        if value:
            return str(value)
    return None
