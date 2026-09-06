# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Designate, resolve and provision a company's CEO (#15770).

The CEO is the middle step of the default reporting chain: anyone with no
explicit line reports to the CEO, the CEO reports to the owners, an owner
terminates the walk (#15763). This service owns that designation.

**Resolution verifies the holder still exists.** A designation whose agent was
deleted is a dangling row, and reporting it as a CEO would put a node in the
chain that nothing can render. :meth:`resolve` returns ``None`` for that case,
exactly as it does for a company with no designation at all, so the walk reports
``NO_CEO`` and the chart still draws. It does **not** promote a nearby node to
fill the gap: an arbitrary promotion is a silent, wrong answer to "who runs this
company", and it is worse than a reported absence because nothing looks broken.
"""

import uuid
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_org import AgentOrgNode, OrgRole

from ..models.company_ceo import LLCCompanyCEO
from ..models.enums import RoleHolderType
from ..models.membership import LLCCompanyMembership
from .base import LLCServiceBase

#: The holders a company may designate. Mirrors ``_PLACEABLE`` in
#: :mod:`llc.services.reporting_line`: a contact is not a member of the
#: hierarchy, so it cannot hold the position either.
_DESIGNABLE = frozenset({RoleHolderType.USER.value, RoleHolderType.AGENT.value})

#: A provisioned default CEO. ``manager`` is the only ``OrgRole`` denoting
#: authority over other agents; there is no dedicated "ceo" role, and adding one
#: would put the position in two places that can disagree.
DEFAULT_CEO_NAME = "CEO"
DEFAULT_CEO_TITLE = "Chief Executive Officer"
DEFAULT_CEO_ORG_ROLE = OrgRole.MANAGER.value


def default_ceo_slug(company_id: uuid.UUID) -> str:
    """The agent slug a provisioned CEO gets.

    Derived from the company id because ``agent_org_nodes.agent_id`` is unique
    **globally**, not per company (#15812). A fixed slug would collide on the
    second company that provisioned one.
    """
    return f"ceo-{company_id}"


@dataclass(frozen=True)
class CEOHolder:
    """A resolved CEO: which kind of holder, and which row.

    Structurally identical to ``reporting_line.Holder`` and deliberately not
    imported from it: importing the reporting service here would close a cycle,
    since that module resolves the CEO through this one.
    """

    type: str
    id: uuid.UUID


class CompanyCEOService(LLCServiceBase):
    """Read and write the CEO designation for one company."""

    async def designation(self, session: AsyncSession, company_id: uuid.UUID) -> Optional[LLCCompanyCEO]:
        """The raw designation row, whether or not its holder still exists."""
        result = await session.execute(sa.select(LLCCompanyCEO).where(LLCCompanyCEO.company_id == company_id))
        return result.scalar_one_or_none()

    async def resolve(self, session: AsyncSession, company_id: uuid.UUID) -> Optional[CEOHolder]:
        """The company's CEO, or None when there is none to speak of.

        None covers two distinct states on purpose -- no designation, and a
        designation pointing at a holder that no longer exists. Both mean the
        chain has no middle step, and the caller's answer is the same for both.
        """
        row = await self.designation(session, company_id)
        if row is None or row.holder_id is None:
            return None
        if not await self._holder_exists(session, row):
            return None
        return CEOHolder(type=row.holder_type, id=row.holder_id)

    async def _holder_exists(self, session: AsyncSession, row: LLCCompanyCEO) -> bool:
        """Whether the designated holder is still a member of *this* company.

        Existence alone is not enough. A designation naming a holder from
        another company is not a CEO this company may have, and resolving it
        would let one company's chart walk into another's (CWE-639). The check
        is scoped to ``company_id`` on both sides, so a holder that has left the
        company reads exactly like a deleted one.
        """
        if row.holder_type == RoleHolderType.AGENT.value:
            result = await session.execute(
                sa.select(AgentOrgNode.id).where(
                    AgentOrgNode.id == row.holder_agent_id,
                    AgentOrgNode.company_id == row.company_id,
                )
            )
        else:
            result = await session.execute(
                sa.select(LLCCompanyMembership.id).where(
                    LLCCompanyMembership.user_id == row.holder_user_id,
                    LLCCompanyMembership.company_id == row.company_id,
                )
            )
        return result.scalars().first() is not None

    async def _require_in_company(
        self, session: AsyncSession, company_id: uuid.UUID, holder_type: str, holder_id: uuid.UUID
    ) -> None:
        """Refuse a holder that does not belong to this company (CWE-639).

        Without this, ``set_ceo`` accepts any UUID the caller supplies: an agent
        or a member of another company could be installed at the top of this
        company's chart, and the chain walk would then traverse into a tenant
        the caller has no access to. Checked on write as well as on read --
        rejecting at the boundary is what keeps a bad row out of the table,
        rather than merely declining to render one.
        """
        if holder_type == RoleHolderType.AGENT.value:
            result = await session.execute(
                sa.select(AgentOrgNode.id).where(
                    AgentOrgNode.id == holder_id,
                    AgentOrgNode.company_id == company_id,
                )
            )
        else:
            result = await session.execute(
                sa.select(LLCCompanyMembership.id).where(
                    LLCCompanyMembership.user_id == holder_id,
                    LLCCompanyMembership.company_id == company_id,
                )
            )
        if result.scalars().first() is None:
            raise ValueError(f"{holder_type} {holder_id} is not part of company {company_id}")

    async def set_ceo(
        self, session: AsyncSession, company_id: uuid.UUID, holder_type: str, holder_id: uuid.UUID
    ) -> LLCCompanyCEO:
        """Designate ``holder`` as CEO, replacing any existing designation.

        Replacing rather than adding: the position is single-valued, and the
        unique constraint on ``company_id`` would reject a second row anyway.
        """
        if holder_type not in _DESIGNABLE:
            raise ValueError(f"a {holder_type} cannot hold the CEO position")
        await self._require_in_company(session, company_id, holder_type, holder_id)

        row = await self.designation(session, company_id)
        if row is None:
            row = LLCCompanyCEO(company_id=company_id, holder_type=holder_type)
            session.add(row)

        row.holder_type = holder_type
        # Clear the other column: leaving a stale id behind produces a row whose
        # `holder_id` is right and whose contents contradict it.
        row.holder_user_id = holder_id if holder_type == RoleHolderType.USER.value else None
        row.holder_agent_id = holder_id if holder_type == RoleHolderType.AGENT.value else None
        await session.flush()
        return row

    async def clear(self, session: AsyncSession, company_id: uuid.UUID) -> bool:
        """Remove the designation. Returns whether there was one to remove."""
        row = await self.designation(session, company_id)
        if row is None:
            return False
        await session.delete(row)
        await session.flush()
        return True

    async def provision_default(self, session: AsyncSession, company_id: uuid.UUID) -> LLCCompanyCEO:
        """Give a company an agent CEO, creating the agent if it is absent.

        Returns the existing designation untouched when there already is one.
        Provisioning is not "make a new CEO" -- it is "ensure there is one" --
        and the difference matters at company creation, where a caller retrying
        must not displace a CEO an owner has since chosen.
        """
        existing = await self.designation(session, company_id)
        if existing is not None:
            return existing

        agent = await self._get_or_create_default_agent(session, company_id)
        return await self.set_ceo(session, company_id, RoleHolderType.AGENT.value, agent.id)

    async def _get_or_create_default_agent(self, session: AsyncSession, company_id: uuid.UUID) -> AgentOrgNode:
        """The company's default CEO agent, created on first use.

        Adoption is scoped to this company. ``agent_org_nodes.agent_id`` is
        unique **globally** (#15812), so a slug can in principle already be held
        by another company's agent -- and adopting it would install a foreign
        agent as this company's CEO. That case raises rather than adopting: a
        loud failure is recoverable, a cross-tenant CEO is not.

        The insert is wrapped in a savepoint so a concurrent caller that wins
        the race is adopted rather than crashing the outer transaction.
        """
        slug = default_ceo_slug(company_id)
        agent = await self._find_default_agent(session, slug, company_id)
        if agent is not None:
            return agent

        try:
            async with session.begin_nested():
                agent = AgentOrgNode(
                    agent_id=slug,
                    name=DEFAULT_CEO_NAME,
                    title=DEFAULT_CEO_TITLE,
                    org_role=DEFAULT_CEO_ORG_ROLE,
                    company_id=company_id,
                )
                session.add(agent)
                await session.flush()
            return agent
        except IntegrityError:
            # Someone else inserted it between the read and the write. Re-read
            # under the same company scope: if it is theirs, adopt it; if the
            # slug belongs to another company, `_find_default_agent` raises.
            adopted = await self._find_default_agent(session, slug, company_id)
            if adopted is None:
                raise
            return adopted

    async def _find_default_agent(
        self, session: AsyncSession, slug: str, company_id: uuid.UUID
    ) -> Optional[AgentOrgNode]:
        """The agent holding ``slug``, but only if it belongs to this company."""
        result = await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.agent_id == slug))
        agent = result.scalar_one_or_none()
        if agent is None:
            return None
        if agent.company_id != company_id:
            raise ValueError(
                f"default CEO slug {slug!r} is already held by another company; "
                "refusing to adopt a foreign agent as CEO"
            )
        return agent
