# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Totalling what the operation costs to run (#14599).

A sum over the steps the canvas already shows — not a separate analytics
product. Every figure here comes from ``derive_step_cost`` (#14598, #14607); no
arithmetic is repeated, so a change to how a step is costed cannot leave this
disagreeing with the step's own panel.

**Coverage travels with every total.** A step nobody measured, or one whose
role has no rate, is excluded from the sum and counted in ``not_costable``.
Reporting the total alone would present a partial figure as a complete one,
and the reader has no way to tell the difference by looking at it. This is the
same failure that produced #14064, #13617 and #14556 in this area, in its
arithmetic form: silence reading as zero.

There is deliberately no "estimated total" that fills gaps with an average.
A guessed number that looks like a measured one is worse than an obviously
partial answer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Role

from ..models.role_rate import LLCRoleRate
from ..models.role_tool import LLCRoleTool
from ..models.role_workflow import LLCRoleWorkflow
from .step_cost import derive_step_cost


@dataclass
class RollupBucket:
    """One grouping's total, and how much of it is actually known."""

    key: str
    label: str
    per_month: Decimal = Decimal(0)
    #: Steps that contributed a figure.
    costed: int = 0
    #: Steps counted but not costable — never summed as zero.
    not_costable: int = 0
    currencies: set = field(default_factory=set)

    @property
    def total_steps(self) -> int:
        return self.costed + self.not_costable

    @property
    def is_complete(self) -> bool:
        """Whether every step in this bucket contributed."""
        return self.not_costable == 0 and self.costed > 0


def _add(bucket: RollupBucket, cost, currency: Optional[str]) -> None:  # noqa: ANN001
    """Fold one step into a bucket, counting it either way."""
    if cost.per_month is None:
        bucket.not_costable += 1
        return
    bucket.costed += 1
    bucket.per_month += cost.per_month
    if currency:
        bucket.currencies.add(currency)


class StepRollupService:
    """Totals over the company's process steps, by role and by tool."""

    async def rollup(self, session: AsyncSession, company_id: uuid.UUID) -> Dict[str, List[RollupBucket]]:
        """Cost per month grouped by role and by tool.

        Both groupings are derived from the same per-step figures, so they can
        differ in shape but never in the underlying numbers. A step whose role
        carries several tools contributes its full cost to each of those tools:
        that is what "what does this tool cost us to operate" means, and it is
        why the tool totals are not expected to sum to the role total. Stated
        here because a reader comparing the two columns will otherwise assume
        one of them is wrong.
        """
        attachments = (
            await session.execute(
                select(
                    LLCRoleWorkflow.role_id,
                    LLCRoleWorkflow.workflow_id,
                    LLCRoleWorkflow.estimated_minutes,
                    LLCRoleWorkflow.runs_per_month,
                    Role.name,
                )
                .join(Role, Role.id == LLCRoleWorkflow.role_id)
                .where(
                    # Pinned on both sides, as the process-nodes read is: losing
                    # either predicate cannot widen the result.
                    Role.org_id == company_id,
                    LLCRoleWorkflow.company_id == company_id,
                )
                .order_by(Role.name, LLCRoleWorkflow.workflow_id)
            )
        ).all()

        rates = {
            row.role_id: row
            for row in (
                await session.execute(select(LLCRoleRate).where(LLCRoleRate.company_id == company_id))
            ).scalars()
        }

        tool_rows = (
            await session.execute(
                select(LLCRoleTool.role_id, LLCRoleTool.tool_name).where(LLCRoleTool.company_id == company_id)
            )
        ).all()
        tools_by_role: Dict[uuid.UUID, List[str]] = {}
        for role_id, tool_name in tool_rows:
            tools_by_role.setdefault(role_id, []).append(tool_name)

        by_role: Dict[uuid.UUID, RollupBucket] = {}
        by_tool: Dict[str, RollupBucket] = {}

        for role_id, _workflow_id, minutes, runs, role_name in attachments:
            rate = rates.get(role_id)
            cost = derive_step_cost(
                estimated_minutes=minutes,
                runs_per_month=runs,
                hourly_rate=rate.hourly_rate if rate else None,
                currency=rate.currency if rate else None,
            )
            currency = rate.currency if rate else None

            role_bucket = by_role.setdefault(role_id, RollupBucket(key=str(role_id), label=role_name))
            _add(role_bucket, cost, currency)

            for tool_name in tools_by_role.get(role_id, []):
                tool_bucket = by_tool.setdefault(tool_name, RollupBucket(key=tool_name, label=tool_name))
                _add(tool_bucket, cost, currency)

        return {
            "by_role": sorted(by_role.values(), key=lambda b: b.label),
            "by_tool": sorted(by_tool.values(), key=lambda b: b.label),
        }
