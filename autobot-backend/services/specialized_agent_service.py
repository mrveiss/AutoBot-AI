# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Specialized Agent Service (#1794)

Parses .claude/agents/*.md files to surface AutoBot specialized agent
definitions in the web UI.  Each .md file uses YAML frontmatter
(name, description, model, color, tools) followed by a markdown system
prompt.
"""

import re
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Repository root — two levels up from services/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"

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


def _parse_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from an agent .md file (#1794).

    Supports: name, description, model, color, tools (comma-separated).
    """
    result: Dict[str, Any] = {
        "name": "",
        "description": "",
        "tools": [],
        "color": "gray",
        "model": None,
    }

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return result

    for line in match.group(1).split("\n"):
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

    return result


def _extract_system_prompt_excerpt(content: str, max_chars: int = 300) -> str:
    """Return the first ``max_chars`` of the body after frontmatter (#1794)."""
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
    body = content[match.end() :].strip() if match else content.strip()
    if len(body) > max_chars:
        return body[:max_chars] + "…"
    return body


class SpecializedAgentService:
    """Read-only service that discovers AutoBot specialized agents (#1794)."""

    def __init__(self, agents_dir: Path | None = None) -> None:
        self.agents_dir = agents_dir or _AGENTS_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            cat = agent.get("category", "general")
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
            "source_file": str(md_file.relative_to(_REPO_ROOT)),
            "type": "specialized",
            "excerpt": _extract_system_prompt_excerpt(content),
        }

        if include_full_prompt:
            match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
            agent["system_prompt"] = content[match.end() :].strip() if match else content.strip()

        return agent
