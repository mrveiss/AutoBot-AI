# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the one typed AI Stack agent shape (#22141)."""

from type_defs.ai_stack_agents import AIStackAgent, agent_dicts, agent_names


def test_agent_names_of_bare_strings_after_normalising() -> None:
    assert agent_names({"agents": agent_dicts(["rag", "chat"])}) == ["rag", "chat"]


def test_agent_names_of_mixed_list_after_normalising() -> None:
    mixed = ["rag", {"name": "llama3.2:3b", "type": "llama3_2_3b"}, {"id": "kb"}]
    assert agent_names({"agents": agent_dicts(mixed)}) == ["rag", "llama3.2:3b", "kb"]


def test_agent_names_of_empty_result() -> None:
    assert agent_names({}) == []


def test_nameless_entries_are_skipped() -> None:
    assert agent_dicts([{}, {"status": "ready"}, "", "rag"]) == [AIStackAgent(name="rag", type="rag").model_dump()]


def test_status_is_passed_through_only_when_present() -> None:
    reported, silent = agent_dicts([{"name": "a", "status": "busy"}, "b"])
    assert reported["status"] == "busy"
    assert silent["status"] is None
