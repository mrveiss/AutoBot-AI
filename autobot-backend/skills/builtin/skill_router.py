# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Router Meta-Skill

Two-phase skill discovery: keyword scoring (Phase 1) + LLM re-ranking (Phase 2).
Auto-enables the best matching skill for a given task description.
"""

import json
import re
from typing import Any, Dict, List, Set, Tuple

from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest
from skills.registry import get_skill_registry

try:
    from llm_interface_pkg import LLMInterface
except ImportError:
    LLMInterface = None  # type: ignore[assignment,misc]


def _tokenize(text: str) -> Set[str]:
    """Lowercase and split text on non-word characters."""
    return {t for t in re.split(r"[\W_]+", text.lower()) if t}


# Scoring weights — name and tags are preferred over tools and description
# because manifests are canonically authored; adjust when recall is poor.
_W_NAME = 3.0
_W_TAGS = 3.0
_W_TOOLS = 2.0
_W_DESC = 1.0


def _score_from_tokens(
    task_tokens: Set[str],
    name: str,
    tags: List[str],
    tools: List[str],
    description: str,
) -> float:
    """Score a skill against task tokens using weighted field overlap."""
    name_tokens = _tokenize(name)
    tag_tokens: Set[str] = set()
    for tag in tags:
        tag_tokens.update(_tokenize(tag))
    tool_tokens: Set[str] = set()
    for tool in tools:
        tool_tokens.update(_tokenize(tool))
    desc_tokens = _tokenize(description)
    return (
        len(task_tokens & name_tokens) * _W_NAME
        + len(task_tokens & tag_tokens) * _W_TAGS
        + len(task_tokens & tool_tokens) * _W_TOOLS
        + len(task_tokens & desc_tokens) * _W_DESC
    )


def _score_skill(task_tokens: Set[str], manifest: SkillManifest) -> float:
    """Score a skill manifest against task tokens.

    Weights: name (3x), tags (3x), tools (2x), description (1x).
    """
    return _score_from_tokens(
        task_tokens,
        manifest.name,
        manifest.tags,
        manifest.tools,
        manifest.description,
    )


class SkillRouterSkill(BaseSkill):
    """Meta-skill: finds and enables the best skill for a given task."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        return SkillManifest(
            name="skill-router",
            version="1.0.0",
            description="Meta-skill that routes tasks to the most appropriate skill",
            author="mrveiss",
            category="meta",
            tools=["find_skill"],
            tags=["meta", "routing", "discovery", "orchestration"],
            config={
                "top_k": SkillConfigField(
                    type="int",
                    default=5,
                    description="Max candidates sent to LLM for re-ranking",
                ),
                "auto_enable": SkillConfigField(
                    type="bool",
                    default=True,
                    description="Automatically enable the winning skill",
                ),
            },
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
        """Execute a skill router action."""
        if action == "find_skill":
            return await self._find_skill(params)
        return {"success": False, "error": f"Unknown action: {action}"}

    async def _find_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Find and enable the best skill for the given task."""
        task: str = params.get("task", "").strip()
        dry_run: bool = params.get("dry_run", False)

        if not task:
            return {"success": False, "error": "task parameter is required"}

        registry = get_skill_registry()
        candidates = self._build_candidates(task, registry)

        if not candidates:
            return {"success": False, "error": "no skills registered"}

        winner, reason, method = await self._pick_winner(task, candidates)
        return await self._enable_and_respond(
            winner, reason, method, candidates, registry, dry_run
        )

    def _build_candidates(self, task: str, registry: Any) -> List[Dict[str, Any]]:
        """Score all registered skills and return top-K candidates."""
        top_k: int = self._config.get("top_k", 5)
        task_tokens = _tokenize(task)
        scored = [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "tags": s.get("tags", []),
                "tools": s.get("tools", []),
                "score": _score_from_tokens(
                    task_tokens,
                    s["name"],
                    s.get("tags", []),
                    s.get("tools", []),
                    s.get("description", ""),
                ),
            }
            for s in registry.list_skills()
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = [c for c in scored[:top_k] if c["score"] > 0]
        return candidates or scored[:1]

    async def _pick_winner(
        self, task: str, candidates: List[Dict[str, Any]]
    ) -> Tuple[str, str, str]:
        """Run LLM re-ranking; fall back to keyword winner on failure."""
        winner = candidates[0]["name"]
        reason = "top keyword match"
        method = "keyword_fallback"
        try:
            llm_winner, llm_reason = await self._llm_rerank(task, candidates)
            if llm_winner in {c["name"] for c in candidates}:
                winner, reason, method = llm_winner, llm_reason, "llm"
            else:
                self.logger.warning(
                    "LLM returned unknown skill '%s', using keyword winner '%s'",
                    llm_winner,
                    winner,
                )
        except Exception as exc:
            self.logger.warning(
                "LLM re-ranking failed, using keyword fallback: %s", exc
            )
        return winner, reason, method

    async def _enable_and_respond(
        self,
        winner: str,
        reason: str,
        method: str,
        candidates: List[Dict[str, Any]],
        registry: Any,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Enable the winning skill (unless dry_run) and return result."""
        auto_enable: bool = self._config.get("auto_enable", True)
        if auto_enable and not dry_run:
            enable_result = registry.enable_skill(winner)
            if not enable_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to enable '{winner}': {enable_result.get('error')}",
                }
        return {
            "success": True,
            "enabled_skill": winner,
            "reason": reason,
            "method": method,
            "candidates": [
                {"name": c["name"], "score": c["score"]} for c in candidates
            ],
            "dry_run": dry_run,
        }
