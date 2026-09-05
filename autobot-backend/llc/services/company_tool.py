# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The tool catalogue: registry identity plus one company's own facts (#14852).

Three reads and one write.

``catalogue`` joins what the registry knows (name, description, tags) to what
this company recorded (URL, logo) and to how many roles carry the tool. The
join is a **left** join in spirit: a tool with no overlay row and no attachment
still appears, because the catalogue answers "what tools exist for this
company to use", not "what has already been filled in". Dropping the unfilled
ones would hide exactly the tools someone opened the catalogue to set up.

``usage`` answers the question the issue said could not be answered from the
tool's side: which roles carry this tool, and which workflows those roles run.
It needs no new table — ``llc_role_tools`` and ``llc_role_workflows`` already
hold it, and nothing had exposed the reverse direction. It issues one query,
not two, when nothing carries the tool.

``upsert`` records the company's facts. It validates the name against the
registry for the same reason attaching does: an overlay for a name that can
never be attached is a row nothing will ever read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.company_tool import LLCCompanyTool
from ..models.role_tool import LLCRoleTool
from ..models.role_workflow import LLCRoleWorkflow
from .authz import require_company_admin
from .base import LLCServiceBase
from .tool_registry_ref import RegisteredTool, registered_tools, require_registered_tool


@dataclass(frozen=True)
class CatalogueEntry:
    """One tool as the catalogue presents it."""

    name: str
    description: str
    tags: tuple[str, ...]
    url: Optional[str]
    logo_url: Optional[str]
    #: How many roles carry this tool. Zero is meaningful — it is the
    #: difference between "nobody uses this yet" and "this does not exist".
    role_count: int


