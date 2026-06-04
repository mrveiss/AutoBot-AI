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
from typing import Sequence

_DEFAULT_ALLOWED_ROOTS: tuple[str, ...] = (
    "/opt/autobot",
    "/tmp",  # nosec B108 - test/controlled code uses tmpdir intentionally
)


def validate_path(
    user_path: str,
    allowed_roots: Sequence[str] | None = None,
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

    roots = tuple(allowed_roots) if allowed_roots is not None else _DEFAULT_ALLOWED_ROOTS

    resolved = Path(os.path.realpath(user_path))

    for root in roots:
        root_resolved = Path(os.path.realpath(root))
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        # Path is within this root — check existence if required
        if must_exist and not resolved.exists():  # codeql[py/path-injection]
            raise ValueError("Path does not exist")
        return resolved

    raise ValueError("Path is outside allowed directories")


def validate_relative_path(
    user_segment: str,
    base_dir: str | Path,
    *,
    must_exist: bool = False,
) -> Path:
    """Join *user_segment* onto *base_dir* and verify no escape.

    Designed for the common pattern where a user supplies a filename
    or relative sub-path that should stay under a known directory.

    Parameters
    ----------
    user_segment:
        User-supplied path component (filename, sub-path).
    base_dir:
        Trusted root directory the result must remain within.
    must_exist:
        When *True*, require the resolved path to exist on disk.

    Returns
    -------
    pathlib.Path
        The resolved, validated path.

    Raises
    ------
    ValueError
        If the resolved path escapes *base_dir*, contains null
        bytes, or (when *must_exist*) does not exist.
    """
    if not user_segment or "\x00" in user_segment:
        raise ValueError("Invalid path segment: empty or contains null bytes")

    base = Path(os.path.realpath(str(base_dir)))
    resolved = Path(os.path.realpath(str(base / user_segment)))

    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError("Path traversal detected: segment escapes base directory")

    if must_exist and not resolved.exists():  # codeql[py/path-injection]
        raise ValueError(f"Path does not exist: {resolved}")

    return resolved
