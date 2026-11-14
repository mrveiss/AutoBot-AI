# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Node-level post-sync: one ordered plan per node, every action recorded (#17455).

``POST /nodes/{node_id}/sync`` syncs ALL ACTIVE roles on a node, then runs ONE plan:
each role's actions (``roles._classify_post_sync``) through ``ordered_post_sync_plan``
-- installs, schema, builds, restarts across roles, ollama once, chromadb before
ai-stack, slm-backend last -- executed by ``services/post_sync_plan_runner``.
``POST /roles/{role_name}/sync`` (api/code_sync.py) uses the same path for its one role
on each node, so there is a single execution path for post-sync work.
``GET /code-sync/post-sync-runs/{run_id}`` returns what a run recorded.

Auth is the same as ``POST /roles/{role_name}/sync``: the route's own
``get_current_user`` plus the include-level ``require_service_management_or_internal``
main.py attaches to ``code_sync_router`` / ``nodes_router``; both new routers are
mounted on those two in ``api/__init__.py``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api._post_sync_plan import _RESTART_LAST_UNITS, ordered_post_sync_plan
from api.roles import PostSyncAction, _classify_post_sync
from autobot_shared.async_compat import fire_and_forget
from models.database import Node, NodeRole, Role, RoleStatus
from models.post_sync_action_run import PostSyncActionRun
from models.post_sync_schemas import NodePostSyncResponse, NodeRoleSyncResult, PostSyncRunResponse
from services.auth import get_current_user
from services.database import db_service, get_db
from services.post_sync_plan_runner import NodeConn, PlanResult, execute_plan, issue_deferred, record_issued
from services.post_sync_recorder import RunContext
from services.service_restart import wait_for_response_flush
from services.sync_orchestrator import get_sync_orchestrator

logger = logging.getLogger(__name__)

#: Mounted on ``nodes_router`` -> ``/api/nodes/{node_id}/sync``.
router = APIRouter(tags=["nodes"])
#: Mounted on ``code_sync_router`` -> ``/api/code-sync/post-sync-runs/{run_id}``.
runs_router = APIRouter(tags=["code-sync"])


@dataclass
class NodeSyncOutcome:
    """What syncing a set of roles on one node did."""

    node_id: str
    roles: List[dict] = field(default_factory=list)  # {"role_name", "success", "message"}
    plan: PlanResult = field(default_factory=PlanResult)


def build_node_actions(roles: List[Role], restart: bool) -> List[PostSyncAction]:
    """Every role's post-sync actions. A command the classifier does not recognise still runs."""
    actions: List[PostSyncAction] = []
    for role in roles:
        found = _classify_post_sync(role)
        if role.post_sync_cmd and not any(a.category != "restart" for a in found):
            display = role.display_name or role.name
            found.insert(
                0,
                PostSyncAction(
                    role_name=role.name,
                    display_name=display,
                    category="post_sync",
                    label=f"Post-sync ({display})",
                    command=role.post_sync_cmd,
                ),
            )
        actions.extend(a for a in found if restart or a.category != "restart")
    return actions


async def _load_roles(names: List[str]) -> List[Role]:
    async with db_service.session() as db:
        result = await db.execute(select(Role).where(Role.name.in_(names)))
        return list(result.scalars().all())


async def _sync_role_files(orchestrator, node_id: str, role_names: List[str], commit: str):
    """File-sync each role; returns (per-role results, synced role names, connection of the node)."""
    results, synced, conn = [], [], None
    for name in role_names:
        ok, msg, ctx = await orchestrator.sync_role_files(node_id, name, commit)
        results.append({"role_name": name, "success": ok, "message": msg if not ok else "files synced"})
        if ok:
            synced.append(name)
            conn = conn or NodeConn(node_id, ctx.node_ip, ctx.node_user, ctx.node_port)
    return results, synced, conn


async def sync_node_roles(
    node_id: str, role_names: List[str], commit: str, restart: bool, run_id: str, host_id: str | None = None
) -> NodeSyncOutcome:
    """File sync per role, then ONE ordered plan for the node; versions recorded only if it did not abort.

    On the SLM host (``host_id``) the self-killing restart is NOT sent here: versions are recorded
    and committed first, then an *issued* row is committed, and the restart is returned in
    ``outcome.plan.deferred`` for ``schedule_self_restarts`` to send after the response.
    """
    orchestrator = get_sync_orchestrator()
    outcome = NodeSyncOutcome(node_id)
    outcome.roles, synced, conn = await _sync_role_files(orchestrator, node_id, role_names, commit)
    if not synced:
        return outcome
    plan = ordered_post_sync_plan(build_node_actions(await _load_roles(synced), restart))
    defer = _RESTART_LAST_UNITS if node_id == host_id else ()
    outcome.plan = await execute_plan(plan, conn, RunContext(run_id, node_id, ""), defer)
    if outcome.plan.aborted:
        return outcome
    for name in synced:
        await orchestrator.record_role_synced(node_id, name, commit)
    await record_issued(outcome.plan)  # after the versions: nothing is left to lose when the restart lands
    return outcome


