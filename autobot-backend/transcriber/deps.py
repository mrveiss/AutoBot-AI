# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/deps.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI dependencies for the transcriber: database, caller identity, access policy."""

from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request

from auth_middleware import get_current_user
from autobot_shared.auth.permissions import is_admin_role
from transcriber.database import Database

# Owner stamped on every row written before #15758: until then no route resolved
# a caller, so every request -- with or without credentials -- fell back to this
# value. Kept as a real owner so those rows stay addressable; can_access decides
# who may reach them.
DEFAULT_USER = "default"


async def get_db(request: Request) -> Database:
    return request.app.state.transcriber_db


def resolve_user_id(user: dict) -> str:
    """Map an authenticated principal to the transcriber user-id string.

    Raises 403 if the principal carries no identity field. A malformed-but-
    authenticated principal must NOT silently inherit DEFAULT_USER -- that was
    the IDOR (#9968) at the resolver level.
    """
    uid = user.get("user_id") or user.get("username")
    if not uid:
        raise HTTPException(status_code=403, detail="Authenticated principal has no identity")
    return str(uid)


def authenticate(request: Request, current_user: dict = Depends(get_current_user)) -> None:
    """Router-level dependency: authenticate the caller, then record who it is.

    Every transcriber sub-router mounts this (#15758). Before it existed nothing
    set ``request.state.user``, so each request resolved to DEFAULT_USER and could
    reach every row stamped with it. The test suites already modelled identity
    this way -- via a fixture that set ``request.state.user`` -- so this is the
    production half they assumed existed.
    """
    request.state.user = SimpleNamespace(
        id=resolve_user_id(current_user),
        is_admin=is_admin_role(current_user.get("role")),
    )


def caller_id_of(request: Request) -> str:
    """The authenticated caller id. Fails closed: never falls back to DEFAULT_USER."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user.id


def caller_is_admin(request: Request) -> bool:
    return bool(getattr(getattr(request.state, "user", None), "is_admin", False))


def can_access(row: dict, caller_id: str, *, is_admin: bool = False) -> bool:
    """Strict ownership policy for transcriber rows (recordings/projects).

    - owner == caller_id                  -> allow
    - different real users                -> deny
    - DEFAULT_USER row + real caller      -> DENY (the IDOR fixed by #9968)
    - DEFAULT_USER row + admin caller     -> allow (#15758)
    - unowned / falsy user_id row         -> deny

    The admin case is a deliberate, narrow exception, ruled by the repo owner on
    #15758. Before that fix every row was stamped DEFAULT_USER, because no route
    ever resolved a caller -- so the #9968 rule, written for a few legacy strays,
    would otherwise have made the entire existing dataset unreachable. Admins may
    reach DEFAULT_USER rows; they may NOT reach another real user rows, and no
    real user may reach DEFAULT_USER rows. This is not the shared-DEFAULT_USER
    bypass #9968 removed: nothing is shared between users.

    All transcriber-data access checks must go through this helper so the
    policy cannot fork between routes (#9863 review).
    """
    owner = row.get("user_id")
    if not owner:
        return False
    if owner == caller_id:
        return True
    return is_admin and owner == DEFAULT_USER


def caller_can_access(row: dict, request: Request) -> bool:
    """can_access for the caller of *request* -- the one path routes use."""
    return can_access(row, caller_id_of(request), is_admin=caller_is_admin(request))
