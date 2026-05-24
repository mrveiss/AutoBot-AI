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

import sqlalchemy as sa
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc
from llc.models.enums import LLCCompanyStatus
from llc.models.export import LLCExportArtifact
from llc.models.goal import LLCGoal
from llc.models.routine import LLCRoutine
from llc.models.secret import LLCSecret
from llc.models.sprint import LLCPortfolio, LLCProgram, LLCProject, LLCSprint
from llc.models.work_item import LLCWorkItem
from llc.services.activity_log import ActivityEventType, LLCActivityLogService
from llc.services.base import LLCServiceBase
from user_management.models.organization import Organization

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

_SCHEMA_VERSION = "1.0"
_EXPORT_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_SEED_ITEM_TYPES = ("epic", "feature")
_SEED_ITEM_LIMIT = 20
_SECRET_LIKE_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "token",
        "access_token",
        "secret",
        "password",
        "credentials",
        "private_key",
        "client_secret",
        "auth_token",
        "bearer_token",
        "key",
    }
)


# ---------------------------------------------------------------------------
# Pydantic response models live in llc/models/portability.py (imported below)
# to keep service lean.  We use plain dicts internally.
# ---------------------------------------------------------------------------


class TemplateImportError(Exception):
    """Raised when import cannot proceed (schema, collision, rollback)."""


