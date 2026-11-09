# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the live eval's bounded profile still allows, kept visible, and the KB environment cause (#20843)."""

import pytest

from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, _UNIFORM_BUILTIN_TOOLS
from eval.live import READ_ONLY_AGENT_ID, LiveChatCandidate, LiveRunRecord
from eval.runner import TrajectoryReplayer
from eval.store import GoldenTrajectory
from orchestration.agent_registry import match_forbidden_tool, resolve_forbidden_tools

#: Builtin chat tools the ``research_agent`` profile does NOT hard-block. The allowlist assertion
#: (``forbidden_tools``) is what fails a golden that calls any of them; this pins the set so a change to the
#: profile, the builtins or the forbidden manifest shows up here and gets a decision.
_STILL_ALLOWED = frozenset(
    {
        "web_search",
        "read_spilled_output",
        "scrape_url",
        "crawl_site",
        "map_site",
        "extract_structured_data",
        "extract_content",
        "content_reach",
        "navigate",
        "click",
        "fill",
        "select",
        "hover",
        "screenshot",
        "evaluate",
        "get_text",
        "get_attribute",
        "wait_for_selector",
        "click_index",
        "fill_index",
        "select_index",
        "hover_index",
        "browser_state",
        "code_interpreter",
        # LLC work-object tools: allowed by the profile, but each refuses without a verified company
        # (`tool_dispatch_guards.llc_scope_error`), and an eval session carries none.
        "create_task",
        "record_decision",
        "request_approval",
        "update_goal",
    }
)


def test_the_research_agent_profile_still_allows_exactly_these_builtin_tools():
    forbidden = resolve_forbidden_tools(READ_ONLY_AGENT_ID)
    builtins = set(_UNIFORM_BUILTIN_TOOLS) | set(_BUILTIN_TOOL_SCHEMAS)
    allowed = {tool for tool in builtins if match_forbidden_tool(tool, forbidden) is None}
    assert allowed == set(
        _STILL_ALLOWED
    ), f"newly allowed: {sorted(allowed - _STILL_ALLOWED)}; no longer allowed: {sorted(_STILL_ALLOWED - allowed)}"


def test_the_shell_tool_is_hard_blocked_by_the_profile():
    assert match_forbidden_tool("execute_command", resolve_forbidden_tools(READ_ONLY_AGENT_ID)) is not None


async def _resolve(model):
    return "http://127.0.0.1:11434"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["empty", "unreachable"])
async def test_a_grounded_golden_on_an_empty_or_unreachable_kb_is_not_run_as_an_environment_cause(status):
    calls = []

    async def turn(g, model, workspace):
        calls.append(g.trajectory_id)
        return LiveRunRecord(final_text="x")

    async def kb():
        return status

    candidate = LiveChatCandidate(
        ["m"], "ollama", turn_runner=turn, resolve_endpoint=_resolve, resolve_provider=lambda: "ollama", probe_kb=kb
    )
    await candidate.prepare()
    grounded = GoldenTrajectory("qa", "knowledge_qa", {"prompt": "p"}, [], 0.9)
    ungrounded = GoldenTrajectory("fix", "code_fix", {"prompt": "p"}, [], 0.9)
    report = await TrajectoryReplayer().run([grounded, ungrounded], candidate.runner_for("m"))
    first, second = report.outcomes
    assert first.classify() == "unmeasured" and f"knowledge base is {status}" in first.detail
    assert "unsupported_claim" not in first.failure_categories
    assert calls == ["fix"], "the grounded turn must not have run"
    assert second.passed is True
    assert candidate.kb_status == status


def test_every_mutating_member_of_the_still_allowed_set_is_gated_by_an_approval_category():
    """The profile does not block these, so the approval categories must: each mutating one is gated."""
    from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS, ToolEffect, match_tool_name, tools_with

    gated = [tool for tools in APPROVAL_CATEGORY_TOOLS.values() for tool in tools]
    mutating = sorted(t for t in _STILL_ALLOWED if t in tools_with(ToolEffect.MUTATING))
    assert {"navigate", "click", "fill", "select", "evaluate", "code_interpreter"} <= set(mutating), mutating
    ungated = [t for t in mutating if match_tool_name(t, gated, word_boundary=True) is None]
    assert ungated == [], f"allowed by the profile and gated by no approval category: {ungated}"