class CompanyToolService(LLCServiceBase):
    """Read the tool catalogue for a company; record that company's own facts."""

    async def _record(
        self,
        session: AsyncSession,
        overlay: LLCCompanyTool,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(overlay.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="llc_company_tool",
            entity_id=str(overlay.id),
            after=after,
        )

    async def get(self, session: AsyncSession, company_id: uuid.UUID, tool_name: str) -> Optional[LLCCompanyTool]:
        """This company's overlay row for one tool, or None when none exists."""
        result = await session.execute(
            select(LLCCompanyTool).where(
                LLCCompanyTool.company_id == company_id,
                LLCCompanyTool.tool_name == tool_name,
            )
        )
        return result.scalar_one_or_none()

    async def _overlays(self, session: AsyncSession, company_id: uuid.UUID) -> Dict[str, LLCCompanyTool]:
        result = await session.execute(select(LLCCompanyTool).where(LLCCompanyTool.company_id == company_id))
        return {row.tool_name: row for row in result.scalars()}

    async def _role_counts(self, session: AsyncSession, company_id: uuid.UUID) -> Dict[str, int]:
        result = await session.execute(
            select(LLCRoleTool.tool_name, func.count(LLCRoleTool.role_id.distinct()))
            .where(LLCRoleTool.company_id == company_id)
            .group_by(LLCRoleTool.tool_name)
        )
        return {name: count for name, count in result.all()}

    @staticmethod
    def _entry(tool: RegisteredTool, overlay: Optional[LLCCompanyTool], role_count: int) -> CatalogueEntry:
        return CatalogueEntry(
            name=tool.name,
            description=tool.description,
            tags=tool.tags,
            url=overlay.url if overlay else None,
            logo_url=overlay.logo_url if overlay else None,
            role_count=role_count,
        )

    async def catalogue(self, session: AsyncSession, company_id: uuid.UUID) -> List[CatalogueEntry]:
        """Every registered tool, carrying this company's facts where recorded.

        Driven by the registry, not by the overlay table: a tool nobody has
        recorded anything about is still a tool this company can attach.
        """
        tools = registered_tools()
        overlays = await self._overlays(session, company_id)
        counts = await self._role_counts(session, company_id)
        return [self._entry(tools[name], overlays.get(name), counts.get(name, 0)) for name in sorted(tools)]

    async def usage(self, session: AsyncSession, company_id: uuid.UUID, tool_name: str) -> Dict[str, List[str]]:
        """Which roles carry this tool, and which workflows those roles run.

        Scoped by ``company_id`` on both queries — a dropped filter on either
        reports another company's roles as carrying this tool.

        The workflow lookup is skipped when no role carries the tool. That is a
        saved round trip, **not** a correctness guard: SQLAlchemy renders
        ``in_([])`` as an empty-set expression that is correctly empty on every
        dialect. An earlier revision of this docstring claimed the short-circuit
        prevented an empty ``IN ()`` from matching every row; mutation testing
        showed removing the short-circuit changed no result, which is exactly
        what that claim would have denied.
        """
        role_rows = await session.execute(
            select(LLCRoleTool.role_id).where(
                LLCRoleTool.company_id == company_id,
                LLCRoleTool.tool_name == tool_name,
            )
        )
        role_ids = [row[0] for row in role_rows.all()]
        if not role_ids:
            return {"role_ids": [], "workflow_ids": []}

        workflow_rows = await session.execute(
            select(LLCRoleWorkflow.workflow_id)
            .where(
                LLCRoleWorkflow.company_id == company_id,
                LLCRoleWorkflow.role_id.in_(role_ids),
            )
            .distinct()
        )
        return {
            "role_ids": [str(role_id) for role_id in role_ids],
            "workflow_ids": sorted(row[0] for row in workflow_rows.all()),
        }

    async def _insert_or_adopt(
        self, session: AsyncSession, company_id: uuid.UUID, tool_name: str
    ) -> tuple[Optional[LLCCompanyTool], bool]:
        """Insert the overlay row, or adopt the one a concurrent writer inserted.

        Returns ``(row, created)``. ``created`` is what actually happened, not an
        inference from the row's contents: a losing writer that adopted a row
        whose fields were still empty is indistinguishable from an inserting one
        by looking at the row, and the activity log should not have to guess.

        ``upsert`` reads before it writes, and between those two steps another
        request for the same ``(company, tool)`` can insert the row. The unique
        index then rejects this insert, and without this the ``IntegrityError``
        surfaces as a 500 on what is a ``PUT`` — an idempotent operation that a
        double-click or a client retry can genuinely issue twice.

        The insert runs in a SAVEPOINT so a conflict rolls back only the failed
        insert and leaves the surrounding transaction usable; rolling back the
        whole session here would discard the caller's work as well. On conflict
        the winner's row is re-read and returned, so both requests converge on
        one row and last-write-wins on the fields.

        A savepoint rather than dialect-specific ``ON CONFLICT``: the same code
        then covers PostgreSQL in production and SQLite under test, and the
        conflict branch is reachable by a test rather than skipped on the
        dialect that runs in CI.
        """
        try:
            async with session.begin_nested():
                overlay = LLCCompanyTool(company_id=company_id, tool_name=tool_name)
                session.add(overlay)
                await session.flush()
            return overlay, True
        except IntegrityError:
            # The other writer won. Its row is the one that exists, so use it.
            return await self.get(session, company_id, tool_name), False

    async def upsert(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        tool_name: str,
        url: Optional[str],
        logo_url: Optional[str],
        actor_user_id: uuid.UUID,
    ) -> LLCCompanyTool:
        """Record or update this company's facts about one registered tool."""
        if company_id is None:
            raise ValueError("company_id is required")

        await require_company_admin(session, company_id, actor_user_id)
        cleaned = require_registered_tool(tool_name)

        overlay = await self.get(session, company_id, cleaned)
        created = False
        if overlay is None:
            overlay, created = await self._insert_or_adopt(session, company_id, cleaned)
            if overlay is None:
                # Neither our insert nor the conflict re-read produced a row.
                # Refusing beats returning None to a caller typed to receive a
                # row, which would surface as an AttributeError far from here.
                raise ValueError(f"could not record company facts for tool {cleaned!r}")

        overlay.url = url
        overlay.logo_url = logo_url
        await session.flush()
        await self._record(
            session,
            overlay,
            "company_tool.created" if created else "company_tool.updated",
            actor_user_id,
            {"tool_name": cleaned, "url": url, "logo_url": logo_url},
        )
        return overlay
