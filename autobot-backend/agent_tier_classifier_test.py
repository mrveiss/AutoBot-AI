# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Guard test for AGENT_TIER_MAP roster drift (#14194).

AGENT_TIER_MAP (agent_tier_classifier.py) classifies TWO independent agent
rosters for vLLM prefix-cache tiering, and neither roster can see the other:

  1. Claude Code dev subagents -- one ``.claude/agents/*.md`` file per agent,
     each carrying the agent's ``name:`` frontmatter field.
  2. AutoBot's own internal task-agent taxonomy -- ``AgentType`` in
     ``agents/agent_orchestration/types.py``, dispatched at runtime by
     ``BaseModalityAgent`` subclasses (``agents/*_agent.py``) and the
     orchestrator/workflow templates via
     ``LLMService.chat_optimized(agent_type=...)``.

An agent_type absent from AGENT_TIER_MAP does not error -- get_agent_tier()
silently defaults it to TIER_1_DEFAULT (see agent_tier_classifier.py). This
test makes that silent default loud in both directions: a roster member with
no AGENT_TIER_MAP entry, and an AGENT_TIER_MAP entry with no roster member
(a dead/orphan entry).

Both rosters are read here WITHOUT going through agent_tier_classifier or the
``agents`` package:

- ``.claude/agents/*.md`` via a regex frontmatter scan -- the same technique
  ``services/specialized_agent_service.py`` already uses in production.
- ``AgentType`` via ``importlib.util.spec_from_file_location``, loading
  ``types.py`` in isolation. ``agents/__init__.py`` eagerly imports
  ``kb_librarian_agent`` (which imports ``services.llm_service``), and
  ``agents/agent_orchestration/__init__.py`` eagerly imports the distributed
  orchestration stack -- the same eager-`__init__` defect class as #12830 and
  #12814. ``types.py`` has no runtime dependency on either package (its one
  package-relative import, ``agents.base_agent``, is TYPE_CHECKING-only), so
  loading the file directly is safe and avoids the cycle entirely
  (``agent_tier_classifier`` is imported from inside
  ``services/llm_service.py``).

get_agent_tier() normalizes '_' -> '-' before lookup, so both rosters are
compared here in dash form to match AGENT_TIER_MAP's own key convention.
"""

import importlib.util
import re
from pathlib import Path

from agent_tier_classifier import AGENT_TIER_MAP

_BACKEND_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_ROOT.parent
_CLAUDE_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"
_AGENT_TYPES_FILE = _BACKEND_ROOT / "agents" / "agent_orchestration" / "types.py"

_FRONTMATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def _claude_subagent_names() -> set[str]:
    """Every ``name:`` frontmatter value across ``.claude/agents/*.md``."""
    names: set[str] = set()
    for md_file in sorted(_CLAUDE_AGENTS_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        block = _FRONTMATTER_BLOCK_RE.match(content)
        if not block:
            continue
        name_match = _FRONTMATTER_NAME_RE.search(block.group(1))
        if name_match:
            names.add(name_match.group(1))
    return names


def _agent_orchestration_type_values() -> set[str]:
    """AgentType's string values, loaded without importing the ``agents`` package."""
    spec = importlib.util.spec_from_file_location("_agent_orchestration_types_isolated", _AGENT_TYPES_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {_AGENT_TYPES_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {member.value.replace("_", "-") for member in module.AgentType}


def test_claude_subagent_roster_is_non_empty():
    """Sanity check: the .claude/agents scan must find real agents (#14194).

    Guards against a silently-empty roster making the drift tests vacuously
    pass -- e.g. a wrong path or a frontmatter format change.
    """
    assert len(_claude_subagent_names()) >= 10


def test_agent_orchestration_roster_is_non_empty():
    """Sanity check: the AgentType scan must find real members (#14194)."""
    assert len(_agent_orchestration_type_values()) >= 5


def test_every_claude_subagent_definition_is_mapped():
    """Every .claude/agents/*.md name has an AGENT_TIER_MAP entry (#14194).

    Direction 1 (on disk, unmapped): the agent silently defaults to
    TIER_1_DEFAULT instead of getting a deliberate classification.
    """
    unmapped = _claude_subagent_names() - set(AGENT_TIER_MAP)
    assert not unmapped, (
        f"Agent definition(s) on disk with no AGENT_TIER_MAP entry: {sorted(unmapped)}. "
        "Add a deliberate AgentTier to AGENT_TIER_MAP in agent_tier_classifier.py."
    )


def test_every_agent_orchestration_type_is_mapped():
    """Every AgentType member has an AGENT_TIER_MAP entry (#14194).

    Same failure mode as above, for AutoBot's internal task-agent roster.
    """
    unmapped = _agent_orchestration_type_values() - set(AGENT_TIER_MAP)
    assert not unmapped, (
        f"AgentType member(s) with no AGENT_TIER_MAP entry: {sorted(unmapped)}. "
        "Add a deliberate AgentTier to AGENT_TIER_MAP in agent_tier_classifier.py."
    )


def test_agent_tier_map_has_no_orphan_entries():
    """Every AGENT_TIER_MAP key traces to one of the two known rosters (#14194).

    Direction 2 (mapped, no definition anywhere): a dead entry -- the agent
    was renamed or removed and AGENT_TIER_MAP was never updated.
    """
    known_roster = _claude_subagent_names() | _agent_orchestration_type_values()
    orphans = set(AGENT_TIER_MAP) - known_roster
    assert not orphans, (
        f"AGENT_TIER_MAP entries with no matching .claude/agents definition or "
        f"AgentType member: {sorted(orphans)}. Remove the dead entry, or restore the "
        "missing agent definition / AgentType member if it still exists elsewhere."
    )
