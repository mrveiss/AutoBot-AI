# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PortabilityService — company template export/import with collision detection (GH#8246).

Depends on GH#8245 (export) for the shared template schema version "1.0".
"""

import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from llc.models.enums import LLCAgentStatus, LLCCompanyStatus
from llc.models.goal import LLCGoal
from llc.models.routine import LLCRoutine
from llc.models.sprint import LLCProject
from llc.models.work_item import LLCWorkItem
from llc.services.base import LLCServiceBase
from user_management.models.organization import Organization

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


# ---------------------------------------------------------------------------
# Pydantic response models live in llc/models/portability.py (imported below)
# to keep service lean.  We use plain dicts internally.
# ---------------------------------------------------------------------------


class ImportError(Exception):
    """Raised when import cannot proceed (schema, collision, rollback)."""


class PortabilityService(LLCServiceBase):
    """Service for company template import (GH#8246).

    All methods accept an ``AsyncSession`` and participate in the caller's
    transaction.  ``execute_import`` manages its own savepoint for rollback.
    """

    def __init__(self, session: AsyncSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def preview_import(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Return collision/creation preview without writing anything."""
        self._validate_schema(template)
        company_meta = template.get("company", {})
        agents = template.get("agents", [])
        goals = template.get("goals", [])
        projects = template.get("projects", [])
        work_items = template.get("work_items", [])

        collisions: List[Dict[str, Any]] = []
        warnings: List[str] = []

        # issue_prefix collision
        prefix = company_meta.get("issue_prefix")
        if prefix:
            existing = await self._prefix_exists(prefix)
            if existing:
                collisions.append({"type": "issue_prefix", "value": prefix})

        # agent name collisions (company_id is unknown at preview time — check globally)
        agent_names = [a.get("name") for a in agents if a.get("name")]
        conflicting_agents = await self._agent_names_exist(agent_names)
        for name in conflicting_agents:
            collisions.append({"type": "agent_name", "value": name})

        # goal title collisions (global — no company yet)
        goal_titles = [g.get("title") for g in goals if g.get("title")]
        conflicting_goals = await self._goal_titles_exist(goal_titles)
        for title in conflicting_goals:
            collisions.append({"type": "goal_title", "value": title})

        # secret placeholder warning
        all_placeholders: set[str] = set()
        for agent in agents:
            cfg = agent.get("adapter_config") or {}
            all_placeholders.update(_PLACEHOLDER_RE.findall(str(cfg)))
        if all_placeholders:
            warnings.append(f"Secret placeholders found that require mapping: {sorted(all_placeholders)}")

        return {
            "collisions": collisions,
            "will_create": {
                "agents": len(agents),
                "goals": len(goals),
                "projects": len(projects),
                "work_items": len(work_items),
            },
            "warnings": warnings,
        }

    async def execute_import(
        self,
        template: Dict[str, Any],
        *,
        target_company_id: Optional[uuid.UUID] = None,
        remapping_options: Optional[Dict[str, Any]] = None,
        secret_mapping: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Transactional import.  Rolls back entirely on any entity failure."""
        self._validate_schema(template)
        remapping_options = remapping_options or {}
        secret_mapping = secret_mapping or {}

        created_entities: Dict[str, Any] = {
            "agents": [],
            "goals": [],
            "projects": [],
            "work_items": [],
        }
        skipped: Dict[str, List[str]] = {"agents": [], "goals": [], "work_items": []}
        warnings: List[str] = []

        sp = await self.session.begin_nested()
        try:
            company_id = await self._resolve_or_create_company(template, target_company_id, remapping_options, warnings)

            # agents
            agent_id_map: Dict[str, str] = {}
            for agent in template.get("agents", []):
                agent_id = await self._import_agent(agent, company_id, secret_mapping, warnings)
                if agent_id:
                    agent_id_map[agent.get("agent_id", "")] = agent_id
                    created_entities["agents"].append(agent_id)
                else:
                    skipped["agents"].append(agent.get("name", ""))

            # goals
            goal_id_map: Dict[str, str] = {}
            for goal in template.get("goals", []):
                goal_id = await self._import_goal(goal, company_id)
                if goal_id:
                    goal_id_map[str(goal.get("id", ""))] = str(goal_id)
                    created_entities["goals"].append(str(goal_id))
                else:
                    skipped["goals"].append(goal.get("title", ""))

            # projects
            for project in template.get("projects", []):
                project_id = await self._import_project(project, company_id)
                if project_id:
                    created_entities["projects"].append(str(project_id))

            # seed work items
            for item in template.get("work_items", []):
                if not item.get("is_seed"):
                    continue
                item_id = await self._import_work_item(item, company_id)
                if item_id:
                    created_entities["work_items"].append(str(item_id))
                else:
                    skipped["work_items"].append(item.get("title", ""))

            await sp.commit()
        except Exception as exc:
            await sp.rollback()
            raise ImportError(f"Import rolled back: {exc}") from exc

        return {
            "company_id": str(company_id),
            "created_entities": created_entities,
            "skipped": skipped,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Private helpers — collision checks
    # ------------------------------------------------------------------

    async def _prefix_exists(self, prefix: str) -> bool:
        result = await self.session.execute(select(Organization.id).where(Organization.issue_prefix == prefix).limit(1))
        return result.scalar() is not None

    async def _agent_names_exist(self, names: List[str]) -> List[str]:
        if not names:
            return []
        rows = await self.session.execute(
            text("SELECT name FROM agent_org_nodes WHERE name = ANY(:names)").bindparams(names=names)
        )
        return [r[0] for r in rows]

    async def _goal_titles_exist(self, titles: List[str]) -> List[str]:
        if not titles:
            return []
        result = await self.session.execute(select(LLCGoal.title).where(LLCGoal.title.in_(titles)))
        return [r[0] for r in result]

    # ------------------------------------------------------------------
    # Private helpers — entity creation
    # ------------------------------------------------------------------

    async def _resolve_or_create_company(
        self,
        template: Dict[str, Any],
        target_company_id: Optional[uuid.UUID],
        remapping_options: Dict[str, Any],
        warnings: List[str],
    ) -> uuid.UUID:
        if target_company_id:
            result = await self.session.execute(select(Organization).where(Organization.id == target_company_id))
            org = result.scalar_one_or_none()
            if org is None:
                raise ImportError(f"target_company_id {target_company_id} not found")
            return org.id

        meta = template.get("company", {})
        prefix = meta.get("issue_prefix")
        if prefix and await self._prefix_exists(prefix):
            prefix = await self._next_available_prefix(prefix)
            warnings.append(f"issue_prefix remapped to {prefix!r}")

        require_approval = remapping_options.get(
            "require_approval_for_hires",
            meta.get("require_approval_for_hires", False),
        )

        org = Organization(
            id=uuid.uuid4(),
            name=meta.get("name", "Imported Company"),
            slug=meta.get("slug", f"imported-{uuid.uuid4().hex[:8]}"),
            description=meta.get("description"),
            issue_prefix=prefix,
            budget_monthly_cents=meta.get("budget_monthly_cents", 0),
            brand_color=meta.get("brand_color"),
            require_approval_for_hires=require_approval,
            llc_status=LLCCompanyStatus.ONBOARDING.value,
            settings={},
            issue_counter=0,
            spent_monthly_cents=0,
        )
        self.session.add(org)
        await self.session.flush()
        return org.id

    async def _next_available_prefix(self, prefix: str) -> str:
        for n in range(2, 1000):
            candidate = f"{prefix}{n}"
            if not await self._prefix_exists(candidate):
                return candidate
        raise ImportError(f"Cannot find free issue_prefix for {prefix!r}")

    async def _import_agent(
        self,
        agent: Dict[str, Any],
        company_id: uuid.UUID,
        secret_mapping: Dict[str, str],
        warnings: List[str],
    ) -> Optional[str]:
        """Insert agent_org_nodes row.  Returns new agent_id or None if skipped."""
        name = agent.get("name", "")
        existing = await self._agent_names_exist([name])
        if existing:
            warnings.append(f"Agent {name!r} already exists — skipped")
            return None

        new_agent_id = str(uuid.uuid4())
        adapter_config = self._resolve_secrets(agent.get("adapter_config") or {}, secret_mapping, name, warnings)

        await self.session.execute(
            text("""
                INSERT INTO agent_org_nodes
                  (id, agent_id, name, reports_to, org_role, title, capabilities,
                   company_id, adapter_type, adapter_config, heartbeat_cron,
                   heartbeat_enabled, context_mode)
                VALUES
                  (:id, :agent_id, :name, :reports_to, :org_role, :title, :capabilities,
                   :company_id, :adapter_type, :adapter_config::jsonb, :heartbeat_cron,
                   :heartbeat_enabled, :context_mode)
                """).bindparams(
                id=uuid.uuid4(),
                agent_id=new_agent_id,
                name=name,
                reports_to=agent.get("reports_to"),
                org_role=agent.get("org_role", "worker"),
                title=agent.get("title"),
                capabilities=agent.get("capabilities"),
                company_id=company_id,
                adapter_type=agent.get("adapter_type"),
                adapter_config=__import__("json").dumps(adapter_config),
                heartbeat_cron=agent.get("heartbeat_cron"),
                heartbeat_enabled=agent.get("heartbeat_enabled", False),
                context_mode=agent.get("context_mode"),
            )
        )
        return new_agent_id

    def _resolve_secrets(
        self,
        config: Any,
        secret_mapping: Dict[str, str],
        agent_name: str,
        warnings: List[str],
    ) -> Any:
        """Replace {{SECRET_NAME}} placeholders with values from secret_mapping."""
        config_str = __import__("json").dumps(config)
        unresolved: List[str] = []

        def replace(m: re.Match) -> str:
            key = m.group(1)
            if key in secret_mapping:
                return secret_mapping[key]
            unresolved.append(key)
            return m.group(0)

        resolved_str = _PLACEHOLDER_RE.sub(replace, config_str)
        if unresolved:
            warnings.append(f"Agent {agent_name!r}: unresolved secret placeholders {unresolved}")
        return __import__("json").loads(resolved_str)

    async def _import_goal(self, goal: Dict[str, Any], company_id: uuid.UUID) -> Optional[uuid.UUID]:
        title = goal.get("title", "")
        existing = await self._goal_titles_exist([title])
        if existing:
            return None

        new_id = uuid.uuid4()
        obj = LLCGoal(
            id=new_id,
            company_id=str(company_id),
            title=title,
            description=goal.get("description"),
            level=goal.get("level", "objective"),
            status=goal.get("status", "draft"),
            owner_agent_id=None,
            due_date=None,
        )
        self.session.add(obj)
        await self.session.flush()
        return new_id

    async def _import_project(self, project: Dict[str, Any], company_id: uuid.UUID) -> Optional[uuid.UUID]:
        new_id = uuid.uuid4()
        obj = LLCProject(
            id=new_id,
            company_id=company_id,
            name=project.get("name", "Imported Project"),
            description=project.get("description"),
            status=project.get("status", "planning"),
        )
        self.session.add(obj)
        await self.session.flush()
        return new_id

    async def _import_work_item(self, item: Dict[str, Any], company_id: uuid.UUID) -> Optional[uuid.UUID]:
        new_id = uuid.uuid4()
        identifier = f"IMP-{new_id.hex[:8].upper()}"
        obj = LLCWorkItem(
            id=new_id,
            company_id=company_id,
            type=item.get("type", "epic"),
            identifier=identifier,
            title=item.get("title", ""),
            description=item.get("description"),
            status="backlog",
            priority=item.get("priority", "medium"),
            labels=item.get("labels", []),
        )
        self.session.add(obj)
        await self.session.flush()
        return new_id

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_schema(template: Dict[str, Any]) -> None:
        version = template.get("schema_version")
        if version != "1.0":
            raise ImportError(f"Unsupported schema_version {version!r}; expected '1.0'")
