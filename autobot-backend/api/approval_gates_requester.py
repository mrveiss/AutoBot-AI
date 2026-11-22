# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who requested an approval gate: the verified caller, never a field of the request (#20521).

The requester drives who may resubmit (``approval_gates._requester_matches``), so it is stamped server-side in the
``user:<id>`` form that ``_requester_matches`` and ``autobot_shared.approval_four_eyes.requester_id`` parse. A
requester the body names (the SLM console sends a ``data_hygiene_console`` label) is kept only as
``requested_label`` in the approval's context, for display; nothing reads it for an authorisation decision.
"""

from __future__ import annotations

from typing import Any, Mapping

from fastapi import HTTPException, status

from services.approval_execution import REQUESTED_LABEL_KEY


def stamped_requester(current_user: Mapping[str, Any]) -> str:
    """``user:<id>`` for the authenticated caller; a caller with no identity is refused (401), never anonymous."""
    ident = current_user.get("id") or current_user.get("user_id") or current_user.get("username")
    if not ident:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return f"user:{ident}"


def with_requested_label(context: dict | None, label: str | None) -> dict | None:
    """*context* with the body's requester kept as a display label; unchanged when the body named none."""
    if not label:
        return context
    return {**(context or {}), REQUESTED_LABEL_KEY: label}
