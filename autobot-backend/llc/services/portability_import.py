# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import entity helpers for :class:`~llc.services.portability.PortabilityService`.

Split out of ``portability.py`` (#19643) so each module stays under the file-size
ceiling. Pure move: reporting-line linking, secret resolution and the goal,
project and work-item inserts. ``_import_agent`` stays on the service.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.models.goal import LLCGoal
from llc.models.sprint import LLCProject
from llc.models.work_item import LLCWorkItem

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


class PortabilityImportMixin:
    """Reporting lines, secrets and entity inserts; mixed into ``PortabilityService``."""

    session: AsyncSession

    async def _link_reporting_lines(
        self,
        agents_list: List[Dict[str, Any]],
        landed: Dict[str, str],
        dropped_links: List[Dict[str, str]],
        company_id: Any,
    ) -> None:
        """Attach reports_to for agents whose manager was actually inserted (#14811).

        Runs inside execute_import's savepoint, so a failure here rolls the whole
        import back with everything else.

        A manager that was skipped leaves its subordinate as a root rather than
        pointing at a row that does not exist. That is not a silent downgrade:
        the unresolvable edge is recorded in `dropped_links` and returned to the
        caller. The alternative — keeping the pointer — made the subordinate
        vanish from the org tree entirely, because that tree matches children by
        agent_id and roots by a NULL reports_to, so an agent referencing a
        nonexistent manager is neither.
        """
        names_by_source_id = {str(a["agent_id"]): a.get("name", "") for a in agents_list if a.get("agent_id")}

        for agent in agents_list:
            source_id = str(agent.get("agent_id") or "")
            manager_source_id = str(agent.get("reports_to") or "")
            if not source_id or not manager_source_id or source_id not in landed:
                continue

            manager_dest_id = landed.get(manager_source_id)
            if manager_dest_id is None:
                dropped_links.append(
                    {
                        "agent_name": agent.get("name", ""),
                        "agent_id": landed[source_id],
                        "manager_name": names_by_source_id.get(manager_source_id, ""),
                        "manager_source_agent_id": manager_source_id,
                    }
                )
                continue

            # Scoped by company as well as agent_id. `agent_id` carries a
            # table-wide UNIQUE constraint today, so the company clause is
            # redundant — but that constraint is declared in a migration three
            # files away, and if it ever became per-company (the natural change
            # when two tenants want the same agent slug) this UPDATE would
            # silently start crossing tenants. Every sibling query on this table
            # scopes by company_id; this one was the outlier.
            await self.session.execute(
                text(
                    "UPDATE agent_org_nodes SET reports_to = :mgr " "WHERE agent_id = :aid AND company_id = :cid"
                ).bindparams(mgr=manager_dest_id, aid=landed[source_id], cid=company_id)
            )

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
