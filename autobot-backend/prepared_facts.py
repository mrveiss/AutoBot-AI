# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Runtime-facts pattern for AutoBot hot paths (GH#7370).

Each dataclass represents a set of facts computed once at startup and
consumed directly in hot paths, eliminating per-request rediscovery.

Facts:
  SkillTokenFact     — pre-tokenized fields for a single registered skill
  SkillRoutingIndex  — compiled index of all skill facts; rebuilt on registry change
  ProviderRuntimeFact — per-provider capabilities precomputed at registration
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Internal tokenizer — same regex as skill_router._tokenize but returns a
# frozenset so facts can be frozen.  Kept here to avoid a circular import
# between prepared_facts and skills.builtin.skill_router.
# ---------------------------------------------------------------------------


def _tok(text: str) -> FrozenSet[str]:
    return frozenset(t for t in re.split(r"[\W_]+", text.lower()) if t)


# ---------------------------------------------------------------------------
# Skill-routing facts
# ---------------------------------------------------------------------------

_W_NAME = 3.0
_W_TAGS = 3.0
_W_TOOLS = 2.0
_W_DESC = 1.0


@dataclass(frozen=True)
class SkillTokenFact:
    """Pre-tokenized fields for a single registered skill.

    Built once at registration time; all token sets are frozen so the
    dataclass itself is immutable and safe to share across workers.
    """

    name: str
    name_tokens: FrozenSet[str]
    tag_tokens: FrozenSet[str]
    tool_tokens: FrozenSet[str]
    desc_tokens: FrozenSet[str]

    @classmethod
    def build_at_startup(
        cls,
        name: str,
        tags: Sequence[str],
        tools: Sequence[str],
        description: str,
    ) -> "SkillTokenFact":
        """Build a fact from skill manifest fields."""
        tag_t: set = set()
        for tag in tags:
            tag_t.update(_tok(tag))
        tool_t: set = set()
        for tool in tools:
            tool_t.update(_tok(tool))
        return cls(
            name=name,
            name_tokens=_tok(name),
            tag_tokens=frozenset(tag_t),
            tool_tokens=frozenset(tool_t),
            desc_tokens=_tok(description),
        )

    def score(self, task_tokens: FrozenSet[str]) -> float:
        """Score this skill against a pre-tokenized task description."""
        return (
            len(task_tokens & self.name_tokens) * _W_NAME
            + len(task_tokens & self.tag_tokens) * _W_TAGS
            + len(task_tokens & self.tool_tokens) * _W_TOOLS
            + len(task_tokens & self.desc_tokens) * _W_DESC
        )


class SkillRoutingIndex:
    """Compiled index of pre-tokenized skill facts plus a skills snapshot.

    Rebuilt once when the registry changes (register / unregister).
    Per-message lookup is O(n_skills) with no regex work; only the task
    text is tokenized at request time.
    """

    def __init__(
        self,
        facts: List[SkillTokenFact],
        skill_map: Dict[str, Dict[str, Any]],
    ) -> None:
        self._facts = facts
        self._skill_map = skill_map

    @classmethod
    def build_at_startup(cls, skills: Sequence[Dict[str, Any]]) -> "SkillRoutingIndex":
        """Build the index from the list returned by registry.list_skills()."""
        facts = [
            SkillTokenFact.build_at_startup(
                name=s["name"],
                tags=s.get("tags", []),
                tools=s.get("tools", []),
                description=s.get("description", ""),
            )
            for s in skills
        ]
        skill_map = {s["name"]: s for s in skills}
        return cls(facts, skill_map)

    def score_candidates(
        self,
        task_text: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return top-k skill dicts (with 'score' field) sorted by score desc.

        task_text is tokenized once here; all per-skill work uses pre-built
        frozen token sets — no regex is executed for individual skills.
        """
        task_tokens = _tok(task_text)
        scored: List[Tuple[SkillTokenFact, float]] = [(f, f.score(task_tokens)) for f in self._facts]
        scored.sort(key=lambda x: x[1], reverse=True)
        result = []
        for fact, score in scored[:top_k]:
            if score <= 0:
                break
            skill_data = self._skill_map.get(fact.name, {})
            result.append(
                {
                    "name": fact.name,
                    "description": skill_data.get("description", ""),
                    "tags": skill_data.get("tags", []),
                    "tools": skill_data.get("tools", []),
                    "score": score,
                }
            )
        return result

    def __len__(self) -> int:
        return len(self._facts)


# ---------------------------------------------------------------------------
# Provider runtime facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderRuntimeFact:
    """Precomputed per-provider capabilities, built once at registration.

    Avoids repeated introspection of provider objects in the hot path.
    auth_configured signals whether credentials were present at startup;
    is_local marks providers that run in-process with no external API cost.
    """

    name: str
    auth_configured: bool
    is_local: bool

    @classmethod
    def build_at_startup(cls, name: str, provider: Any) -> "ProviderRuntimeFact":
        """Build a fact for a provider instance."""
        settings: Dict[str, Any] = getattr(provider, "settings", {}) or {}
        auth_configured = bool(settings.get("api_key") or settings.get("api_token") or settings.get("base_url"))
        is_local = name in {"ollama", "vllm"}
        return cls(name=name, auth_configured=auth_configured, is_local=is_local)


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
    "SkillTokenFact",
    "SkillRoutingIndex",
    "ProviderRuntimeFact",
]
