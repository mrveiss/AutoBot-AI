# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat graph is the canonical loop; ``AgentLoop`` is marked PORTED (#21024, #20846).

Maintainer decision 2026-11-07: ``chat_workflow/graph.py`` is the canonical loop. This keeps that
recorded where a reader of ``AgentLoop`` lands, keeps the ask-human and chat-graph defaults defined
once in SSOT, and keeps ``agent_loop/types.py`` reading them instead of carrying its own literals.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

MARKER = "PORTED TO THE CHAT GRAPH"
GRAPH = "chat_workflow/graph.py"
_LOOP_DIR = "autobot-backend/agent_loop"


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def names_chat_graph_canonical(text: str) -> bool:
    """True when the text carries the PORTED marker and names the chat graph module."""
    return MARKER in text and GRAPH in text


def types_defines_own_literals(text: str) -> list[str]:
    """Literal ask-human defaults or env reads in ``types.py`` (SSOT must own them)."""
    found = []
    if re.search(r"env_int\(\s*[\"']AUTOBOT_ASK_HUMAN", text):
        found.append("env_int read of AUTOBOT_ASK_HUMAN_*")
    if re.search(r"ask_human_escalation_policy\s*:\s*str\s*=\s*[\"']", text):
        found.append("literal ask_human_escalation_policy default")
    if re.search(r"ASK_HUMAN_TIMEOUT_SECONDS\s*:\s*int\s*=\s*\d", text):
        found.append("literal ASK_HUMAN_TIMEOUT_SECONDS")
    return found


def test_package_and_class_docstrings_name_chat_graph_canonical():
    for rel in (f"{_LOOP_DIR}/__init__.py", f"{_LOOP_DIR}/loop.py"):
        assert names_chat_graph_canonical(_read(rel)), f"{rel} lacks the PORTED marker"


def test_ssot_fields_exist_with_stop_off_defaults():
    from autobot_shared.ssot_config import LLMConfig

    f = LLMConfig.model_fields
    assert f["chat_planner_enabled"].default is False
    assert f["chat_stall_escalation"].default == "stop"
    assert f["ask_human_timeout_seconds"].default == 300
    assert f["ask_human_escalation_policy"].default == "abandon"


def test_types_reads_ssot_not_literals():
    text = _read(f"{_LOOP_DIR}/types.py")
    assert types_defines_own_literals(text) == []
    assert "_ssot_config.llm.ask_human_timeout_seconds" in text
    assert "_ssot_config.llm.ask_human_escalation_policy" in text


def test_control_catches_removed_marker_and_literals():
    """Control: the checks fire on planted input, so a pass is not an empty scan."""
    assert not names_chat_graph_canonical("NOT WIRED IN PRODUCTION (#11221)")
    assert names_chat_graph_canonical(f"{MARKER} ... {GRAPH}")
    assert types_defines_own_literals('X: int = env_int("AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS", 300)')
    assert types_defines_own_literals('ask_human_escalation_policy: str = "abandon"')
    assert types_defines_own_literals("ASK_HUMAN_TIMEOUT_SECONDS: int = 300")


def test_planner_is_a_chat_graph_node_behind_the_ssot_switch():
    """#21023: the planner is wired into the canonical loop, and only the SSOT switch turns it on."""
    graph = _read("autobot-backend/chat_workflow/graph.py")
    assert 'builder.add_node("create_plan", create_plan)' in graph
    assert "advance_after_tools(" in graph
    assert "config.llm.chat_planner_enabled" in _read("autobot-backend/chat_workflow/plan_runner.py")
    assert "_run_llm_iterations" in _read("autobot-backend/chat_workflow/manager.py")
    assert "open_for_ctx(" in _read("autobot-backend/chat_workflow/manager.py")
