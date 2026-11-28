# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Specialized Agent Service (#1794)

Parses the host's Claude Code user-level agent definitions (``*.md``) to
surface them in the web UI.  The directory comes from SSOT config
(``claude_agents_dir()``), never from the source tree.  Each
.md file uses YAML frontmatter (name, description, model, color, tools, and an
optional ``tier``) followed by a markdown system prompt.  Agents are arbitrary
user content: a ``tier`` that names an AgentTier wins, any other agent gets
the classifier's default tier.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from agent_tier_classifier import AgentTier, get_agent_tier
from autobot_shared.claude_config import claude_agents_dir
from autobot_shared.frontmatter import split_frontmatter, strip_frontmatter
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults

logger = get_logger(__name__)

# Agent categories inferred from name + description keywords.
_CATEGORY_RULES: List[tuple] = [
    (
        "analysis",
        [
            "skeptic",
            "architect",
            "performance",
            "security",
            "auditor",
            "review",
        ],
    ),
    (
        "implementation",
        [
            "engineer",
            "developer",
            "backend",
            "frontend",
            "database",
            "devops",
            "testing",
        ],
    ),
    (
        "planning",
        ["project", "manager", "planner", "prd", "task"],
    ),
    (
        "specialized",
        [
            "content",
            "writer",
            "designer",
            "compacter",
            "memory",
            "refactor",
        ],
    ),
]


def _categorize_agent(name: str, description: str) -> str:
    """Categorize agent by name/description keywords (#1794)."""
    combined = f"{name} {description}".lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            # analysis takes priority over implementation for reviewers
            if category == "implementation" and ("review" in combined or "analysis" in combined):
                return "analysis"
            return category
    return "general"


def _yaml_scalar(value: str) -> str | None:
    """A frontmatter value decoded as a YAML scalar (quotes and trailing comments dropped)."""
    try:
        decoded = yaml.safe_load(value)
    except yaml.YAMLError:
        return value
    return None if decoded is None else str(decoded)


def _parse_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from an agent .md file (#1794).

    Supports: name, description, model, color, tier, tools (comma-separated).
    """
    result: Dict[str, Any] = {
        "name": "",
        "description": "",
        "tools": [],
        "color": "gray",
        "model": None,
        "tier": None,
    }

    raw, _ = split_frontmatter(content)
    if raw is None:
        return result

    for line in raw.split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key == "name":
            result["name"] = value
        elif key == "description":
            result["description"] = value
        elif key == "tools":
            result["tools"] = [t.strip() for t in value.split(",") if t.strip()]
        elif key == "color":
            result["color"] = value
        elif key == "model":
            result["model"] = value
        elif key == "tier":
            result["tier"] = _yaml_scalar(value)

    return result


def _resolve_tier(stem: str, declared: str | None) -> str:
    """Tier value for an agent: a valid declared ``tier``, else the classifier default."""
    if declared and declared in {t.value for t in AgentTier}:
        return declared
    if declared:
        logger.warning("Agent %s declares unknown tier %r; using the default tier", stem, declared)
    return get_agent_tier(stem).value


def _extract_system_prompt_excerpt(content: str, max_chars: int = 300) -> str:
    """Return the first ``max_chars`` of the body after frontmatter (#1794)."""
    body = strip_frontmatter(content).strip()
    if len(body) > max_chars:
        return body[:max_chars] + "…"
    return body


class SpecializedAgentService:
    """Read-only service that discovers the host's Claude Code agents (#1794)."""

    def __init__(self, agents_dir: Path | None = None) -> None:
        self.agents_dir = agents_dir or claude_agents_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Whether the agents directory exists (False = the setting needs configuring)."""
        return self.agents_dir.is_dir()

    def list_agents(self) -> List[Dict[str, Any]]:
        """Return all agents found in the agents directory (#1794)."""
        if not self.agents_dir.exists():
            logger.warning("Agents directory not found: %s", self.agents_dir)
            return []

        agents: List[Dict[str, Any]] = []
        for md_file in sorted(self.agents_dir.glob("*.md")):
            agent = self._parse_file(md_file)
            if agent:
                agents.append(agent)

        return agents

    def list_payload(self) -> Dict[str, Any]:
        """Listing body for GET /agents/specialized, minus the timestamp (#1794)."""
        agents = self.list_agents()
        return {
            "agents": agents,
            "total_count": len(agents),
            "categories": self.get_categories_summary(agents),
            "available": self.is_available(),
        }

    def get_agent(self, agent_id: str) -> Dict[str, Any] | None:
        """Return a single agent by ID (stem of .md filename) (#1794)."""
        if not self.agents_dir.exists():
            return None

        md_file = self.agents_dir / f"{agent_id}.md"
        if not md_file.exists():
            return None

        return self._parse_file(md_file, include_full_prompt=True)

    def get_categories_summary(self, agents: List[Dict[str, Any]] | None = None) -> Dict[str, int]:
        """Return count per category (#1794)."""
        if agents is None:
            agents = self.list_agents()

        counts: Dict[str, int] = {}
        for agent in agents:
            cat = agent.get("category", CategoryDefaults.GENERAL)
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_file(self, md_file: Path, include_full_prompt: bool = False) -> Dict[str, Any] | None:
        """Parse a single .md agent file (#1794)."""
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            logger.error("Failed to read agent file: %s", md_file)
            return None

        frontmatter = _parse_frontmatter(content)
        name = frontmatter["name"] or md_file.stem
        description = frontmatter["description"]

        agent: Dict[str, Any] = {
            "id": md_file.stem,
            "name": name,
            "description": description,
            "model": frontmatter["model"],
            "color": frontmatter["color"],
            "tools": frontmatter["tools"],
            "category": _categorize_agent(name, description),
            "source_file": md_file.name,
            "tier": _resolve_tier(md_file.stem, frontmatter["tier"]),
            "type": "specialized",
            "excerpt": _extract_system_prompt_excerpt(content),
        }

        if include_full_prompt:
            agent["system_prompt"] = strip_frontmatter(content).strip()

        return agent
