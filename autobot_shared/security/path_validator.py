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
from pathlib import Path, PurePosixPath
from typing import Sequence

from autobot_shared.paths import project_root

# #15238: no `/tmp` here. It is world-writable and shared with every other
# process on the host, so an unprivileged local process can plant a file
# there for any endpoint that falls back to this default to read back.
# Every caller must state the root it actually means; there is no safe
# universal fallback.
_DEFAULT_ALLOWED_ROOTS: tuple[str, ...] = ("/opt/autobot",)

#: Call sites that mean "inside the AutoBot project" — the common case for
#: request handlers analyzing this codebase — import this alongside
#: ``validate_path`` instead of hand-rolling `/opt/autobot` or reaching for
#: the (deliberately narrow) default. Centralised so a grandfathered,
#: line-frozen call site can add it via its *existing* import line (#15238).
PROJECT_ALLOWED_ROOTS: tuple[str, ...] = (str(project_root()),)

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


#: Decode-loop cap for :func:`_canonicalize`. ``os.path.realpath`` never
#: decodes anything itself, so a percent-encoded ``..`` only *looks* like a
#: harmless literal filename to it. 8 rounds is deep enough for any encoding
#: depth seen in practice while bounding a pathological input.
_MAX_DECODE_ROUNDS = 8