class PortabilityService(LLCServiceBase):
    """Service for company template export/import (GH#8245, GH#8246).

    All methods accept an ``AsyncSession`` and participate in the caller's
    transaction.  ``execute_import`` manages its own savepoint for rollback.
    """

    def __init__(self, session: AsyncSession, activity_log: Optional[LLCActivityLogService] = None) -> None:
        super().__init__(activity_log=activity_log)
        self.session = session

    # ------------------------------------------------------------------
    # Export — Public API
    # ------------------------------------------------------------------

    async def export_template(self, company_id: uuid.UUID, actor: str = "system") -> Dict[str, Any]:
        """Return a portable template dict for the company.

        Includes company meta, agents (secrets scrubbed), goals, active
        routines, projects + portfolios (no sprint data), and up to 20 seed
        work items (epic/feature) marked ``is_seed=true``.  Secret values are
        never exported.
        """
        cid = str(company_id)
        secret_map = await self._build_secret_map(cid)

        company_data = await self._export_company(cid)
        agents_data = await self._export_agents(cid, secret_map)
        goals_data = await self._export_goals(cid)
        routines_data = await self._export_routines(cid)
        projects_data, portfolios_data = await self._export_projects_portfolios(cid)
        seed_items = await self._export_seed_items(cid)

        payload = {
            "schema_version": _SCHEMA_VERSION,
            "export_kind": "template",
            "company": company_data,
            "agents": agents_data,
            "goals": goals_data,
            "routines": routines_data,
            "portfolios": portfolios_data,
            "projects": projects_data,
            "seed_work_items": seed_items,
        }

        artifact_id = await self._persist(company_id, "template", payload, actor)
        payload["artifact_id"] = str(artifact_id)
        return payload

    async def export_snapshot(self, company_id: uuid.UUID, actor: str = "system") -> Dict[str, Any]:
        """Return a full-state snapshot for backup/migration.

        Extends the template with ALL work items, sprint history rows, and KB
        collection names (not KB content).
        """
        cid = str(company_id)
        secret_map = await self._build_secret_map(cid)

        company_data = await self._export_company(cid)
        agents_data = await self._export_agents(cid, secret_map)
        goals_data = await self._export_goals(cid)
        routines_data = await self._export_routines(cid)
        projects_data, portfolios_data = await self._export_projects_portfolios(cid)
        all_items = await self._export_all_work_items(cid)
        sprints_data = await self._export_sprints(cid)
        kb_collections = await self._list_kb_collections(cid)

        payload = {
            "schema_version": _SCHEMA_VERSION,
            "export_kind": "snapshot",
            "company": company_data,
            "agents": agents_data,
            "goals": goals_data,
            "routines": routines_data,
            "portfolios": portfolios_data,
            "projects": projects_data,
            "work_items": all_items,
            "sprints": sprints_data,
            "kb_collection_names": kb_collections,
        }

        artifact_id = await self._persist(company_id, "snapshot", payload, actor)
        payload["artifact_id"] = str(artifact_id)
        return payload

    # ------------------------------------------------------------------
    # Import — Public API
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
                a.get("agent_id", ""): str(uuid.uuid4()) for a in agents_list if a.get("agent_id")
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
    # Private helpers — export data collectors
    # ------------------------------------------------------------------

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

    async def _list_kb_collections(self, company_id: str) -> List[str]:
        """Return KB collection names for the company (not content)."""
        redis = await get_async_redis_client()
        if redis is None:
            return []
        pattern = f"llc:kb:{company_id}:*"
        keys = await redis.keys(pattern)
        names = []
        for k in keys:
            key_str = k.decode("utf-8") if isinstance(k, bytes) else k
            parts = key_str.split(":")
            if len(parts) >= 4:
                names.append(":".join(parts[3:]))
        return sorted(names)

    # ------------------------------------------------------------------
    # Private helpers — export persistence
    # ------------------------------------------------------------------

    async def _persist(self, company_id: uuid.UUID, export_kind: str, payload: Dict[str, Any], actor: str) -> uuid.UUID:
        artifact_id = uuid.uuid4()
        storage_path = f"llc:export:{company_id}:{artifact_id}"

        redis = await get_async_redis_client()
        if redis is not None:
            await redis.set(
                storage_path,
                json.dumps(payload, default=str, ensure_ascii=False),
                ex=_EXPORT_TTL_SECONDS,
            )

        artifact = LLCExportArtifact(
            id=artifact_id,
            company_id=company_id,
            export_kind=export_kind,
            schema_version=_SCHEMA_VERSION,
            storage_path=storage_path,
            created_by=actor,
        )
        self.session.add(artifact)

        if self.activity_log:
            event_type = (
                ActivityEventType.COMPANY_EXPORT_TEMPLATE
                if export_kind == "template"
                else ActivityEventType.COMPANY_EXPORT_SNAPSHOT
            )
            await self.activity_log.append(
                session=self.session,
                company_id=company_id,
                event_type=event_type,
                after={"artifact_id": str(artifact_id), "storage_path": storage_path},
            )

        return artifact_id

    # ------------------------------------------------------------------
    # Private helpers — collision checks
    # ------------------------------------------------------------------

    async def _prefix_exists(self, prefix: str) -> bool:
        result = await self.session.execute(select(Organization.id).where(Organization.issue_prefix == prefix).limit(1))
        return result.scalar() is not None

    async def _agent_names_exist(self, names: List[str], company_id: Optional[uuid.UUID] = None) -> List[str]:
        if not names:
            return []
        if company_id is not None:
            rows = await self.session.execute(
                text(
                    "SELECT name FROM agent_org_nodes WHERE name = ANY(:names) AND company_id = :company_id"
                ).bindparams(names=names, company_id=str(company_id))
            )
        else:
            rows = await self.session.execute(
                text("SELECT name FROM agent_org_nodes WHERE name = ANY(:names)").bindparams(names=names)
            )
        return [r[0] for r in rows]

    async def _goal_titles_exist(self, titles: List[str], company_id: Optional[uuid.UUID] = None) -> List[str]:
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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _scrub_adapter_config(config: Dict[str, Any], secret_map: Dict[str, str]) -> Dict[str, Any]:
    """Replace secret values in adapter_config with ``{{NAME}}`` placeholders.

    Uses secret_map (name->name) for known bound secrets; falls back to
    uppercasing the key name for unrecognised secret-like keys.
    """
    scrubbed: Dict[str, Any] = {}
    for k, v in config.items():
        key_lower = k.lower()
        if key_lower in _SECRET_LIKE_KEYS and v:
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


__all__ = ["PortabilityService", "TemplateImportError"]
