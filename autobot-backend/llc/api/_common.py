# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared route helpers for the LLC API surface.

``_actor_id`` and the error translators were written three times over
(``roles.py``, ``contacts.py``, ``workflows.py``) with identical bodies and
three different docstrings. This is the single copy; the existing three are
tracked for migration separately so that change stays reviewable on its own.

The actor rule is the one worth stating once and keeping stated: the acting
user comes from the authenticated session and never from the request body or
query. A client-supplied actor let the audit trail's identity and its
USER/SYSTEM discriminator be whatever the caller typed (#13969 review M1).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status


def actor_id(current_user: dict) -> uuid.UUID:
    """The acting user, from the session — never from the body or query."""
    raw = current_user.get("id") or current_user.get("user_id")
    return uuid.UUID(str(raw))


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def forbidden(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def registry_unavailable(exc: Exception) -> HTTPException:
    """503, not 400.

    An unpopulated tool registry is an environment problem, and reporting it as
    a bad request tells the caller to fix their input when there is nothing
    wrong with it.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
    )
