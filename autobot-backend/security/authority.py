# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a principal may do, and how a chain of principals combines (#16950).

#16946, owner decision 1: effective permission at any hop is the meet of every hop
from the originator through it. Relaying can never widen it.

Four surfaces carry authority today, in four vocabularies. Ruling F1 on #16950:
keep each in its own vocabulary, side by side, with its own meet. Translating them
into one namespace would need role→tool and capability→tool tables that nobody has
decided, and a second copy of four policies to drift.

| Surface | Kind | Meet | Top (no constraint) |
|---|---|---|---|
| approval gates (``requires_approval_before``) | restriction | union | empty set |
| forbidden tools (a profile's ``forbidden_work``) | restriction | union | empty set |
| RBAC permissions | grant | intersection | ``None`` |
| A2A capabilities | grant | intersection | ``None`` |

"More restrictive" is the meet in every row. It points one way for restrictions and
the other for grants.

**A surface a hop does not use is top for that hop, never bottom.** A hop that has
nothing to do with A2A has no capabilities to intersect, and must not zero out a
chain it never touched. That is why grants default to ``None`` and not to an empty
set: an empty set is a real grant of nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from typing import FrozenSet


def _meet_grant(a: FrozenSet[str] | None, b: FrozenSet[str] | None) -> FrozenSet[str] | None:
    """Intersect two grants, where None is the unconstrained top."""
    if a is None:
        return b
    if b is None:
        return a
    return a & b


@dataclass(frozen=True)
class Authority:
    """One principal's authority across the four surfaces. Defaults are the top: no constraint at all."""

    approval_gates: FrozenSet[str] = frozenset()
    forbidden_tools: FrozenSet[str] = frozenset()
    permissions: FrozenSet[str] | None = None
    capabilities: FrozenSet[str] | None = None

    def meet(self, other: Authority) -> Authority:
        """The authority both hold: every restriction of either, only the grants of both."""
        return Authority(
            approval_gates=self.approval_gates | other.approval_gates,
            forbidden_tools=self.forbidden_tools | other.forbidden_tools,
            permissions=_meet_grant(self.permissions, other.permissions),
            capabilities=_meet_grant(self.capabilities, other.capabilities),
        )

    def permits(self, permission: str) -> bool:
        """Whether the RBAC grant covers *permission*. Top covers everything, so the role alone decides."""
        return self.permissions is None or permission in self.permissions

    def has_capability(self, capability: str) -> bool:
        """Whether the A2A grant covers *capability*. Top, an internal principal, covers everything."""
        return self.capabilities is None or capability in self.capabilities


#: The unconstrained authority: the identity element of ``meet``.
TOP = Authority()


def meet_all(*hops: Authority) -> Authority:
    """The meet of every hop in a chain; ``TOP`` for an empty one."""
    return reduce(Authority.meet, hops, TOP)
