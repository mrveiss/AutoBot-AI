# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Router Meta-Skill

Two-phase skill discovery: keyword scoring (Phase 1) + LLM re-ranking (Phase 2).
Auto-enables the best matching skill for a given task description.
"""

import json
import logging
import re
from typing import Any, Dict, List, Set, Tuple

from skills.base_skill import BaseSkill, SkillManifest

try:
    from llm_interface_pkg import LLMInterface
except ImportError:
    LLMInterface = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> Set[str]:
    """Lowercase and split text on non-word characters."""
    return {t for t in re.split(r"[\W_]+", text.lower()) if t}


# Scoring weights — name and tags are preferred over tools and description
# because manifests are canonically authored; adjust when recall is poor.
_W_NAME = 3.0
_W_TAGS = 3.0
_W_TOOLS = 2.0
_W_DESC = 1.0


def _score_skill(task_tokens: Set[str], manifest: SkillManifest) -> float:
    """Score a skill manifest against task tokens.

    Weights: name (3x), tags (3x), tools (2x), description (1x).
    """
    name_tokens = _tokenize(manifest.name)
    tag_tokens: Set[str] = set()
    for tag in manifest.tags:
        tag_tokens.update(_tokenize(tag))
    tool_tokens: Set[str] = set()
    for tool in manifest.tools:
        tool_tokens.update(_tokenize(tool))
    desc_tokens = _tokenize(manifest.description)

    return (
        len(task_tokens & name_tokens) * _W_NAME
        + len(task_tokens & tag_tokens) * _W_TAGS
        + len(task_tokens & tool_tokens) * _W_TOOLS
        + len(task_tokens & desc_tokens) * _W_DESC
    )


class SkillRouterSkill(BaseSkill):
    """Stub — full implementation in later tasks."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        return SkillManifest(
            name="skill-router",
            version="1.0.0",
            description="Meta-skill that routes tasks to the most appropriate skill",
            author="mrveiss",
            category="meta",
            tags=["meta", "routing", "discovery", "orchestration"],
        )

    async def _llm_rerank(
        self, task: str, candidates: List[Dict[str, Any]]
    ) -> Tuple[str, str]:
        """Re-rank candidates via LLM. Returns (skill_name, reason).

        Raises ValueError if LLM unavailable or response unparseable.
        """
        if LLMInterface is None:
            raise ValueError("LLMInterface not available")

        summaries = [
            f"- {c['name']}: {c['description']} "
            f"(tags: {', '.join(c['tags'])}, tools: {', '.join(c['tools'])})"
            for c in candidates
        ]
        prompt = (
            f'Given this task: "{task}"\n\n'
            f"Choose the most appropriate skill from:\n"
            + "\n".join(summaries)
            + '\n\nRespond with JSON only: {"skill": "<name>", "reason": "<brief reason>"}'
        )
        messages = [{"role": "user", "content": prompt}]
        llm = LLMInterface()
        response = await llm.chat_completion(messages, llm_type="task")

        content = response.content.strip()
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in LLM response: {content[:100]}")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed JSON in LLM response: {match.group()[:100]}"
            ) from exc
        return data["skill"], data.get("reason", "")

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}
