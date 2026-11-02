# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Roll back to an earlier commit through the builtin updater (#20214).

    GET  /code-sync/rollback/candidates   the commits that may be chosen
    GET  /code-sync/rollback/preview      what choosing one would do, and whether a migration is in the way
    POST /code-sync/rollback              start it (202, the update-all job; poll /update-all/status)

Mounted on the code-sync router (``api/__init__.py``), so it carries the include-level auth of
Update Everything, and takes the same per-request dependency (``get_current_user``). The work is in
``services/code_rollback.py``; this module is the HTTP edge only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api import code_sync as cs
from autobot_shared.logging_manager import get_logger
from models.rollback_schemas import (
    RollbackCandidates,
    RollbackCommit,
    RollbackDatabaseCheck,
    RollbackPreview,
    RollbackRequest,
)
from services import rollback_audit
from services.auth import get_current_user
from services.code_rollback import Preflight, orchestrator, preflight
from services.database import get_db
from services.rollback_commits import CommitInfo, RollbackRefused, list_candidates

logger = get_logger(__name__)

router = APIRouter(prefix="/rollback", tags=["code-sync"])

_AUDIT_DOWN = "The audit trail is unavailable, so the rollback was not started."


def _commit_model(info: CommitInfo, deployed: str | None) -> RollbackCommit:
    return RollbackCommit(
        commit=info.commit, short=info.short, date=info.date, subject=info.subject, is_deployed=info.commit == deployed
    )


def _actor(user: dict) -> str | None:
    value = user.get("sub") or user.get("username")
    return str(value) if value else None


def _bad_request(exc: RollbackRefused) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.reason)


async def _source(db: AsyncSession):
    tracker = await cs._get_tracker_for_db(db)
    return tracker.repo_path, tracker.remote, tracker.branch


@router.get("/candidates")
async def rollback_candidates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RollbackCandidates:
    """The newest commits of the tracked branch, with dates and subjects, for the picker."""
    repo, remote, branch = await _source(db)
    try:
        commits = await list_candidates(repo, remote, branch)
    except RollbackRefused as exc:
        raise _bad_request(exc) from exc
    deployed = await cs._get_slm_deployed_commit()
    return RollbackCandidates(
        branch=branch, deployed_commit=deployed, commits=[_commit_model(c, deployed) for c in commits]
    )


def _preview(result: Preflight) -> RollbackPreview:
    return RollbackPreview(
        commit=_commit_model(result.target, result.deployed),
        allowed=result.refusal is None,
        refusal=result.refusal,
        checks=[RollbackDatabaseCheck(**vars(c)) for c in result.checks],
    )


@router.get("/preview")
async def rollback_preview(
    commit: Annotated[str, Query(max_length=200)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RollbackPreview:
    """Validate one commit and say whether a database migration is in the way."""
    repo, remote, branch = await _source(db)
    try:
        return _preview(await preflight(repo, remote, branch, commit))
    except RollbackRefused as exc:
        raise _bad_request(exc) from exc


async def _refuse(user: dict, commit: str, reason: str, code: int) -> HTTPException:
    """Record a refusal in the audit trail (best effort: the refusal stands either way) and build the response."""
    try:
        await rollback_audit.record_rollback(
            actor=_actor(user),
            commit=commit,
            outcome=rollback_audit.DENIED,
            phase=rollback_audit.PHASE_REQUESTED,
            reason=reason,
        )
    except rollback_audit.AuditUnavailable:
        pass
    return HTTPException(status_code=code, detail=reason)


async def _start_after_audit(user: dict, result: Preflight) -> cs.UpdateAllJob:
    """Make the request durable, then start through the same gate Update Everything uses."""
    commit = result.target.commit
    try:
        await rollback_audit.record_rollback(
            actor=_actor(user), commit=commit, outcome=rollback_audit.SUCCESS, phase=rollback_audit.PHASE_REQUESTED
        )
    except rollback_audit.AuditUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AUDIT_DOWN) from exc
    try:
        async with cs._update_all_start_lock:
            return await cs._start_update_all_locked(orchestrate=orchestrator(result.target, _actor(user)))
    except HTTPException as exc:
        raise await _refuse(user, commit, str(exc.detail), exc.status_code) from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_rollback(
    body: RollbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> cs.UpdateAllJob:
    """Deploy the chosen earlier commit. Refused while an update runs or when a migration is in the way."""
    repo, remote, branch = await _source(db)
    try:
        result = await preflight(repo, remote, branch, body.commit)
    except RollbackRefused as exc:
        raise await _refuse(user, body.commit, exc.reason, status.HTTP_400_BAD_REQUEST) from exc
    if result.refusal is not None:
        raise await _refuse(user, result.target.commit, result.refusal, status.HTTP_409_CONFLICT)
    return await _start_after_audit(user, result)
