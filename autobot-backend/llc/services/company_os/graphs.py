# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Store, read and validate a workflow's process graph (#18390).

A graph is written whole (``replace``): nodes and transitions are validated as one
unit and swapped in one transaction, so a half-edited graph is never stored.
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.company_os import LLCProcess, LLCWorkflowNode, LLCWorkflowTransition
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase
from models.workflow import Workflow

from .errors import GraphInvalid
from .graph_types import GraphContext, GraphReport, GraphSpec, HandoffTarget, NodeSpec, TransitionSpec
from .graph_validation import validate_graph
from .loaders import get_workflow_row, load_meta_skills
from .role_skills import RoleSkillService


class GraphService(LLCServiceBase):
    async def build_context(
        self, session: AsyncSession, company_id: uuid.UUID, row: Workflow, spec: GraphSpec
    ) -> GraphContext:
        procs = (await session.execute(select(LLCProcess).where(LLCProcess.company_id == company_id))).scalars()
        metas = await load_meta_skills(session, company_id)
        held = frozenset()
        if row.owner_role_id is not None:
            held = await RoleSkillService().held_skill_names(session, company_id, row.owner_role_id)
        return GraphContext(
            own_workflow_id=row.workflow_id,
            own_role_id=row.owner_role_id,
            processes={p.process_key: list(p.required_skills or []) for p in procs},
            meta_skills=frozenset(metas),
            handoff_targets=await self._targets(session, company_id, spec),
            held_skills=held,
            meta_calls={k: frozenset(m.calls) for k, m in metas.items()},
        )

    async def _targets(self, session: AsyncSession, company_id: uuid.UUID, spec: GraphSpec) -> Dict[str, HandoffTarget]:
        ids = {t.handoff_workflow_id for t in spec.transitions if t.handoff_workflow_id}
        if not ids:
            return {}
        rows = await session.execute(
            select(Workflow.workflow_id, Workflow.kind, Workflow.owner_role_id).where(
                Workflow.company_id == company_id, Workflow.workflow_id.in_(ids)
            )
        )
        return {r.workflow_id: HandoffTarget(r.kind, r.owner_role_id) for r in rows}

    async def validate_spec(
        self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str, spec: GraphSpec
    ) -> GraphReport:
        row = await get_workflow_row(session, company_id, workflow_id)
        return validate_graph(spec, await self.build_context(session, company_id, row, spec))

    async def validate_stored(self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> GraphReport:
        return await self.validate_spec(
            session, company_id, workflow_id, await self.get(session, company_id, workflow_id)
        )

    async def replace(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        spec: GraphSpec,
        *,
        actor: Optional[uuid.UUID],
    ) -> GraphReport:
        """Validate then swap in *spec*. Raises :class:`GraphInvalid` on any error."""
        await require_company_admin(session, company_id, actor)
        # Lock the workflow row so two concurrent PUTs serialise rather than interleave
        # their delete-then-insert of the same graph.
        row = await get_workflow_row(session, company_id, workflow_id, lock=True)
        report = validate_graph(spec, await self.build_context(session, company_id, row, spec))
        if report.errors:
            raise GraphInvalid(report.errors)
        for model in (LLCWorkflowTransition, LLCWorkflowNode):
            await session.execute(delete(model).where(model.workflow_row_id == row.id, model.company_id == company_id))
        await self._insert(session, company_id, row, spec)
        await session.flush()
        return report

    async def _insert(self, session: AsyncSession, company_id: uuid.UUID, row: Workflow, spec: GraphSpec) -> None:
        proc_ids = {
            p.process_key: p.id
            for p in (await session.execute(select(LLCProcess).where(LLCProcess.company_id == company_id))).scalars()
        }
        wf_ids = await self._workflow_rows(session, company_id, spec)
        for i, n in enumerate(spec.nodes):
            session.add(
                LLCWorkflowNode(
                    position=i,
                    company_id=company_id,
                    workflow_row_id=row.id,
                    node_key=n.key,
                    kind=n.kind.value,
                    label=n.label,
                    process_id=proc_ids.get(n.process_key or ""),
                    meta_skill_row_id=wf_ids.get(n.meta_skill_id or ""),
                    end_outcome=n.end_outcome.value if n.end_outcome else None,
                )
            )
        for i, t in enumerate(spec.transitions):
            session.add(
                LLCWorkflowTransition(
                    position=i,
                    company_id=company_id,
                    workflow_row_id=row.id,
                    from_node_key=t.from_node,
                    to_node_key=t.to_node,
                    kind=t.kind.value,
                    retry_max=t.retry_max,
                    condition=t.condition,
                    timeout_seconds=t.timeout_seconds,
                    handoff_row_id=wf_ids.get(t.handoff_workflow_id or ""),
                )
            )

    async def _workflow_rows(
        self, session: AsyncSession, company_id: uuid.UUID, spec: GraphSpec
    ) -> Dict[str, uuid.UUID]:
        wanted = {n.meta_skill_id for n in spec.nodes if n.meta_skill_id}
        wanted |= {t.handoff_workflow_id for t in spec.transitions if t.handoff_workflow_id}
        if not wanted:
            return {}
        rows = await session.execute(
            select(Workflow.workflow_id, Workflow.id).where(
                Workflow.company_id == company_id, Workflow.workflow_id.in_(wanted)
            )
        )
        return {r.workflow_id: r.id for r in rows}

    async def get(self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> GraphSpec:
        row = await get_workflow_row(session, company_id, workflow_id)
        nodes = await self._rows(session, LLCWorkflowNode, row, LLCWorkflowNode.position)
        trans = await self._rows(session, LLCWorkflowTransition, row, LLCWorkflowTransition.position)
        proc_keys = {
            p.id: p.process_key
            for p in (await session.execute(select(LLCProcess).where(LLCProcess.company_id == company_id))).scalars()
        }
        wf_keys = await self._row_keys(session, company_id)
        return GraphSpec(
            nodes=[
                NodeSpec(
                    key=n.node_key,
                    kind=n.kind,
                    label=n.label,
                    process_key=proc_keys.get(n.process_id),
                    meta_skill_id=wf_keys.get(n.meta_skill_row_id),
                    end_outcome=n.end_outcome,
                )
                for n in nodes
            ],
            transitions=[
                TransitionSpec(
                    from_node=t.from_node_key,
                    kind=t.kind,
                    to_node=t.to_node_key,
                    retry_max=t.retry_max,
                    condition=t.condition,
                    timeout_seconds=t.timeout_seconds,
                    handoff_workflow_id=wf_keys.get(t.handoff_row_id),
                )
                for t in trans
            ],
        )

    async def _rows(self, session: AsyncSession, model, row: Workflow, order):  # noqa: ANN001, ANN202
        stmt = select(model).where(model.workflow_row_id == row.id, model.company_id == row.company_id)
        return list((await session.execute(stmt.order_by(order, model.id))).scalars().all())

    async def _row_keys(self, session: AsyncSession, company_id: uuid.UUID) -> Dict[uuid.UUID, str]:
        rows = await session.execute(select(Workflow.id, Workflow.workflow_id).where(Workflow.company_id == company_id))
        return {r.id: r.workflow_id for r in rows}
