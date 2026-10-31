# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Differential test of the tool-classification planes (#13416, part of #13250).

Three planes classify the same tool names independently:

1. agent-loop approval  -- ``tool_catalogue.SENSITIVE_TOOLS``, prefix-matched (``match_tool_name``)
2. code-exec sandbox    -- ``code_exec.tool_policy`` (exact names, env-widenable injectable set)
3. work-item seam       -- ``tool_catalogue.APPROVAL_CATEGORY_TOOLS`` (word-boundary prefix)

Equality would fail constantly (prefix is broader than exact), so every assertion is a
one-directional safety property. Intentional exceptions are the commented allowlists
below; both are empty because no divergence exists at merge time.
Pure set logic: no network, model call, container or I/O.
"""

import sys
from pathlib import Path

import pytest

from autobot_shared.tool_catalogue import (
    APPROVAL_CATEGORY_TOOLS,
    SENSITIVE_TOOLS,
    TOOL_ALIASES,
    TOOL_EFFECTS,
    match_tool_name,
)

_BACKEND = str(Path(__file__).resolve().parents[1] / "autobot-backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

#: Tools plane 1 gates that may nevertheless be injectable into the sandbox. Each entry
#: needs a reason; empty means no such tool exists (verified by the tests below).
INJECTABLE_DESPITE_SENSITIVE: "dict[str, str]" = {}
#: Tools plane 2 calls sensitive that plane 1 does not gate. Same rule.
SANDBOX_SENSITIVE_UNGATED: "dict[str, str]" = {}
#: Plane-1 tools reachable through no plane-3 approval category. Same rule.
UNCATEGORISED_SENSITIVE: "dict[str, str]" = {}


def _policy():
    from chat_workflow.code_exec import tool_policy

    return tool_policy


def known_tool_names() -> "frozenset[str]":
    """Every tool name any plane knows, plus a prefix-variant of each plane-1 pattern."""
    tp = _policy()
    names = set(TOOL_EFFECTS) | set(TOOL_ALIASES) | set(SENSITIVE_TOOLS) | set(tp.SENSITIVE_TOOLS)
    names |= tp.CODEEXEC_INJECTABLE_TOOLS | tp.CODEEXEC_READONLY_TOOLS
    for tools in APPROVAL_CATEGORY_TOOLS.values():
        names |= set(tools)
    return frozenset(names)


def plane1_sensitive(name: str) -> bool:
    return match_tool_name(name, SENSITIVE_TOOLS) is not None


def injectable_but_sensitive(injectable: "frozenset[str]") -> "list[str]":
    """Tools plane 1 gates that are injectable, minus the explained exceptions."""
    return sorted(t for t in injectable if plane1_sensitive(t) and t not in INJECTABLE_DESPITE_SENSITIVE)


def sandbox_sensitive_but_ungated(sandbox_sensitive: "frozenset[str]") -> "list[str]":
    return sorted(t for t in sandbox_sensitive if not plane1_sensitive(t) and t not in SANDBOX_SENSITIVE_UNGATED)


def _in_no_category(tools: "frozenset[str]") -> "list[str]":
    in_category = {
        t
        for t in tools
        for pats in APPROVAL_CATEGORY_TOOLS.values()
        if match_tool_name(t, pats, word_boundary=True) is not None
    }
    return sorted(t for t in tools if t not in in_category)


def uncategorised(tools: "frozenset[str]") -> "list[str]":
    return [t for t in _in_no_category(tools) if t not in UNCATEGORISED_SENSITIVE]


def test_the_universe_is_not_empty():
    assert len(known_tool_names()) > 20 and SENSITIVE_TOOLS


def test_no_plane1_sensitive_tool_is_injectable_by_default():
    assert injectable_but_sensitive(_policy().CODEEXEC_INJECTABLE_TOOLS) == []


def test_no_plane1_sensitive_tool_is_injectable_when_the_env_is_widened_to_everything():
    """The hostile case: an operator lists every known tool as injectable and read-only."""
    universe = known_tool_names()
    injectable, readonly = _policy().derive_views(universe, universe)
    assert injectable_but_sensitive(injectable) == []
    assert injectable_but_sensitive(readonly) == []


def test_every_sandbox_sensitive_tool_is_gated_by_the_approval_plane():
    assert sandbox_sensitive_but_ungated(_policy().SENSITIVE_TOOLS) == []


def test_every_plane1_sensitive_tool_is_reachable_through_an_approval_category():
    assert uncategorised(SENSITIVE_TOOLS) == []


def test_allowlists_are_not_stale():
    """An allowlist entry for a tool that no longer diverges is dead and must be removed."""
    for allow, divergent in (
        (INJECTABLE_DESPITE_SENSITIVE, lambda t: t in _policy().CODEEXEC_INJECTABLE_TOOLS and plane1_sensitive(t)),
        (SANDBOX_SENSITIVE_UNGATED, lambda t: t in _policy().SENSITIVE_TOOLS and not plane1_sensitive(t)),
    ):
        assert all(divergent(t) for t in allow)
    assert set(UNCATEGORISED_SENSITIVE) <= set(_in_no_category(SENSITIVE_TOOLS))


# --- contrast: the checks fail when a plane drops a tool ---------------------


@pytest.mark.parametrize("dropped", ["write_file", "execute_command", "git_push", "terminal"])
def test_contrast_sandbox_plane_dropping_a_tool_makes_it_injectable_and_is_caught(monkeypatch, dropped):
    tp = _policy()
    monkeypatch.setattr(tp, "SENSITIVE_TOOLS", tp.SENSITIVE_TOOLS - {dropped})
    injectable, _ = tp.derive_views(known_tool_names(), known_tool_names())
    assert dropped in injectable_but_sensitive(injectable)


@pytest.mark.parametrize("dropped", ["write_file", "system_exec", "helm"])
def test_contrast_approval_plane_dropping_a_tool_is_caught(monkeypatch, dropped):
    import autobot_shared.approval_planes_differential_test as me

    monkeypatch.setattr(me, "SENSITIVE_TOOLS", frozenset(SENSITIVE_TOOLS - {dropped}))
    assert dropped in sandbox_sensitive_but_ungated(_policy().SENSITIVE_TOOLS)


def test_contrast_a_category_dropping_a_tool_is_caught(monkeypatch):
    import autobot_shared.approval_planes_differential_test as me

    trimmed = {k: tuple(t for t in v if t != "write_file") for k, v in APPROVAL_CATEGORY_TOOLS.items()}
    monkeypatch.setattr(me, "APPROVAL_CATEGORY_TOOLS", trimmed)
    assert "write_file" in uncategorised(SENSITIVE_TOOLS)
