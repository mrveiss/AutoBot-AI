# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repo-relative path normalizer (#11182).

Converts absolute runtime paths (from tracebacks) to repo-relative POSIX
paths that can be joined against the codebase for source mapping.

Usage::

    from autobot_shared.repo_path import to_repo_relative

    rel = to_repo_relative("/opt/autobot/code_source/autobot-backend/services/x.py")
    # → "autobot-backend/services/x.py"
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

# Out-of-repo markers: paths containing any of these segments are stdlib /
# third-party and must be excluded from in-repo traceback frames.
_OUT_OF_REPO_MARKERS: tuple[str, ...] = (
    "/usr/",
    "/lib/python",
    "site-packages",
    "dist-packages",
    "/.venv/",
    "/venv/",
    "/.tox/",
)

# Canonical segment that marks the repo root in production paths.
_CODE_SOURCE_SEGMENT = "code_source/"


def to_repo_relative(path: str) -> str | None:
    """Return a repo-relative POSIX path, or None if the path is out-of-repo.

    Anchor logic (applied in order):
    1. If the path contains ``code_source/``, strip everything up to and
       including that segment — covers production paths such as
       ``/opt/autobot/code_source/autobot-backend/services/x.py``.
    2. If the path matches a known out-of-repo marker (stdlib, venv,
       site-packages …), return ``None``.
    3. Normalise OS separators to POSIX.  If the result already looks
       repo-relative (does not start with ``/`` or a Windows drive), return
       it as-is.
    4. Otherwise return ``None`` — the path is absolute but not anchored.

    Args:
        path: Absolute or relative filesystem path from a traceback frame.

    Returns:
        Repo-relative POSIX string (e.g. ``"autobot-backend/services/x.py"``),
        or ``None`` when the path is outside the repo (stdlib, venv, etc.).
    """
    if not path:
        return None

    # Normalise Windows backslashes to forward slashes.
    normalised = path.replace("\\", "/")

    # 1. Production code_source anchor.
    if _CODE_SOURCE_SEGMENT in normalised:
        idx = normalised.index(_CODE_SOURCE_SEGMENT) + len(_CODE_SOURCE_SEGMENT)
        rel = normalised[idx:]
        return rel if rel else None

    # 2. Out-of-repo markers.
    for marker in _OUT_OF_REPO_MARKERS:
        if marker in normalised:
            return None

    # 3. Already repo-relative (no leading slash, no Windows drive letter).
    posix = PurePosixPath(normalised)
    if not posix.is_absolute():
        # Reject Windows-drive-absolute paths like "C:/..."
        try:
            PureWindowsPath(normalised).drive  # non-empty means drive-absolute
            if PureWindowsPath(normalised).drive:
                return None
        except Exception:
            pass
        # Canonicalize: drop leading "./" and interior "." segments so a path
        # like "./autobot-backend/x.py" joins against "autobot-backend/x.py".
        return posix.as_posix()

    # 4. Absolute but no known anchor → out-of-repo.
    return None
