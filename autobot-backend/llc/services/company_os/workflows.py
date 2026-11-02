# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Role-owned workflows and meta skills on the existing store (#18390).

This is the workflow layer: the ``workflows`` table that Automation already uses
(``models/workflow.py``), extended with a kind, an owner role and one trigger.
Creation goes through ``llc.services.workflow.WorkflowService`` so there is one
write path for a workflow row, not a second registry.
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.company_os import LLCRoleSkill, LLCWorkflowNode, LLCWorkflowTransition
from llc.models.company_os_enums import WorkflowKind, WorkflowTriggerKind
from llc.models.enums import WorkflowStatus
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase
from llc.services.workflow import WorkflowConflictError, WorkflowService
from models.workflow import Workflow

from .errors import CompanyOsConflict, CompanyOsError
from .loaders import get_process_row, get_workflow_row, require_role_in_company
from .triggers import validate_trigger


class CompanyOsWorkflowService(LLCServiceBase):
    def __init__(self, activity_log: Any = None) -> None:
        super().__init__(activity_log)
        self._base = WorkflowService(activity_log)

    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        *,
        workflow_id: str,
        actor: Optional[uuid.UUID],
        kind: str = WorkflowKind.WORKFLOW.value,
        name: Optional[str] = None,
        owner_role_id: Optional[uuid.UUID] = None,
        trigger_type: Optional[str] = None,
        trigger_config: Optional[dict] = None,
    ) -> Workflow:
        await require_company_admin(session, company_id, actor)
        kind = self._kind(kind)
        trigger_type, trigger_config = validate_trigger(kind, trigger_type, trigger_config)
        await self._check_ownership(session, company_id, kind, owner_role_id)
        await self._check_trigger_refs(session, company_id, trigger_type, trigger_config)
        try:
            return await self._base.create(
                session,
                company_id,
                workflow_id,
                name=name,
                actor=actor,
                kind=kind,
                owner_role_id=owner_role_id,
                trigger_type=trigger_type,
                trigger_config=trigger_config,
            )
        except WorkflowConflictError as exc:
            raise CompanyOsConflict(f"workflow {workflow_id!r} already exists") from exc

    @staticmethod
    def _kind(kind: str) -> str:
        try:
            return WorkflowKind(kind).value
        except ValueError as exc:
            raise CompanyOsError(f"unknown workflow kind {kind!r}") from exc

    async def _check_ownership(
        self, session: AsyncSession, company_id: uuid.UUID, kind: str, owner_role_id: Optional[uuid.UUID]
    ) -> None:
        if kind == WorkflowKind.META_SKILL.value:
            if owner_role_id is not None:
                raise CompanyOsError("a meta skill has no owning role")
            return
        if owner_role_id is None:
            raise CompanyOsError("a workflow belongs to exactly one role: owner_role_id is required")
        await require_role_in_company(session, company_id, owner_role_id)

    async def _check_trigger_refs(
        self, session: AsyncSession, company_id: uuid.UUID, trigger_type: Optional[str], config: dict
    ) -> None:
        if trigger_type == WorkflowTriggerKind.PROCESS_RESULT.value:
            await get_process_row(session, company_id, config["process_key"])

    async def get(self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> Workflow:
        return await get_workflow_row(session, company_id, workflow_id)

    async def list(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        *,
        kind: Optional[str] = None,
        owner_role_id: Optional[uuid.UUID] = None,
    ) -> List[Workflow]:
        stmt = select(Workflow).where(Workflow.company_id == company_id).order_by(Workflow.workflow_id)
        if kind is not None:
            stmt = stmt.where(Workflow.kind == self._kind(kind))
        if owner_role_id is not None:
            stmt = stmt.where(Workflow.owner_role_id == owner_role_id)
        return list((await session.execute(stmt)).scalars().all())

    async def update(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        *,
        actor: Optional[uuid.UUID],
        **fields: Any,
    ) -> Workflow:
        """Apply only the keys present in *fields*; ``kind`` never changes."""
        await require_company_admin(session, company_id, actor)
        row = await get_workflow_row(session, company_id, workflow_id)
        if "name" in fields:
            row.name = fields["name"]
        if "owner_role_id" in fields:
            await self._move_to_role(session, company_id, row, fields["owner_role_id"])
        if "trigger_type" in fields or "trigger_config" in fields:
            await self._set_trigger(session, company_id, row, fields)
        await session.flush()
        return row

    async def _set_trigger(self, session: AsyncSession, company_id: uuid.UUID, row: Workflow, fields: dict) -> None:
        trigger_type, config = validate_trigger(
            row.kind, fields.get("trigger_type", row.trigger_type), fields.get("trigger_config", row.trigger_config)
        )
        await self._check_trigger_refs(session, company_id, trigger_type, config)
        row.trigger_type, row.trigger_config = trigger_type, config

    async def _move_to_role(
        self, session: AsyncSession, company_id: uuid.UUID, row: Workflow, role_id: Optional[uuid.UUID]
    ) -> None:
        """Re-own a workflow. The move must keep every handoff crossing roles."""
        await self._check_ownership(session, company_id, row.kind, role_id)
        if role_id is not None and await self._handoff_clash(session, company_id, row, role_id):
            raise CompanyOsConflict("moving the workflow there would make a handoff stay within one role")
        row.owner_role_id = role_id

    async def _handoff_clash(
        self, session: AsyncSession, company_id: uuid.UUID, row: Workflow, role_id: uuid.UUID
    ) -> bool:
        out_rows = await session.execute(
            select(Workflow.owner_role_id)
            .join(LLCWorkflowTransition, LLCWorkflowTransition.handoff_row_id == Workflow.id)
            .where(LLCWorkflowTransition.workflow_row_id == row.id, Workflow.company_id == company_id)
        )
        in_rows = await session.execute(
            select(Workflow.owner_role_id)
            .join(LLCWorkflowTransition, LLCWorkflowTransition.workflow_row_id == Workflow.id)
            .where(LLCWorkflowTransition.handoff_row_id == row.id, Workflow.company_id == company_id)
        )
        return role_id in {r for (r,) in out_rows} | {r for (r,) in in_rows}

    async def update_status(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        status: str,
        *,
        actor: Optional[uuid.UUID],
    ) -> Workflow:
        """Change the lifecycle status; the same admin gate as every other write."""
        await require_company_admin(session, company_id, actor)
        row = await get_workflow_row(session, company_id, workflow_id)
        row.status = WorkflowStatus(status).value
        await session.flush()
        return row

    async def delete(
        self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str, *, actor: Optional[uuid.UUID]
    ) -> None:
        await require_company_admin(session, company_id, actor)
        row = await get_workflow_row(session, company_id, workflow_id)
        await self._refuse_if_referenced(session, company_id, row)
        for model in (LLCWorkflowTransition, LLCWorkflowNode):
            for stale in (await session.execute(select(model).where(model.workflow_row_id == row.id))).scalars():
                await session.delete(stale)
        await session.flush()
        await self._base.delete(session, company_id, workflow_id, actor=actor)

    async def _refuse_if_referenced(self, session: AsyncSession, company_id: uuid.UUID, row: Workflow) -> None:
        checks = (
            (LLCWorkflowTransition, LLCWorkflowTransition.handoff_row_id, "a handoff"),
            (LLCWorkflowNode, LLCWorkflowNode.meta_skill_row_id, "a workflow graph"),
            (LLCRoleSkill, LLCRoleSkill.meta_skill_row_id, "a role"),
        )
        for model, column, what in checks:
            hit = await session.execute(
                select(model.id).where(model.company_id == company_id, column == row.id).limit(1)
            )
            if hit.first() is not None:
                raise CompanyOsConflict(f"workflow {row.workflow_id!r} is still referenced by {what}")
