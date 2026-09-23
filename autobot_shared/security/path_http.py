# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One translation from a path-validator ``ValueError`` into an HTTP refusal (#13579).

Six call sites wrote this by hand and disagreed: three raised 400, two raised
403, and one 404. The status code a caller sees for the same rejection therefore
depended on which endpoint they happened to hit.

WHY 400, NOT 403
----------------
``validate_path`` refuses for several distinct reasons -- a decoding failure, a
``..`` segment, an absolute path, a drive qualifier, or a containment failure --
and deliberately does not say which. Containment is the sole authority and the
pre-resolution refusals are defence in depth (THREAT_MODEL, section 1). A single
status preserves that non-distinction.

403 does not. It asserts "this is a real target you may not have", which is a
claim the validator never made: validation is lexical and containment-based, and
it never asked whether the target exists. It also lets a caller separate
"outside the allowed roots" from "malformed", which maps the root boundary one
request at a time.

This follows the ruling already recorded for session ownership (#14012):
creating over an existing session id returns 409 identically for "owned by
someone else" and "no recorded owner", because a 403 on the first would confirm
who owns it. Same reasoning, same choice -- prefer the response that
distinguishes least.

400 is honest for every refusal reason: the path is not acceptable input. It was
also already the majority (three of six).

WHAT THIS DOES NOT COVER
------------------------
An endpoint where the *existence* of the resource is itself the secret wants
404, so that an out-of-bounds path is indistinguishable from a missing one.
That is strictly more opaque than 400 and is correct where it applies, so it is
not offered as a parameter here -- a call site needing it keeps its own handler
with the reason written down, rather than passing a status code into a helper
whose whole purpose is that the status is not a per-call decision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path, validate_relative_path

logger = get_logger(__name__)

#: Every refusal renders as this. Never the path, never the allowed roots: the
#: detail reaches the client, and echoing either turns a rejected probe into a
#: reply describing the filesystem layout it was probing for.
PATH_REFUSED_STATUS = 400
PATH_REFUSED_DETAIL = "Invalid path"


def _refuse(kind: str, offending: object, exc: ValueError) -> HTTPException:
    # The offending value is logged, not returned. Detection needs it; the
    # caller must not have it.
    logger.warning("%s rejected by the path validator: %r — %s", kind, offending, exc)
    return HTTPException(status_code=PATH_REFUSED_STATUS, detail=PATH_REFUSED_DETAIL)


# Named `require_contained_*`, not `validate_path_or_http`: `grep "def
# validate_path"` is the documented first move when auditing path handling, and
# #13518 exists because false hits on that grep made a reviewer read schema
# validators as containment helpers. A wrapper whose name starts with
# `validate_path` puts a non-containment function back into those results.
def require_contained_path(
    user_path: str,
    allowed_roots: Sequence[str] | None = None,
    *,
    must_exist: bool = False,
) -> Path:
    """``validate_path``, raising ``HTTPException`` instead of ``ValueError``."""
    try:
        return validate_path(user_path, allowed_roots, must_exist=must_exist)
    except ValueError as exc:
        raise _refuse("path", user_path, exc) from exc


def require_contained_relative_path(
    user_segment: str,
    base_dir: str | Path,
    *,
    must_exist: bool = False,
) -> Path:
    """``validate_relative_path``, raising ``HTTPException`` instead of ``ValueError``."""
    try:
        return validate_relative_path(user_segment, base_dir, must_exist=must_exist)
    except ValueError as exc:
        raise _refuse("relative path", user_segment, exc) from exc
