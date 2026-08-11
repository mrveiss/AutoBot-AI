# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Sequence

_DEFAULT_ALLOWED_ROOTS: tuple[str, ...] = (
    "/opt/autobot",
    "/tmp",  # nosec B108  # test/controlled code uses tmpdir intentionally
)

# Characters rejected outright in sandbox-relative user paths (Issue #326).
# Single source of truth for the sandbox resolver shared by files.py and
# sandbox_files.py (#11844).
SANDBOX_INVALID_PATH_CHARACTERS: frozenset[str] = frozenset({"<", ">", ":", '"', "|", "?", "*"})


class SandboxPathError(ValueError):
    """A sandbox-relative path failed validation (#11844).

    Carries the exact user-facing message so callers can surface it
    verbatim (e.g. as a FastAPI ``HTTPException`` detail) without
    re-deriving wording.
    """


def _contains_traversal_token(path: str) -> bool:
    """True when *path* hides a parent-directory reference behind encoding.

    ``os.path.realpath`` performs neither percent-decoding nor Unicode
    normalization, so ``validate_path``'s containment check alone never
    caught a disguised ``..`` — it only rejected such input incidentally,
    on hosts where the allowed root happened not to contain the caller's
    current working directory (#14050 — the filesystem MCP bridge's
    allowlist, ``config.base_dir``, exposed this once a checkout became
    a real, existing allowed root instead of a nonexistent deployment path).

    Checks the raw string, up to two rounds of percent-decoding (covers
    single- and double-encoded ``%2e%2e%2f`` forms — matching the encoded
    case ``resolve_within_sandbox`` already guards, #11844), and the NFKC
    normalization of each (collapses Unicode confusables such as ``﹒``
    SMALL FULL STOP or ``‥`` TWO DOT LEADER down to ASCII ``.``) for a
    literal ``..``.
    """
    candidates = {path}
    decoded = path
    for _ in range(2):
        next_decoded = urllib.parse.unquote(decoded)
        candidates.add(next_decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    candidates.update({unicodedata.normalize("NFKC", candidate) for candidate in list(candidates)})
    return any(".." in candidate for candidate in candidates)


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
        If the path escapes all allowed roots, contains null bytes, hides a
        parent-directory reference behind percent-encoding or a Unicode
        confusable, or (when *must_exist*) does not exist.
    """
    if not user_path or "\x00" in user_path:
        raise ValueError("Invalid path: empty or contains null bytes")

    # #14050: reject a disguised ".." before it ever reaches realpath —
    # os.path.realpath resolves the raw byte string, so an allowed root that
    # happens to contain the caller's cwd (any checkout-relative root) would
    # otherwise let a decoded traversal land on a real, in-bounds file.
    if _contains_traversal_token(user_path):
        raise ValueError("Path is outside allowed directories")

    roots = tuple(allowed_roots) if allowed_roots is not None else _DEFAULT_ALLOWED_ROOTS

    resolved = Path(os.path.realpath(user_path))

    for root in roots:
        root_resolved = Path(os.path.realpath(root))
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        # Path is within this root — check existence if required
        if must_exist and not resolved.exists():
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

    if must_exist and not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")

    return resolved


def resolve_within_sandbox(path: str, root: Path) -> Path:
    """Strip, reject traversal, and resolve *path* under *root* (#11844).

    Single shared sandbox resolver for the file-management APIs. ``''`` and
    ``'/'`` (and ``'//'``) address the sandbox root itself and return *root*
    unchanged: historically these stripped to an empty segment that
    :func:`validate_relative_path` rejected, surfacing a misleading "outside
    sandbox" error and making the root unlistable for every endpoint (#11823).
    All other input is checked for traversal (``..``, leading ``/``, ``~``,
    invalid characters, and URL-encoded traversal) before resolution.

    Parameters
    ----------
    path:
        Raw, user-supplied sandbox-relative path.
    root:
        Trusted sandbox root the result must remain within.

    Returns
    -------
    pathlib.Path
        The resolved path (``root`` for the root-addressing cases).

    Raises
    ------
    SandboxPathError
        On any traversal / escape attempt. The message is safe to surface
        verbatim to the caller.
    """
    if not path:
        return root

    clean_path = path.strip("/")

    # "/" (and "//") address the sandbox root; after stripping they collapse
    # to "", which validate_relative_path rejects as an empty segment (#11823).
    if not clean_path:
        return root

    if (
        ".." in clean_path
        or clean_path.startswith("/")
        or "~" in clean_path
        or any(char in clean_path for char in SANDBOX_INVALID_PATH_CHARACTERS)
    ):
        raise SandboxPathError("Invalid path: path traversal not allowed")

    # #14050: shares _contains_traversal_token with validate_path so a
    # double-encoded (%252e%252e) or Unicode-confusable (﹒﹒, ‥) traversal
    # can't slip past this resolver either — the single-pass unquote() this
    # replaced only caught one level of percent-encoding.
    if _contains_traversal_token(clean_path) or urllib.parse.unquote(clean_path).startswith("/"):
        raise SandboxPathError("Invalid path: encoded traversal not allowed")

    try:
        return validate_relative_path(clean_path, root)
    except ValueError:
        raise SandboxPathError("Path outside sandbox not allowed")
