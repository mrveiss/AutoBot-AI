# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Researcher Meta-Skill (Issue #1182)

Multi-source research phase: queries the LLM from three independent angles
(technical, ecosystem, user experience) then synthesises the findings into
structured context that the autonomous-skill-development pipeline uses to
build more accurate and complete skills.
"""

import json
import logging
import re
from typing import Any, Dict, List

from skills.base_skill import BaseSkill, SkillManifest

logger = logging.getLogger(__name__)

try:
    from llm_interface_pkg import LLMInterface
except ImportError:
    LLMInterface = None  # type: ignore[assignment,misc]


# Three angles — each represents an independent "source" of knowledge.
_RESEARCH_QUERIES = [
    (
        "technical",
        "Explain how {c} works technically. Cover the key architecture, "
        "main components, and data flow. Be concise but thorough.",
    ),
    (
        "ecosystem",
        "List the main libraries and tools available for implementing {c}. "
        "For each, briefly state: maturity, pros, cons.",
    ),
    (
        "user_experience",
        "What are the most common problems, gotchas, and user complaints "
        "when implementing {c}? Include practical pitfalls and lessons "
        "learned from practitioners.",
    ),
]

_SYNTHESIS_TEMPLATE = (
    'Synthesise the following research about "{capability}":\n\n'
    "{sources}\n\n"
    "Respond with JSON only — no markdown fences:\n"
    '{{"summary": "2-3 sentence overview", '
    '"key_libraries": ["lib1", "lib2"], '
    '"best_practices": ["practice1"], '
    '"common_pitfalls": ["pitfall1"], '
    '"implementation_hints": "specific guidance for coding this capability"}}'
)


def _build_queries(capability: str) -> List[tuple]:
    """Return list of (label, prompt) tuples for the given capability."""
    return [(label, prompt.format(c=capability)) for label, prompt in _RESEARCH_QUERIES]


def _build_synthesis_prompt(capability: str, sources: List[Dict[str, str]]) -> str:
    """Format the synthesis prompt from gathered sources."""
    formatted = "\n\n".join(f"[{s['angle'].upper()}]\n{s['content']}" for s in sources)
    return _SYNTHESIS_TEMPLATE.format(capability=capability, sources=formatted)


def _parse_synthesis(content: str) -> Dict[str, Any]:
    """Extract and parse the JSON block from LLM synthesis response."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return _empty_findings()
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return _empty_findings()


def _empty_findings() -> Dict[str, Any]:
    """Return a blank research result used as fallback."""
    return {
        "summary": "",
        "key_libraries": [],
        "best_practices": [],
        "common_pitfalls": [],
        "implementation_hints": "",
    }


class SkillResearcherSkill(BaseSkill):
    """Meta-skill: multi-source research about a capability before skill generation."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        return SkillManifest(
            name="skill-researcher",
            version="1.0.0",
            description=(
                "Researches a capability from multiple independent angles "
                "(technical, ecosystem, user experience) and synthesises "
                "findings to inform autonomous skill generation."
            ),
            author="mrveiss",
            category="meta",
            tools=["research_capability"],
            tags=["meta", "research", "knowledge-gathering", "skill-generation"],
        )

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch to the research_capability tool."""
        if action == "research_capability":
            return await self._research(params)
        return {"success": False, "error": f"Unknown action: {action}"}

    async def _research(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate multi-source research and synthesis."""
        capability = params.get("capability", "").strip()
        if not capability:
            return {"success": False, "error": "capability is required"}
        if LLMInterface is None:
            return {"success": False, "error": "LLMInterface not available"}

        sources = await self._query_sources(capability)
        findings = await self._synthesize(capability, sources)
        return {
            "success": True,
            "capability": capability,
            "sources_consulted": len(sources),
            **findings,
        }

    async def _query_sources(self, capability: str) -> List[Dict[str, str]]:
        """Run each research query; skip silently on LLM failure."""
        llm = LLMInterface()
        sources = []
        for label, prompt in _build_queries(capability):
            try:
                response = await llm.chat_completion(
                    [{"role": "user", "content": prompt}], llm_type="task"
                )
                sources.append({"angle": label, "content": response.content.strip()})
            except Exception as exc:
                self.logger.warning("Research query '%s' failed: %s", label, exc)
        return sources

    async def _synthesize(
        self, capability: str, sources: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Synthesise gathered sources into structured findings."""
        if not sources:
            return _empty_findings()
        prompt = _build_synthesis_prompt(capability, sources)
        llm = LLMInterface()
        try:
            response = await llm.chat_completion(
                [{"role": "user", "content": prompt}], llm_type="task"
            )
            return _parse_synthesis(response.content)
        except Exception as exc:
            self.logger.warning("Synthesis failed: %s", exc)
            return _empty_findings()
