# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for self-awareness context-block gating (#12509).

Every chat message was getting prefixed with a
``[SYSTEM CONTEXT - AutoBot Self-Awareness]`` block reporting
"System Maturity: 0%, 0 capabilities across 0 categories, Completed
Phases: 0/10" — a broken/uninitialized state (root cause: the optional
``PhaseValidator``/``phase_validation_system`` dependency is absent, same as
#12458, so ``current_capabilities`` never gets populated). Injecting that
zero-state into every prompt both wastes context and biases the model
toward "0 capabilities" hedging.

These tests verify that ``inject_awareness_context()`` omits the block
entirely when the underlying maturity/capability data is empty, and still
injects it when there is real, non-empty data.
"""

import pytest

from llm_self_awareness import LLMSelfAwareness

ZERO_STATE_CONTEXT = {
    "system_identity": {
        "name": "AutoBot",
        "version": "1.0.0",
        "current_phase": "phase_6_self_awareness",
        "system_maturity": 0,
    },
    "current_capabilities": {"active": [], "count": 0, "categories": {}},
    "phase_information": {
        "current_phase": "phase_6_self_awareness",
        "completion_status": {},
        "completed_phases": 0,
        "total_phases": 10,
    },
    "system_metrics": {"maturity_score": 0, "validation_score": 0, "capability_count": 0},
    "operational_status": {
        "auto_progression_enabled": True,
        "last_validation": None,
        "recent_changes": 0,
        "milestones_achieved": 0,
    },
    "contextual_information": {},
}

REAL_DATA_CONTEXT = {
    "system_identity": {
        "name": "AutoBot",
        "version": "1.0.0",
        "current_phase": "Phase 3: LLM Integration",
        "system_maturity": 40,
    },
    "current_capabilities": {
        "active": ["basic_api", "llm_interface"],
        "count": 2,
        "categories": {"core": ["basic_api"], "ai": ["llm_interface"]},
    },
    "phase_information": {
        "current_phase": "Phase 3: LLM Integration",
        "completion_status": {},
        "completed_phases": 2,
        "total_phases": 10,
    },
    "system_metrics": {"maturity_score": 40, "validation_score": 80, "capability_count": 2},
    "operational_status": {
        "auto_progression_enabled": True,
        "last_validation": None,
        "recent_changes": 0,
        "milestones_achieved": 1,
    },
    "contextual_information": {},
}

ERROR_FALLBACK_CONTEXT = {
    "system_identity": {
        "name": "AutoBot",
        "version": "1.0.0",
        "error": "Failed to load complete context",
    },
    "current_capabilities": {"active": [], "error": "boom"},
}


def _make_awareness() -> LLMSelfAwareness:
    """Build an LLMSelfAwareness instance without running __init__.

    Issue #12509: __init__ wires up heavy collaborators (progression
    manager, state tracker, project state manager) that are irrelevant to
    the gating logic under test.
    """
    return object.__new__(LLMSelfAwareness)


class TestHasMeaningfulAwarenessData:
    """Unit tests for the `_has_meaningful_awareness_data` gate."""

    def test_zero_state_is_not_meaningful(self) -> None:
        assert LLMSelfAwareness._has_meaningful_awareness_data(ZERO_STATE_CONTEXT) is False

    def test_real_data_is_meaningful(self) -> None:
        assert LLMSelfAwareness._has_meaningful_awareness_data(REAL_DATA_CONTEXT) is True

    def test_error_fallback_context_is_not_meaningful(self) -> None:
        """Malformed/error-fallback shape must not raise KeyError — treated as empty."""
        assert LLMSelfAwareness._has_meaningful_awareness_data(ERROR_FALLBACK_CONTEXT) is False

    def test_nonzero_capability_count_alone_is_meaningful(self) -> None:
        context = {**ZERO_STATE_CONTEXT, "current_capabilities": {"active": ["x"], "count": 1, "categories": {}}}
        assert LLMSelfAwareness._has_meaningful_awareness_data(context) is True

    def test_nonzero_completed_phases_alone_is_meaningful(self) -> None:
        context = {
            **ZERO_STATE_CONTEXT,
            "phase_information": {**ZERO_STATE_CONTEXT["phase_information"], "completed_phases": 1},
        }
        assert LLMSelfAwareness._has_meaningful_awareness_data(context) is True


@pytest.mark.asyncio
class TestInjectAwarenessContext:
    """Issue #12509: block injection must be gated on non-empty data."""

    async def test_zero_state_omits_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        awareness = _make_awareness()

        async def _fake_get_system_context(include_detailed: bool = False):
            return ZERO_STATE_CONTEXT

        monkeypatch.setattr(awareness, "get_system_context", _fake_get_system_context)

        prompt = "How do I get to the city centre?"
        result = await awareness.inject_awareness_context(prompt)

        assert result == prompt
        assert "SYSTEM CONTEXT" not in result
        assert "System Maturity" not in result

    async def test_real_data_injects_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        awareness = _make_awareness()

        async def _fake_get_system_context(include_detailed: bool = False):
            return REAL_DATA_CONTEXT

        monkeypatch.setattr(awareness, "get_system_context", _fake_get_system_context)

        prompt = "How do I get to the city centre?"
        result = await awareness.inject_awareness_context(prompt)

        assert "[SYSTEM CONTEXT - AutoBot Self-Awareness]" in result
        assert "System Maturity: 40%" in result
        assert result.endswith(prompt)

    async def test_error_fallback_omits_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error-fallback context must not raise nor inject a broken block."""
        awareness = _make_awareness()

        async def _fake_get_system_context(include_detailed: bool = False):
            return ERROR_FALLBACK_CONTEXT

        monkeypatch.setattr(awareness, "get_system_context", _fake_get_system_context)

        prompt = "hello"
        result = await awareness.inject_awareness_context(prompt)

        assert result == prompt
