# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for pending_skills registry + trigger_gap_fill (#7431)."""

import asyncio

import pytest

from skills.pending_skills import (
    PendingSkillsRegistry,
    get_pending_skills_registry,
    reset_pending_skills_registry_for_tests,
    trigger_gap_fill,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_pending_skills_registry_for_tests()
    yield
    reset_pending_skills_registry_for_tests()


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


def test_registry_starts_empty():
    assert PendingSkillsRegistry().size() == 0


def test_register_creates_binding_with_unique_id():
    """Each register() call produces a unique pending_skill_id."""
    r = PendingSkillsRegistry()
    a = r.register("intent A", "plan1", "task1")
    b = r.register("intent B", "plan1", "task2")
    assert a.pending_skill_id != b.pending_skill_id
    assert r.size() == 2


def test_register_records_intent_plan_task():
    """Binding fields match constructor args."""
    r = PendingSkillsRegistry()
    binding = r.register("translate French", "plan-x", "task-7", language="fr")
    assert binding.intent == "translate French"
    assert binding.plan_id == "plan-x"
    assert binding.task_id == "task-7"
    assert binding.metadata == {"language": "fr"}
    assert binding.created_at > 0


def test_get_returns_binding_by_id():
    r = PendingSkillsRegistry()
    binding = r.register("x", "p", "t")
    assert r.get(binding.pending_skill_id) is binding


def test_get_returns_none_for_unknown_id():
    assert PendingSkillsRegistry().get("no-such-id") is None


def test_clear_removes_binding():
    r = PendingSkillsRegistry()
    binding = r.register("x", "p", "t")
    assert r.clear(binding.pending_skill_id) is True
    assert r.get(binding.pending_skill_id) is None
    assert r.size() == 0


def test_clear_returns_false_for_unknown_id():
    assert PendingSkillsRegistry().clear("no-such-id") is False


def test_find_by_intent_returns_all_matching():
    """Multiple plans can wait on the same intent — find_by_intent
    returns every matching binding so the resume path can wake all of them."""
    r = PendingSkillsRegistry()
    a = r.register("translate", "plan1", "t1")
    b = r.register("translate", "plan2", "t2")
    r.register("summarize", "plan3", "t3")
    matches = r.find_by_intent("translate")
    assert len(matches) == 2
    assert {m.pending_skill_id for m in matches} == {a.pending_skill_id, b.pending_skill_id}


def test_all_bindings_returns_snapshot():
    """all_bindings() returns a list copy — mutating it doesn't affect the registry."""
    r = PendingSkillsRegistry()
    r.register("x", "p", "t")
    snap = r.all_bindings()
    snap.clear()
    assert r.size() == 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance():
    a = get_pending_skills_registry()
    b = get_pending_skills_registry()
    assert a is b


def test_reset_for_tests_drops_singleton():
    a = get_pending_skills_registry()
    reset_pending_skills_registry_for_tests()
    b = get_pending_skills_registry()
    assert a is not b


# ---------------------------------------------------------------------------
# trigger_gap_fill — fire-and-forget Phase 3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_gap_fill_records_binding_and_returns_id():
    binding = await trigger_gap_fill("novel intent", "plan-1", "task-1")
    # router_call=None case: binding is recorded but no Phase 3 invoked.
    assert binding.intent == "novel intent"
    assert binding.plan_id == "plan-1"
    assert binding.task_id == "task-1"
    assert get_pending_skills_registry().get(binding.pending_skill_id) is binding


@pytest.mark.asyncio
async def test_trigger_gap_fill_invokes_router_in_background():
    """When router_call is provided, it is awaited in a background task —
    trigger_gap_fill itself returns immediately."""
    invocations = []

    async def fake_router(intent: str):
        invocations.append(intent)
        return {"success": True, "build_triggered": True}

    binding = await trigger_gap_fill("translate French", "p1", "t1", router_call=fake_router)
    # Yield to let the create_task background coroutine run
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert binding.pending_skill_id  # returned synchronously
    assert invocations == ["translate French"]


@pytest.mark.asyncio
async def test_trigger_gap_fill_swallows_router_failures():
    """A failing background router_call must not crash the planner — the
    binding stays in the registry so observability surfaces stuck IDs."""

    async def failing_router(intent: str):
        raise RuntimeError("LLM down")

    binding = await trigger_gap_fill("stuck intent", "p1", "t1", router_call=failing_router)
    # Drain the background task
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Binding remains — test infrastructure / observability would surface this
    assert get_pending_skills_registry().get(binding.pending_skill_id) is not None
