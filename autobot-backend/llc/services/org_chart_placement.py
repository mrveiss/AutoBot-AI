# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Placing org-chart nodes and assembling them into a tree (#15763).

Extracted from ``companies.py``, which is grandfathered at 1802 lines and may
not grow: the exemption freezes the size it was granted for, it does not
license more (#14236). The cut is a seam rather than an arithmetic trim —
these two steps answer "who is above whom, and what shape does that make",
while the route keeps gathering rows and returning the result.

``OrgChartNode`` stays defined in ``companies.py`` and is imported here only
under ``TYPE_CHECKING``. That works because neither function **constructs** a
node — one sets ``parent_id`` and the other arranges existing nodes — so no
runtime import is needed and there is no cycle with the module that builds
them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.enums import RoleHolderType
from llc.models.reporting_line import LLCReportingLine

if TYPE_CHECKING:  # pragma: no cover - typing only
    from llc.api.companies import OrgChartNode


async def apply_reporting_lines(session: AsyncSession, company_id: uuid.UUID, flat: Dict[str, OrgChartNode]) -> None:
    """Set ``parent_id`` from ``llc_reporting_lines`` for people and agents alike.

    **Two id spaces meet here and picking the wrong one is silent.**

    * ``OrgChartNode.id`` is the *display* id — an agent slug, or ``user:{uuid}``
      for a person. It is what the legacy ``agent_org_nodes.reports_to`` column
      references, and it is what ``flat`` is keyed by.
    * ``OrgChartNode.node_id`` is the *assignment* keyspace (#10032):
      ``str(AgentOrgNode.id)`` for an agent, the user id for a person. It is
      what ``assignee_agent_id``, ``holder_agent_id`` and
      ``llc_reporting_lines`` all reference.

    A parent map built from ``id`` looks right and places nobody: the reporting
    rows simply fail to match, every node keeps the parent it already had, and
    the chart renders perfectly with the wrong shape. There is no error to see.
    So the lookup is keyed by ``(holder type, node_id)`` and the result is
    translated back to a display id before it is stored on the node.

    An explicit line wins over whatever ``reports_to`` produced, because it is
    the newer store and the one the migration carried those edges into. Nodes
    with no line keep what they had, which is how the legacy column stays
    readable until it is retired.
    """

    by_holder: Dict[tuple[str, str], OrgChartNode] = {}
    for node in flat.values():
        holder_type = RoleHolderType.USER.value if node.is_human else RoleHolderType.AGENT.value
        if node.node_id:
            by_holder[(holder_type, str(node.node_id))] = node

    rows = (
        (await session.execute(select(LLCReportingLine).where(LLCReportingLine.company_id == company_id)))
        .scalars()
        .all()
    )

    for row in rows:
        subject_id, manager_id = row.subject_id, row.manager_id
        if subject_id is None or manager_id is None:
            # A row whose discriminator disagrees with its populated columns is
            # corrupt; skipping beats guessing a column, which is the same
            # contract as LLCReportingLine.subject_id itself.
            continue
        subject = by_holder.get((row.subject_type, str(subject_id)))
        manager = by_holder.get((row.manager_type, str(manager_id)))
        if subject is None or manager is None:
            # An edge naming somebody outside this chart — a departed member,
            # or an agent in another company. Leaving the subject where it is
            # beats attaching it to nothing.
            continue
        subject.parent_id = manager.id


def assemble_forest(flat: Dict[str, "OrgChartNode"]) -> List["OrgChartNode"]:
    """Arrange placed nodes into a forest, attaching each to its parent.

    A node joins its parent only when its chain is acyclic. Cycle members, and
    nodes whose parent is absent or is themselves, become roots with no parent
    edge — so the output is always a true forest: every node appears exactly
    once and nothing nests infinitely.

    The cycle guard is not defensive tidiness. ``parent_id`` comes from stored
    reporting lines and from the legacy ``reports_to`` column, neither of which
    prevents a row pointing back into its own chain, so a walk without ``seen``
    does not terminate on real data.
    """

    def _chain_resolves_to_root(node_id: str) -> bool:
        seen: set[str] = set()
        cur: Optional["OrgChartNode"] = flat.get(node_id)
        while cur is not None and cur.parent_id:
            if cur.id in seen:
                return False  # cycle
            seen.add(cur.id)
            parent = flat.get(cur.parent_id)
            if parent is None or parent.id == cur.id:
                return True  # parent absent/self → effectively rooted
            cur = parent
        return True

    roots: List["OrgChartNode"] = []
    for node in flat.values():
        parent = flat.get(node.parent_id) if node.parent_id else None
        if parent is not None and parent.id != node.id and _chain_resolves_to_root(node.id):
            parent.children.append(node)
        else:
            roots.append(node)
    return roots
