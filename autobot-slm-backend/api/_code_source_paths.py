# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Root confinement for a code-source repo_path (#17300, CodeQL 452/453).

Extracted from `code_source.py`, which is grandfathered at its file-size ceiling
(#5060) and may not grow.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, status

from autobot_shared.env_utils import env_str
from autobot_shared.security.path_validator import validate_path

logger = logging.getLogger(__name__)

#: Roots a code-source repo_path may live under (#17300, CodeQL 452/453).
#: `repo_path` arrives from a POST body and reached Path(...).is_dir()/.iterdir()
#: with no confinement, so any authenticated user -- these routes are gated by
#: get_current_user, NOT by an admin role -- could probe for the existence of
#: arbitrary paths on the host. The default is the default repo_path, so an
#: ordinary deployment is unaffected; an operator with the checkout elsewhere
#: adds it here rather than the code allowing everything by omission.
_ALLOWED_ROOTS_ENV = "AUTOBOT_CODE_SOURCE_ALLOWED_ROOTS"


def _allowed_repo_roots() -> list[str] | None:
    """Roots from the env var, or None to use `validate_path`'s own default.

    None rather than restating the default here: `path_validator` already owns
    it (`_DEFAULT_ALLOWED_ROOTS`), and a second copy is a value that can drift
    from the one actually enforced -- which is the whole subject of the
    constraints work in this PR, one layer down.
    """
    raw = env_str(_ALLOWED_ROOTS_ENV, "").strip()
    if not raw:
        return None
    return [r.strip() for r in raw.split(",") if r.strip()]


def _confined_repo_path(repo_path: str) -> Path:
    """Resolve *repo_path* inside an allowed root, or raise HTTP 400.

    The message deliberately does not echo the path back: a caller who supplied
    it already knows it, and one probing does not need confirmation.
    """
    try:
        return validate_path(repo_path, allowed_roots=_allowed_repo_roots())
    except ValueError as exc:
        logger.warning("Rejected a code-source repo_path outside the allowed roots: %r (%s)", repo_path, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path is not inside an allowed root (see {_ALLOWED_ROOTS_ENV})",
        ) from None


def _similar_path_parent(parent_dir: str) -> Path:
    """The directory to scan for a case-insensitive sibling, confined first.

    `_find_similar_paths` used to `iterdir()` whatever directory the caller's
    repo_path pointed at, which is how a typo-suggestion feature became a
    filesystem oracle (#17300).
    """
    return validate_path(parent_dir, allowed_roots=_allowed_repo_roots())
