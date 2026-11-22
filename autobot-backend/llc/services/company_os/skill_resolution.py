# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which skills a role holds, and through what (#18390). Pure, no I/O.

Owner decision 2026-10-12: a skill delivered through a held meta skill counts as
held, transitively, and the answer must say which meta skill it came through.

What a meta skill *contains* is the union of ``required_skills`` of the processes
in its graph, plus whatever the meta skills it calls contain. A skill can be held
several ways at once (directly and through two meta skills), so each skill carries
every source rather than the first one found.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set


@dataclass(frozen=True)
class MetaSkillDef:
    """A meta skill as the resolver sees it."""

    workflow_id: str
    name: str
    #: Skills required by the process nodes of its own graph.
    skills: tuple = ()
    #: ``workflow_id`` of each meta skill its graph calls.
    calls: tuple = ()


@dataclass(frozen=True)
class SkillSource:
    """Where a held skill came from: ``direct`` or through a meta skill.

    ``via`` is the call path, outermost meta skill first -- the held one -- so a
    skill reached through a nested meta skill shows the whole chain.
    """

    kind: str
    meta_skill_id: str | None = None
    meta_skill_name: str | None = None
    via: tuple = ()


@dataclass
class HeldSkill:
    skill: str
    sources: List[SkillSource] = field(default_factory=list)


def _walk(held: MetaSkillDef, metas: Dict[str, MetaSkillDef]) -> Iterable[tuple]:
    """Yield ``(skill, path)`` for every skill reachable from *held*, cycle-safe."""
    stack = [(held, (held.workflow_id,))]
    seen: Set[str] = set()
    while stack:
        meta, path = stack.pop()
        if meta.workflow_id in seen:
            continue
        seen.add(meta.workflow_id)
        for skill in meta.skills:
            yield skill, path
        for called_id in meta.calls:
            called = metas.get(called_id)
            if called is not None:
                stack.append((called, path + (called_id,)))


def resolve_held_skills(
    direct: Iterable[str], held_meta_ids: Iterable[str], metas: Dict[str, MetaSkillDef]
) -> List[HeldSkill]:
    """Every skill the role holds, with every source, sorted by skill name."""
    held: Dict[str, HeldSkill] = {}
    for skill in direct:
        held.setdefault(skill, HeldSkill(skill)).sources.append(SkillSource(kind="direct"))
    for meta_id in held_meta_ids:
        meta = metas.get(meta_id)
        if meta is None:
            continue
        for skill, path in _walk(meta, metas):
            src = SkillSource("meta_skill", meta.workflow_id, meta.name, tuple(metas[p].name for p in path))
            entry = held.setdefault(skill, HeldSkill(skill))
            if src not in entry.sources:
                entry.sources.append(src)
    return sorted(held.values(), key=lambda h: h.skill)
