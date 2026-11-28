# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Validation of the one-approval-record columns (#13421 S1).

``source``, ``risk_tier``, ``expires_at``, ``payload_hash`` and ``resume_ref`` are set only by
server-side emitters through ``ApprovalGateService.create_approval``. Nothing here is reachable
from ``POST /approval-gates``: a caller-chosen ``source`` would let any authenticated user pose
as the terminal, and a caller-chosen ``resume_ref`` would pick what the server resumes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from autobot_shared.content_digest import content_digest
from autobot_shared.risk_tier import parse_risk_tier
from autobot_shared.time_utils import now_utc
from models.approval import ApprovalSource
from services.approval_execution import is_registered_resume_source


def payload_hash_of(payload: Any) -> str:
    """sha256 hex of *payload* in canonical JSON, so equal payloads hash equally."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)
    return content_digest(canonical)


def _checked_expiry(expires_at: datetime | None) -> datetime | None:
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    if expires_at <= now_utc():
        raise ValueError("expires_at must be in the future")
    return expires_at


def record_fields(
    *,
    source: str | None,
    risk_tier: Any,
    expires_at: datetime | None,
    payload_hash: str | None,
    resume_ref: str | None,
    context: Dict[str, Any] | None,
    owner_user: str | None = None,
) -> Dict[str, Any]:
    """Validated column values for a new approval; every key is present, unset ones are ``None``.

    A sourced approval must be graded (``risk_tier``) and owned (``owner_user``, so the pending
    list can scope it), and must name a registered resume handler when it carries a
    ``resume_ref`` -- the same "no gate that can never resume" rule #17315
    applied to ``context["action"]``. ``payload_hash`` defaults to the hash of ``context`` for a
    sourced approval.
    """
    owner_user = owner_user.strip() if isinstance(owner_user, str) else owner_user
    fields: Dict[str, Any] = {
        "source": None,
        "risk_tier": None,
        "expires_at": _checked_expiry(expires_at),
        "payload_hash": payload_hash,
        "resume_ref": resume_ref,
        "owner_user": owner_user,
    }
    if source is None:
        if risk_tier is not None or resume_ref is not None or owner_user is not None:
            raise ValueError("risk_tier, resume_ref and owner_user require a source")
        return fields
    if not owner_user:
        raise ValueError("a sourced approval must carry the owner_user of the session that raised it")
    fields["source"] = ApprovalSource(source).value
    if risk_tier is None:
        raise ValueError("a sourced approval must carry a risk_tier")
    fields["risk_tier"] = parse_risk_tier(risk_tier).value
    if resume_ref is not None and not is_registered_resume_source(fields["source"]):
        raise ValueError(f"source {fields['source']!r} has no registered resume handler for resume_ref")
    if payload_hash is None:
        fields["payload_hash"] = payload_hash_of(context or {})
    return fields
