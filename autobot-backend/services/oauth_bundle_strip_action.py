# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wires the OAuth-bundle strip (#13630) behind an approved cleanup request (#17038).

A proposal is an ordinary approval-gate request (``destructive_action``) whose
context names this action:

    {"action": "oauth_bundle_strip_app_credentials", "backup_reference": "..."}

The proposer (``api.admin_oauth_bundle_strip``) cannot execute it. Approving it
runs :func:`execute_oauth_bundle_strip` through ``services.approval_execution``.
The handler refuses to run unless :func:`verify_backup` confirms the
``backup_reference`` (the owner-approved procedure's step 2), and re-evaluates every bundle at execution time, so a
provider that lost its operator config between proposal and approval is skipped,
not stripped. The outcome -- counts per provider, never values -- lands as an
ApprovalComment and an audit entry (#17038 rule 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.approval import ApprovalComment
from services import oauth_bundle_strip
from services.approval_execution import register_post_approval_action
from services.audit_logger import audit_log
from services.secrets_backup_verifier import verify_backup

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

ACTION = "oauth_bundle_strip_app_credentials"
PROPOSED_BY = "api.admin_oauth_bundle_strip"


def _comment_body(report: oauth_bundle_strip.StripReport, *, completed: bool) -> str:
    s = oauth_bundle_strip
    residual = sum(report.count(o) for o in s.NOT_CLEAN_OUTCOMES)
    parts = ", ".join(f"{report.count(o)} {o}" for o in (s.STRIPPED, s.CLEAN, *s.NOT_CLEAN_OUTCOMES, s.UNREADABLE))
    state = "completed" if completed else "INTERRUPTED -- partial run"
    return (
        f"OAuth bundle strip {state}: {parts}. Bundles not stripped or in doubt: {residual}. "
        "Still to do by the operator: one forced refresh per provider."
    )


NO_VERIFIABLE_BACKUP = "no verifiable secrets-store backup (#18281)"


async def _write_refusal(approval: "Approval", session: "AsyncSession", reason: str) -> None:
    """Record a refused execution (comment + audit) so the trail shows why nothing ran."""
    session.add(
        ApprovalComment(
            approval_id=approval.id,
            author="system",
            author_type="system",
            body=f"OAuth bundle strip REFUSED, no bundle was touched: {reason}.",
        )
    )
    await session.commit()
    await audit_log(
        "oauth_bundle.strip_app_credentials",
        result="refused",
        user_id=approval.decided_by_user,
        resource="connector_oauth_token",
        details={"approval_id": str(approval.id), "reason": reason},
    )


async def _write_trail(approval: "Approval", session: "AsyncSession", report, *, completed: bool) -> None:
    """The durable record (ApprovalComment + audit entry). Runs in a ``finally``, so a partial run is accounted for."""
    s = oauth_bundle_strip
    session.add(
        ApprovalComment(
            approval_id=approval.id,
            author="system",
            author_type="system",
            body=_comment_body(report, completed=completed),
        )
    )
    await session.commit()
    clean_run = completed and not (report.count(s.VERIFY_FAILED) or report.count(s.ERROR))
    await audit_log(
        "oauth_bundle.strip_app_credentials",
        result="success" if clean_run else "failed",
        user_id=approval.decided_by_user,
        resource="connector_oauth_token",
        details={
            "approval_id": str(approval.id),
            "completed": completed,
            "outcomes": report.summary(),
            "secret_ids": report.secret_ids,
        },
    )


async def execute_oauth_bundle_strip(approval: "Approval", session: "AsyncSession") -> None:
    """Strip the legacy app-credential copies once a human has approved."""
    from services.secrets_service import get_secrets_service

    context = approval.context or {}
    if not str(context.get("backup_reference") or "").strip():
        raise ValueError(f"approval {approval.id} names no backup_reference -- refusing to rewrite credentials")
    if not await verify_backup(str(context["backup_reference"]).strip()):
        await _write_refusal(approval, session, NO_VERIFIABLE_BACKUP)
        raise ValueError(f"approval {approval.id}: {NO_VERIFIABLE_BACKUP} -- refusing to rewrite credentials")
    report = oauth_bundle_strip.StripReport()
    completed = False
    try:
        await oauth_bundle_strip.strip_all(
            get_secrets_service(), approval.decided_by_user or "approval-executor", report
        )
        completed = True
    finally:
        await _write_trail(approval, session, report, completed=completed)


def register_strip_action() -> None:
    """Idempotent registration of the executor, with its declared proposer."""
    register_post_approval_action(ACTION, execute_oauth_bundle_strip, proposed_by=PROPOSED_BY)


__all__ = ["ACTION", "PROPOSED_BY", "execute_oauth_bundle_strip", "register_strip_action"]
