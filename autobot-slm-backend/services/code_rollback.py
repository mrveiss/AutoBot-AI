# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Roll back to an earlier commit through the builtin updater (#20214).

A rollback IS an Update Everything run whose target is the chosen commit instead of the branch head.
It shares the job, the start gate (``api.code_sync._start_update_all_locked``), the self-update
that restarts this service, the resume plan that survives that restart, and the fleet stage. What
differs, and why:

* Stage 1 still fetches and records the branch head as ``slm_agent_latest_commit``. That value is
  what every currency label compares a node's commit with, so after a rollback the nodes read
  OUTDATED against the latest: the drift report tells the truth, and Update Everything is the way
  back, unchanged.
* Stage 2 (pull code_source to the branch head) is skipped. The playbook checks the chosen commit
  out itself, and the next stage-2 pull works from a detached head (``sync_orchestrator``).
* ``deploy_ref`` reaches every playbook run through ``services.rollback_target``; the playbook
  does not announce the commit to ``/code-source/notify`` for a rollback, which would overwrite
  the latest-commit record with the older commit.
"""

from __future__ import annotations

from dataclasses import dataclass

from autobot_shared.logging_manager import get_logger
from services import rollback_audit
from services.rollback_commits import CommitInfo, RollbackRefused, resolve_target
from services.rollback_migrations import CLEAR, MigrationCheck, check_migrations
from services.rollback_target import rollback_scope

logger = get_logger(__name__)

_SUCCESS_STATUSES = frozenset({"completed", "already_current", "partial"})


@dataclass(frozen=True)
class Preflight:
    """Everything the operator is shown before confirming, and the gate the run must pass."""

    target: CommitInfo
    deployed: str | None
    checks: list[MigrationCheck]

    @property
    def blockers(self) -> list[MigrationCheck]:
        return [c for c in self.checks if c.status != CLEAR]

    @property
    def refusal(self) -> str | None:
        """The operator-facing reason this rollback is refused, or None when it may run."""
        if self.deployed == self.target.commit:
            return "This SLM already runs that commit. Choose an earlier one, or run Update Everything."
        if self.blockers:
            return " ".join(c.message for c in self.blockers)
        return None


async def preflight(repo: str, remote: str, branch: str, commit: object, **readers) -> Preflight:
    """Validate ``commit`` and read the migration state; raises ``RollbackRefused`` for an invalid commit."""
    from api.code_sync import _get_slm_deployed_commit

    target = await resolve_target(repo, remote, branch, commit)
    checks = await check_migrations(repo, target.commit, **readers)
    return Preflight(target=target, deployed=await _get_slm_deployed_commit(), checks=checks)


def _skip_pull_stage(cs, job) -> None:
    stage = cs._get_stage(job, "code_source_pull")
    stage.status = cs._StageStatus.SKIPPED
    stage.message = "Not used for a rollback: the chosen commit is checked out by the update itself"
    stage.completed_at = cs.utc_timestamp()


async def _revalidate_after_fetch(cs, job, db_service_ref, target: CommitInfo) -> bool:
    """The fetch can move the branch; the commit must still be part of its history."""
    async with db_service_ref.session() as db:
        tracker = await cs._get_tracker_for_db(db)
    try:
        await resolve_target(tracker.repo_path, tracker.remote, tracker.branch, target.commit)
    except RollbackRefused as exc:
        stage = cs._get_stage(job, "github_fetch")
        cs._fail_fleet_stage(job, stage, exc.reason)
        return False
    return True


async def _run_stages(cs, job, db_service_ref, target: CommitInfo) -> None:
    job.status = "running"
    cs._mark_progress(job)
    latest = await cs._run_github_stage(job, db_service_ref)
    if latest is None:
        return
    cs._stage_log(cs._get_stage(job, "github_fetch"), f"Rolling back to {target.short}: {target.subject}")
    if not await _revalidate_after_fetch(cs, job, db_service_ref, target):
        return
    _skip_pull_stage(cs, job)
    cs._mark_progress(job)
    outdated = await cs._collect_outdated_node_ids(job, target.commit, db_service_ref)
    slm_fired = await cs._run_slm_stage(job, target.commit, outdated, db_service_ref)
    cs._mark_progress(job)
    if job.status == "failed":
        return
    if slm_fired:
        await cs._reconcile_self_update_stage(job, target.commit, outdated)
        return
    await cs._run_fleet_stage_or_already_current(job, outdated, target.commit)


async def _record_end(actor: str | None, target: CommitInfo, job) -> None:
    """The final audit entry, when the run ended in this process. Never raises: the run is over."""
    if job.status in _SUCCESS_STATUSES:
        outcome = rollback_audit.SUCCESS
    elif job.status == "failed":
        outcome = rollback_audit.FAILED
    else:
        return
    try:
        await rollback_audit.record_rollback(
            actor=actor,
            commit=target.commit,
            outcome=outcome,
            phase=rollback_audit.PHASE_FINISHED,
            job_status=job.status,
        )
    except rollback_audit.RollbackAuditUnavailable:
        pass  # already logged by the writer; the job status is the record of how it ended


def orchestrator(target: CommitInfo, actor: str | None):
    """The coroutine ``_start_update_all_locked`` runs in place of the forward orchestration."""

    async def _orchestrate(job, db_service_ref) -> None:
        from api import code_sync as cs

        with rollback_scope(target.commit):
            try:
                await _run_stages(cs, job, db_service_ref, target)
            except Exception:
                await _record_error(actor, target)
                raise
        await _record_end(actor, target, job)

    return _orchestrate


async def _record_error(actor: str | None, target: CommitInfo) -> None:
    try:
        await rollback_audit.record_rollback(
            actor=actor, commit=target.commit, outcome=rollback_audit.ERROR, phase=rollback_audit.PHASE_FINISHED
        )
    except rollback_audit.RollbackAuditUnavailable:
        pass
