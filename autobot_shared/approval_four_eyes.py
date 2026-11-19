# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one four-eyes rule (#18430, #8214): who may approve their own request.

The one who asked may approve their own request only when they are the single person eligible
to decide. Each caller supplies who is eligible, because that differs: a company's active owners
and admins, or the platform's active admins. Comparing the set rather than counting it means a
requester who is not eligible cannot pass because someone else is the sole admin.

No database access here, so any layer can use it. A caller reads the eligible set under a row
lock in the decision's transaction, so nobody can leave after the check.
"""

from __future__ import annotations

import uuid
from typing import Optional


class FourEyesError(ValueError):
    """The decider may not approve this request."""


def requester_id(requested_by: object) -> Optional[uuid.UUID]:
    """The person who asked, from a bare user id or ``<kind>:<user id>``; None when it names nobody."""
    try:
        return uuid.UUID(str(requested_by).rsplit(":", 1)[-1])
    except ValueError:
        return None


def four_eyes_self_approval(
    decider: uuid.UUID, requester: uuid.UUID, eligible: set[uuid.UUID], *, what: str, who: str = "owner or admin"
) -> bool:
    """True for a self-approval by the single eligible person, False for another decider; raises when refused."""
    if decider != requester:
        return False
    if eligible != {decider}:
        raise FourEyesError(f"{what} needs a different {who} than the one who asked for it")
    return True
