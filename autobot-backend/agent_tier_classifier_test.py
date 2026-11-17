# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Guard test for AGENT_TIER_MAP roster drift (#14194).

AGENT_TIER_MAP (agent_tier_classifier.py) classifies AutoBot's internal
task-agent taxonomy -- ``AgentType`` in ``agents/agent_orchestration/types.py``,
dispatched at runtime by ``BaseModalityAgent`` subclasses
(``agents/*_agent.py``) and the orchestrator/workflow templates via
``LLMService.chat_optimized(agent_type=...)`` -- for vLLM prefix-cache tiering.

An agent_type absent from AGENT_TIER_MAP does not error -- get_agent_tier()
silently defaults it to TIER_1_DEFAULT (see agent_tier_classifier.py). This
test makes that silent default loud in both directions: an AgentType member
with no AGENT_TIER_MAP entry, and an AGENT_TIER_MAP entry with no AgentType
member (a dead/orphan entry).

``AgentType`` is read here WITHOUT going through agent_tier_classifier or the
``agents`` package: ``importlib.util.spec_from_file_location`` loads
  ``types.py`` in isolation. ``agents/__init__.py`` eagerly imports
  ``kb_librarian_agent`` (which imports ``services.llm_service``), and
  ``agents/agent_orchestration/__init__.py`` eagerly imports the distributed
  orchestration stack -- the same eager-`__init__` defect class as #12830 and
  #12814. ``types.py`` has no runtime dependency on either package (its one
  package-relative import, ``agents.base_agent``, is TYPE_CHECKING-only), so
  loading the file directly is safe and avoids the cycle entirely
  (``agent_tier_classifier`` is imported from inside
  ``services/llm_service.py``).

get_agent_tier() normalizes '_' -> '-' before lookup, so AgentType values are
compared here in dash form to match AGENT_TIER_MAP's own key convention.
"""

import importlib.util
import sys
from pathlib import Path

from agent_tier_classifier import AGENT_TIER_MAP

_BACKEND_ROOT = Path(__file__).resolve().parent
_AGENT_TYPES_FILE = _BACKEND_ROOT / "agents" / "agent_orchestration" / "types.py"

def _agent_orchestration_type_values() -> set[str]:
    """AgentType's string values, loaded without importing the ``agents`` package."""
    name = "_agent_orchestration_types_isolated"
    spec = importlib.util.spec_from_file_location(name, _AGENT_TYPES_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {_AGENT_TYPES_FILE}")
    module = importlib.util.module_from_spec(spec)

    # Registered in sys.modules BEFORE exec_module, then removed.
    #
    # `types.py:169` declares a `@dataclass`, and `dataclasses._is_type` does
    # `sys.modules.get(cls.__module__).__dict__` (CPython 3.14
    # dataclasses.py:814) while scanning for a `KW_ONLY` sentinel. A module
    # executed out-of-band is not in `sys.modules`, so that `.get()` returns
    # None and class creation dies on
    # `'NoneType' object has no attribute '__dict__'`.
    #
    # So `spec_from_file_location` + `exec_module` alone is only safe for a
    # module that declares no dataclass. Same register-then-pop shape as
    # `migrations/runner_deferral_test.py` and `migrations/seed_agents_test.py`,
    # and the `finally` matters: leaving the name behind would shadow a real
    # import for the rest of the session.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        return {member.value.replace("_", "-") for member in module.AgentType}
    finally:
        sys.modules.pop(name, None)


def test_agent_orchestration_roster_is_non_empty():
    """Sanity check: the AgentType scan must find real members (#14194)."""
    assert len(_agent_orchestration_type_values()) >= 5


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
    """Every AGENT_TIER_MAP key is an AgentType member (#14194).

    Direction 2 (mapped, no definition): a dead entry -- the agent was renamed
    or removed and AGENT_TIER_MAP was never updated.
    """
    orphans = set(AGENT_TIER_MAP) - _agent_orchestration_type_values()
    assert not orphans, (
        f"AGENT_TIER_MAP entries with no matching AgentType member: {sorted(orphans)}. "
        "Remove the dead entry, or restore the AgentType member if it still exists."
    )
