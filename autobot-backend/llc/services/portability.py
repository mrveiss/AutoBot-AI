# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PortabilityService — company template export/import with collision detection (GH#8246).

Depends on GH#8245 (export) for the shared template schema version "1.0".
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from llc.models.enums import LLCCompanyStatus
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


class TemplateImportError(Exception):
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

    async def preview_import(
        self,
        template: Dict[str, Any],
        *,
        target_company_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
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

        # agent name collisions — scoped to target company; new-company imports
        # have no pre-existing namespace so there is nothing to collide with
        agent_names = [a.get("name") for a in agents if a.get("name")]
        if target_company_id and agent_names:
            conflicting_agents = await self._agent_names_exist(agent_names, target_company_id)
            for name in conflicting_agents:
                collisions.append({"type": "agent_name", "value": name})

        # goal title collisions — scoped to target company for the same reason
        goal_titles = [g.get("title") for g in goals if g.get("title")]
        if target_company_id and goal_titles:
            conflicting_goals = await self._goal_titles_exist(goal_titles, target_company_id)
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

            # Pass 1: pre-mint all agent IDs so reports_to can be remapped before
            # any INSERT, avoiding topology-ordering FK violations
            agents_list = template.get("agents", [])
            agent_id_map: Dict[str, str] = {
                a.get("agent_id", ""): str(uuid.uuid4())
                for a in agents_list
                if a.get("agent_id")
            }

            # Pass 2: insert agents with remapped reports_to
            for agent in agents_list:
                agent_id = await self._import_agent(agent, company_id, secret_mapping, warnings, agent_id_map)
                if agent_id:
                    created_entities["agents"].append(agent_id)
                else:
                    skipped["agents"].append(agent.get("name", ""))

            # goals
            for goal in template.get("goals", []):
                goal_id = await self._import_goal(goal, company_id)
                if goal_id:
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
            raise TemplateImportError(f"Import rolled back: {exc}") from exc

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

    async def _agent_names_exist(
        self, names: List[str], company_id: Optional[uuid.UUID] = None
    ) -> List[str]:
        if not names:
            return []
        if company_id is not None:
            rows = await self.session.execute(
                text("SELECT name FROM agent_org_nodes WHERE name = ANY(:names) AND company_id = :company_id")
                .bindparams(names=names, company_id=str(company_id))
            )
        else:
            rows = await self.session.execute(
                text("SELECT name FROM agent_org_nodes WHERE name = ANY(:names)").bindparams(names=names)
            )
        return [r[0] for r in rows]

    async def _goal_titles_exist(
        self, titles: List[str], company_id: Optional[uuid.UUID] = None
    ) -> List[str]:
        if not titles:
            return []
        q = select(LLCGoal.title).where(LLCGoal.title.in_(titles))
        if company_id is not None:
            q = q.where(LLCGoal.company_id == str(company_id))
        result = await self.session.execute(q)
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
                raise TemplateImportError(f"target_company_id {target_company_id} not found")
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
        raise TemplateImportError(f"Cannot find free issue_prefix for {prefix!r}")

    async def _import_agent(
        self,
        agent: Dict[str, Any],
        company_id: uuid.UUID,
        secret_mapping: Dict[str, str],
        warnings: List[str],
        agent_id_map: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Insert agent_org_nodes row.  Returns new agent_id or None if skipped."""
        name = agent.get("name", "")
        existing = await self._agent_names_exist([name], company_id)
        if existing:
            warnings.append(f"Agent {name!r} already exists — skipped")
            return None

        # Use pre-minted ID from two-pass map if available
        old_id = agent.get("agent_id", "")
        new_agent_id = (agent_id_map or {}).get(old_id) or str(uuid.uuid4())

        # Remap reports_to from source UUID to destination UUID
        old_reports_to = agent.get("reports_to")
        reports_to: Optional[str] = None
        if old_reports_to and agent_id_map:
            reports_to = agent_id_map.get(str(old_reports_to))

        adapter_config = self._resolve_secrets(agent.get("adapter_config") or {}, secret_mapping, name, warnings)

        # capabilities is TEXT in the schema; serialize list/dict to JSON string
        capabilities = agent.get("capabilities")
        if isinstance(capabilities, (list, dict)):
            capabilities = json.dumps(capabilities)

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
                reports_to=reports_to,
                org_role=agent.get("org_role", "worker"),
                title=agent.get("title"),
                capabilities=capabilities,
                company_id=company_id,
                adapter_type=agent.get("adapter_type"),
                adapter_config=json.dumps(adapter_config),
                heartbeat_cron=agent.get("heartbeat_cron"),
                heartbeat_enabled=agent.get("heartbeat_enabled", False),
                context_mode=agent.get("context_mode", "thin"),
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
        """Replace {{SECRET_NAME}} placeholders in config by walking the structure.

        Operates on the decoded Python object (not the JSON string) to prevent
        injection when secret values contain quote characters.
        """
        unresolved: set[str] = set()

        def _walk(node: Any) -> Any:
            if isinstance(node, str):
                def _replace(m: re.Match) -> str:
                    key = m.group(1)
                    if key in secret_mapping:
                        return secret_mapping[key]
                    unresolved.add(key)
                    return m.group(0)
                return _PLACEHOLDER_RE.sub(_replace, node)
            if isinstance(node, dict):
                return {k: _walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [_walk(v) for v in node]
            return node

        result = _walk(config)
        if unresolved:
            warnings.append(f"Agent {agent_name!r}: unresolved secret placeholders {sorted(unresolved)}")
        return result

    async def _import_goal(self, goal: Dict[str, Any], company_id: uuid.UUID) -> Optional[uuid.UUID]:
        title = goal.get("title", "")
        existing = await self._goal_titles_exist([title], company_id)
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
            raise TemplateImportError(f"Unsupported schema_version {version!r}; expected '1.0'")
