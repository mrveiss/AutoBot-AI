# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Generator (Phase 5)

Uses the LLM to generate SKILL.md + skill.py for a detected capability gap.
Structured output ensures valid manifests every time.
"""

import re
from typing import Any, Dict

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an expert at building AutoBot skill packages.
A skill has two parts:
1. SKILL.md — YAML frontmatter with: name (kebab-case), version, description,
   tools (list of function names), triggers, tags, category.
   Followed by Markdown: when to use, workflow steps, limitations.
2. skill.py — A Python MCP server using the `mcp` library.
   Each tool listed in the manifest must be implemented as @app.tool().

Rules:
- name must be kebab-case
- skill.py must be runnable standalone: `python skill.py`
- Tools must have type-annotated parameters
- Keep skill.py under 100 lines
- Use only stdlib + mcp library (no other deps)
"""

_GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_md": {"type": "string"},
        "skill_py": {"type": "string"},
    },
    "required": ["skill_md", "skill_py"],
}


class SkillGenerator:
    """Generates SKILL.md + skill.py for a capability gap using the LLM."""

    def __init__(self, llm: Any = None) -> None:
        """Initialize with an optional LLM interface (defaults to AutoBot LLM)."""
        self._llm = llm or self._get_default_llm()

    async def generate(self, gap_description: str) -> Dict[str, Any]:
        """Generate a skill package for the described capability gap.

        Returns dict with keys: name, skill_md, skill_py, manifest, gap_description.
        """
        import json

        prompt = (
            f"Generate a skill package for this capability: {gap_description}\n\n"
            "Return ONLY a JSON object with keys 'skill_md' and 'skill_py'. No prose."
        )
        response = await self._llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\nResponse: {response.content[:500]}") from e
        if not isinstance(result, dict) or "skill_md" not in result or "skill_py" not in result:
            raise ValueError(f"LLM response missing required keys: {list(result.keys())}")
        manifest = _parse_manifest(result["skill_md"])
        return {
            "name": manifest.get("name", "generated-skill"),
            "skill_md": result["skill_md"],
            "skill_py": result["skill_py"],
            "manifest": manifest,
            "gap_description": gap_description,
        }

    @staticmethod
    def _get_default_llm() -> Any:
        """Get the AutoBot LLM service singleton."""
        from services.llm_service import get_llm_service

        return get_llm_service()


def _parse_manifest(skill_md: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from SKILL.md content into manifest dict."""
    match = re.match(r"^---\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
