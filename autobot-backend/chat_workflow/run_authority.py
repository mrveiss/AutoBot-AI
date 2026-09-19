# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A run's authority, and what a run it starts inherits from it (#16950).

Delegation built the child from the child's own profile alone. The parent's approval
gates and work item were dropped, so a parent held from ``write_file`` could delegate
the write and the child ran it unapproved. The child's authority is now the meet of
the parent's and its own. It only ever narrows, whichever engine runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Iterable

from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS
from security.authority import TOP, Authority


def authority_of(ctx: Any) -> Authority:
    """Everything that bounds *ctx*'s run: its own profile and gates, met with whatever it inherited."""
    from orchestration.agent_registry import resolve_forbidden_tools

    agent_context = getattr(ctx, "agent_context", None)
    agent_id = agent_context.agent_id if agent_context is not None else None
    own = Authority(
        approval_gates=frozenset(getattr(ctx, "requires_approval_before", None) or ()),
        forbidden_tools=resolve_forbidden_tools(agent_id),
    )
    inherited = getattr(ctx, "authority", None)
    return own.meet(inherited) if inherited is not None else own


@dataclass(frozen=True)
class Inheritance:
    """What a delegated run carries from its parent: the parent's full authority and its work item."""

    authority: Authority = TOP
    work_item_id: str | None = None

    @classmethod
    def of(cls, parent_ctx: Any) -> Inheritance:
        """The inheritance a run started from *parent_ctx* receives. No parent means nothing is inherited."""
        if parent_ctx is None:
            return cls()
        return cls(authority=authority_of(parent_ctx), work_item_id=getattr(parent_ctx, "work_item_id", None))


#: Nothing inherited: a delegation started with no parent run.
NO_INHERITANCE = Inheritance()


def gated_tools(categories: Iterable[str]) -> FrozenSet[str]:
    """Every tool token an approval category holds, for an engine that cannot ask for approval.

    An out-of-process engine runs its own tool loop, so a gated action can only be
    refused there, never held. Refusal is the fail-closed reading of "needs approval".
    """
    return frozenset(tool for category in categories for tool in APPROVAL_CATEGORY_TOOLS.get(category, ()))