def _canonicalize(path: str) -> str:
    """Fully percent-decode (to a fixed point) and NFKC-normalize *path*.

    ``os.path.realpath`` performs neither percent-decoding nor Unicode
    normalization. Left alone, a disguised ``..`` — percent-encoded to any
    depth, or spelled with a Unicode confusable such as ``﹒`` SMALL FULL
    STOP or ``‥`` TWO DOT LEADER — never becomes a real ``..`` and stays an
    inert, nonexistent literal filename. That is not itself an escape (it
    can't resolve past the caller's cwd), but a denylist that rejects the
    raw/partially-decoded string on sight is wrong in the other direction:
    it also rejects a legitimate in-bounds ``a/../b`` and a real file
    literally named ``notes..final.txt`` (#14050).

    Canonicalizing *before* the single containment check — rather than
    denylisting the raw string — makes containment the sole authority: a
    genuinely disguised traversal becomes a real ``..`` that resolves (and
    is rejected if it escapes), while in-bounds ``..`` usage resolves and is
    accepted, exactly as plain ``os.path.realpath`` already handles a
    literal ``..`` today. Callers must resolve and operate on this same
    canonical string — checking one representation and opening a different,
    still-encoded one would reintroduce the gap.
    """
    decoded = path
    for _ in range(_MAX_DECODE_ROUNDS):
        next_decoded = urllib.parse.unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return unicodedata.normalize("NFKC", decoded)


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
        If the path escapes all allowed roots, contains null bytes
        (including one smuggled in via percent-encoding), or (when
        *must_exist*) does not exist.
    """
    if not user_path or "\x00" in user_path:
        raise ValueError("Invalid path: empty or contains null bytes")

    # #14050: canonicalize (decode + normalize) *before* resolving, then let
    # the containment check below be the sole authority — see _canonicalize
    # for why a denylist on the raw string is wrong. The resolved path
    # returned is derived from this same canonical string, so a caller's
    # actual file operation and this check never see different strings.
    canonical = _canonicalize(user_path)
    if "\x00" in canonical:
        raise ValueError("Invalid path: empty or contains null bytes")

    roots = tuple(allowed_roots) if allowed_roots is not None else _DEFAULT_ALLOWED_ROOTS

    resolved = Path(os.path.realpath(canonical))

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

    # Reject the shapes that can escape BEFORE building the path expression
    # (#15786). The containment check below is the real barrier and stays; this
    # is defence in depth plus an honest answer to a specific criticism.
    #
    # `base / "/etc/passwd"` discards `base` entirely -- that is pathlib's
    # documented behaviour for an absolute right-hand side, not a bug -- so an
    # absolute segment never had anything to do with *this* base directory and
    # saying "traversal detected" after the fact describes it less accurately
    # than refusing it up front. `..` is the same: a caller that means a file
    # under `base` never needs to walk out of it.
    #
    # It also moves the sanitisation to where a reader (and a static analyser)
    # expects it: `py/path-injection` flags line ~198 because the check is a
    # post-condition on the sink rather than a pre-condition on the input. The
    # code was already safe; it now says so in the order the reader reads.
    candidate = PurePosixPath(str(user_segment).replace("\\", "/"))
    if candidate.is_absolute() or str(user_segment).startswith("/"):
        # Keeps the "Path traversal detected" prefix the existing contract
        # matches on (path_validator_test.py:293), with the detail made
        # accurate: pathlib discards the base for an absolute right-hand side,
        # so nothing traversed out -- the base was never involved.
        raise ValueError("Path traversal detected: segment is absolute, so the base directory is discarded")
    if ".." in candidate.parts:
        raise ValueError("Path traversal detected: segment contains a parent reference")

    base = Path(os.path.realpath(str(base_dir)))
    resolved = Path(os.path.realpath(str(base / user_segment)))

    # Retained, not replaced: the checks above cannot see a SYMLINK inside the
    # base that points out of it, which resolves only after `realpath`.
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError("Path traversal detected: segment escapes base directory")

    if must_exist and not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")

    return resolved


def require_path_string(value: object, *, context: str) -> str:
    """Reject anything that is not a real path — str or Path (#14217).

    A sanitizer that stringifies whatever it is handed — an object's
    ``repr()``, or (in tests) a ``MagicMock`` whose default ``__fspath__``
    embeds ``/`` separators — turns junk into a real, creatable directory
    tree the moment it reaches ``Path()`` / ``os.makedirs``. ``Path()``
    itself never raises for such a value; it happily calls
    ``os.fspath()`` and returns a multi-component path. Call this at the
    boundary, *before* the value is used as a path, so a malformed or
    unmocked config value is rejected loudly instead of silently promoted
    into a nested directory on disk.

    ``str`` and ``Path`` are both accepted — pydantic ``BaseSettings``
    fields typed ``Path`` (e.g. ``settings.backup_dir``) already coerce a
    genuine config value to ``Path`` before this ever runs, and that is a
    legitimate path, not junk. Anything else (a ``MagicMock``, an int, an
    arbitrary object) is rejected.

    Parameters
    ----------
    value:
        The candidate path value, straight from config or a caller.
    context:
        Human-readable origin of *value*, included in the raised error so
        it points at the misconfigured setting or call site.

    Returns
    -------
    str
        *value* as a ``str``, once validated.

    Raises
    ------
    TypeError
        If *value* is neither a ``str`` nor a ``Path``.
    ValueError
        If *value* is empty or contains a null byte.
    """
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        raise TypeError(f"{context}: expected a str or Path, got {type(value).__name__} instead")
    if not value or "\x00" in value:
        raise ValueError(f"{context}: path is empty or contains a null byte")
    return value


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

    # Unlike validate_path, this sandbox intentionally forbids *any* '..'
    # reference — in-bounds or not. Every caller addresses a single flat
    # file-management root with no legitimate reason to navigate above it,
    # so (unlike validate_path) a denylist is the correct design here; it
    # just needs to canonicalize to the same standard validate_path does.
    # #14050: shares _canonicalize with validate_path so a double-encoded
    # (%252e%252e) or Unicode-confusable (﹒﹒, ‥) traversal can't slip past
    # this resolver either — the single-pass unquote() this replaced only
    # caught one level of percent-encoding.
    canonical = _canonicalize(clean_path)
    if ".." in canonical or canonical.startswith("/"):
        raise SandboxPathError("Invalid path: encoded traversal not allowed")

    try:
        return validate_relative_path(clean_path, root)
    except ValueError:
        raise SandboxPathError("Path outside sandbox not allowed")