async def _slm_host_node_id() -> str | None:
    """The node this SLM runs on: ``code_sync._get_local_slm_node_id`` (IP match on ``external_url``)."""
    from api.code_sync import _get_local_slm_node_id  # lazy: code_sync is its one home

    return await _get_local_slm_node_id()


async def _issue_after_flush(pending: list) -> None:
    await wait_for_response_flush()  # the same #816 flush wait the deferred SLM restarts use
    await issue_deferred(pending)


def schedule_self_restarts(outcomes: List[NodeSyncOutcome]) -> None:
    """Send every held-back self-restart AFTER the response, once all nodes are done (#17455)."""
    pending = [d for o in outcomes for d in o.plan.deferred]
    if pending:
        fire_and_forget(_issue_after_flush(pending), name="post-sync-self-restart")


def _failure_message(outcome: NodeSyncOutcome) -> str:
    failed = [r for r in outcome.plan.rows if r["success"] is False and r["category"] != "restart"]
    return f"post-sync {failed[0]['label']} failed: {failed[0]['error']}" if failed else "post-sync failed"


def _outcome_ok(outcome: NodeSyncOutcome) -> bool:
    return bool(outcome.roles) and all(r["success"] for r in outcome.roles) and not outcome.plan.aborted


async def _active_role_names(db: AsyncSession, node_id: str) -> List[str]:
    result = await db.execute(
        select(NodeRole.role_name).where(NodeRole.node_id == node_id, NodeRole.status == RoleStatus.ACTIVE.value)
    )
    return sorted(set(result.scalars().all()))


@router.post("/{node_id}/sync", response_model=NodePostSyncResponse)
async def sync_node_post_sync_plan(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    restart: bool = True,
) -> NodePostSyncResponse:
    """Sync every ACTIVE role on a node and run ONE ordered post-sync plan (#17455).

    A failed install/schema/build aborts the plan (no restarts, no role marked synced); a
    failed restart is recorded and reported in ``actions[*].success`` without failing the sync.
    """
    if (await db.execute(select(Node.node_id).where(Node.node_id == node_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node not found: {node_id}")
    from api.code_sync import _get_active_commit  # lazy: code_sync is the commit's one reader

    run_id = uuid.uuid4().hex
    commit = await _get_active_commit(db)
    names = await _active_role_names(db, node_id)
    if not names:
        return NodePostSyncResponse(
            success=True, message="No ACTIVE roles on this node", node_id=node_id, run_id=run_id
        )
    outcome = await sync_node_roles(node_id, names, commit, restart, run_id, await _slm_host_node_id())
    schedule_self_restarts([outcome])
    return _node_response(outcome, commit, run_id)


def _node_response(outcome: NodeSyncOutcome, commit: str, run_id: str) -> NodePostSyncResponse:
    ok = _outcome_ok(outcome)
    message = (
        "Synced node" if ok else (_failure_message(outcome) if outcome.plan.aborted else "Some roles failed to sync")
    )
    return NodePostSyncResponse(
        success=ok,
        message=message,
        node_id=outcome.node_id,
        commit=commit,
        run_id=run_id,
        aborted=outcome.plan.aborted,
        skipped=outcome.plan.skipped,
        roles=[NodeRoleSyncResult(**r) for r in outcome.roles],
        actions=outcome.plan.rows,
    )


async def sync_role_on_nodes(node_roles: list, role_name: str, commit: str, restart: bool):
    """``POST /roles/{role_name}/sync``'s engine: the same plan path, one run_id for all nodes.

    Returns (results, success_count, run_id, actions) -- the response fields the route
    always had, plus the run's recorded rows.
    """
    run_id = uuid.uuid4().hex
    host_id = await _slm_host_node_id()
    ordered = sorted(node_roles, key=lambda nr: nr.node_id == host_id)  # the SLM host LAST (stable)
    results, success_count, actions, outcomes = [], 0, [], []
    for nr in ordered:
        outcome = await sync_node_roles(nr.node_id, [role_name], commit, restart, run_id, host_id)
        outcomes.append(outcome)
        ok = _outcome_ok(outcome)
        message = f"Synced {role_name} to {nr.node_id}" if ok else _role_failure_message(outcome)
        results.append({"node_id": nr.node_id, "success": ok, "message": message})
        success_count += ok
        actions.extend(outcome.plan.rows)
    schedule_self_restarts(outcomes)  # only now: every other node is done and every row committed
    return results, success_count, run_id, actions


def _role_failure_message(outcome: NodeSyncOutcome) -> str:
    if outcome.plan.aborted:
        return _failure_message(outcome)
    return next((r["message"] for r in outcome.roles if not r["success"]), "sync failed")


@runs_router.get("/post-sync-runs/{run_id}", response_model=PostSyncRunResponse)
async def get_post_sync_run(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> PostSyncRunResponse:
    """The rows a sync run recorded, in execution order; 404 when no row carries *run_id*."""
    result = await db.execute(
        select(PostSyncActionRun).where(PostSyncActionRun.run_id == run_id).order_by(PostSyncActionRun.id)
    )
    rows = list(result.scalars().all())
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown post-sync run: {run_id}")
    return PostSyncRunResponse(run_id=run_id, actions=rows)
