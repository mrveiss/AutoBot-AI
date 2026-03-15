# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Path validation utility (#1721).

Prevents path traversal attacks by ensuring resolved paths stay within
allowed directories.  Used wherever user-supplied file paths appear in
API endpoints.

Usage:
    from autobot_shared.security.path_validator import validate_path

    safe = validate_path(user_input, allowed_roots=["/opt/autobot/data"])
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

_DEFAULT_ALLOWED_ROOTS: tuple[str, ...] = (
    "/opt/autobot",
    "/tmp",
)


def validate_path(
    user_path: str,
    allowed_roots: Optional[Sequence[str]] = None,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve *user_path* and verify it falls under an allowed root.

    Parameters
    ----------
    user_path:
        The raw, potentially untrusted path string.
    allowed_roots:
        Directories the resolved path must be a child of.
        Falls back to ``_DEFAULT_ALLOWED_ROOTS`` when *None*.
    must_exist:
        When *True*, additionally require the resolved path to exist on
        disk.

    Returns
    -------
    pathlib.Path
        The resolved, validated path.

    Raises
    ------
    ValueError
        If the path escapes all allowed roots, contains null bytes, or
        (when *must_exist*) does not exist.
    """
    if not user_path or "\x00" in user_path:
        raise ValueError("Invalid path: empty or contains null bytes")

    roots = (
        tuple(allowed_roots) if allowed_roots is not None else _DEFAULT_ALLOWED_ROOTS
    )

    resolved = Path(os.path.realpath(user_path))

    for root in roots:
        root_resolved = Path(os.path.realpath(root))
        try:
            resolved.relative_to(root_resolved)
            if must_exist and not resolved.exists():
                raise ValueError(f"Path does not exist: {resolved}")
            return resolved
        except ValueError:
            if must_exist and not resolved.exists():
                raise
            continue

    raise ValueError("Path is outside allowed directories")
