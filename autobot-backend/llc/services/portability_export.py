# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Export data collectors for :class:`~llc.services.portability.PortabilityService`.

Split out of ``portability.py`` (#19643) so each module stays under the file-size
ceiling. Pure move: the collectors read ``self.session`` exactly as before.
"""

from typing import Any, Dict, List

import sqlalchemy as sa
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.goal import LLCGoal
from llc.models.routine import LLCRoutine
from llc.models.secret import LLCSecret
from llc.models.sprint import LLCPortfolio, LLCProject, LLCSprint
from llc.models.work_item import LLCWorkItem
from llc.services.portability_ceo import CEO_EXPORT_KEY, exported_ceo_agent_id
from llc.services.portability_export_names import export_masks

_SEED_ITEM_TYPES = ("epic", "feature")
_SEED_ITEM_LIMIT = 20


def _scrub_adapter_config(config: Dict[str, Any], secret_map: Dict[str, str]) -> Dict[str, Any]:
    """Replace secret values in adapter_config with ``{{NAME}}`` placeholders.

    Uses secret_map (name->name) for known bound secrets; falls back to
    uppercasing the key name for unrecognised secret-like keys.
    """
    scrubbed: Dict[str, Any] = {}
    for k, v in config.items():
        if export_masks(k, v):
            bound = secret_map.get(str(v)) or secret_map.get(k)
            placeholder_name = bound if bound else k.upper()
            scrubbed[k] = f"{{{{{placeholder_name}}}}}"
        else:
            scrubbed[k] = v
    return scrubbed


def _work_item_dict(item: LLCWorkItem) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "parent_id": str(item.parent_id) if item.parent_id else None,
        "project_id": str(item.project_id) if item.project_id else None,
        "sprint_id": str(item.sprint_id) if item.sprint_id else None,
        "goal_id": str(item.goal_id) if item.goal_id else None,
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "assignee_agent_id": str(item.assignee_agent_id) if item.assignee_agent_id else None,
        "assignee_user_id": str(item.assignee_user_id) if item.assignee_user_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


class PortabilityExportMixin:
    """The ``_export_*`` collectors; mixed into ``PortabilityService``."""

    session: AsyncSession

    async def _export_company(self, company_id: str) -> Dict[str, Any]:
        result = await self.session.execute(
            text("""
                SELECT id, name, slug, description, issue_prefix,
                       budget_monthly_cents, brand_color, require_approval_for_hires,
                       parent_org_id, llc_status, created_at
                FROM organizations
                WHERE id = :cid
                """),
            {"cid": company_id},
        )
        row = result.mappings().first()
        if row is None:
            return {}
        data = dict(row)
        data[CEO_EXPORT_KEY] = await exported_ceo_agent_id(self.session, company_id)
        data["id"] = str(data["id"]) if data.get("id") else None
        if data.get("parent_org_id"):
            data["parent_org_id"] = str(data["parent_org_id"])
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        return data

    async def _build_secret_map(self, company_id: str) -> Dict[str, str]:
        """Map secret binding names for this company (name -> name).

        Returns {name: name} so scrubber can substitute ``{{NAME}}``.
        Only active (non-revoked) secrets are included.
        """
        result = await self.session.execute(
            select(LLCSecret.name).where(
                sa.and_(
                    LLCSecret.company_id == company_id,
                    LLCSecret.revoked_at.is_(None),
                )
            )
        )
        return {row[0]: row[0] for row in result}

    async def _export_agents(self, company_id: str, secret_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """Export agents from agent_org_nodes with adapter_config secrets scrubbed."""
        result = await self.session.execute(
            text("""
                SELECT agent_id, name, adapter_type, adapter_config,
                       context_mode, heartbeat_cron, heartbeat_enabled,
                       llc_agent_status, created_at
                FROM agent_org_nodes
                WHERE company_id = :cid
                ORDER BY created_at
                """),
            {"cid": company_id},
        )
        agents = []
        for row in result.mappings():
            d = dict(row)
            d["agent_id"] = str(d["agent_id"]) if d.get("agent_id") else None
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            if d.get("adapter_config"):
                d["adapter_config"] = _scrub_adapter_config(d["adapter_config"], secret_map)
            agents.append(d)
        return agents

    async def _export_goals(self, company_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(LLCGoal).where(LLCGoal.company_id == company_id).order_by(LLCGoal.created_at)
        )
        goals = []
        for (goal,) in result:
            goals.append(
                {
                    "id": str(goal.id),
                    "parent_goal_id": str(goal.parent_goal_id) if goal.parent_goal_id else None,
                    "title": goal.title,
                    "description": goal.description,
                    "level": goal.level,
                    "status": goal.status,
                    "owner_agent_id": goal.owner_agent_id,
                    "created_at": goal.created_at.isoformat() if goal.created_at else None,
                }
            )
        return goals

    async def _export_routines(self, company_id: str) -> List[Dict[str, Any]]:
        """Export only ACTIVE routines (status='active')."""
        result = await self.session.execute(
            select(LLCRoutine).where(
                sa.and_(
                    LLCRoutine.company_id == company_id,
                    LLCRoutine.status == "active",
                )
            )
        )
        routines = []
        for (routine,) in result:
            routines.append(
                {
                    "id": str(routine.id),
                    "name": routine.name,
                    "description": routine.description,
                    "cron_schedule": routine.cron_schedule,
                    "assignee_agent_id": str(routine.assignee_agent_id) if routine.assignee_agent_id else None,
                    "produces": routine.produces,
                    "work_item_template": routine.work_item_template,
                    "env": routine.env,
                }
            )
        return routines

    async def _export_projects_portfolios(self, company_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        portfolios_result = await self.session.execute(
            select(LLCPortfolio).where(LLCPortfolio.company_id == company_id)
        )
        portfolios = [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "status": p.status,
            }
            for (p,) in portfolios_result
        ]

        projects_result = await self.session.execute(select(LLCProject).where(LLCProject.company_id == company_id))
        projects = [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "program_id": str(p.program_id) if p.program_id else None,
                "goal_id": str(p.goal_id) if p.goal_id else None,
                "target_date": p.target_date.isoformat() if p.target_date else None,
                "env": p.env,
                "auto_rollover": p.auto_rollover,
            }
            for (p,) in projects_result
        ]
        return projects, portfolios

    async def _export_seed_items(self, company_id: str) -> List[Dict[str, Any]]:
        """Up to 20 epic/feature work items as seed tasks (is_seed=true)."""
        result = await self.session.execute(
            select(LLCWorkItem)
            .where(
                sa.and_(
                    LLCWorkItem.company_id == company_id,
                    LLCWorkItem.type.in_(list(_SEED_ITEM_TYPES)),
                )
            )
            .order_by(LLCWorkItem.created_at)
            .limit(_SEED_ITEM_LIMIT)
        )
        items = []
        for (item,) in result:
            items.append({**_work_item_dict(item), "is_seed": True})
        return items

    async def _export_all_work_items(self, company_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(LLCWorkItem).where(LLCWorkItem.company_id == company_id).order_by(LLCWorkItem.created_at)
        )
        return [_work_item_dict(item) for (item,) in result]

    async def _export_sprints(self, company_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(LLCSprint).where(LLCSprint.company_id == company_id).order_by(LLCSprint.start_date)
        )
        sprints = []
        for (s,) in result:
            sprints.append(
                {
                    "id": str(s.id),
                    "project_id": str(s.project_id) if s.project_id else None,
                    "name": s.name,
                    "status": s.status,
                    "start_date": s.start_date.isoformat() if s.start_date else None,
                    "end_date": s.end_date.isoformat() if s.end_date else None,
                    "goal": s.goal,
                }
            )
        return sprints
