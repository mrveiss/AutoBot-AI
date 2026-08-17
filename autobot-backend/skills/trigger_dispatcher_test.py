# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the skill trigger dispatcher (#14406).

Every assertion here is about *reachability*: that emitting a declared event
ends up running the declaring skill's handler.  Asserting that a manifest
contains a trigger name would restate the config and stay green while nothing
fires — that class of test is precisely why #14406 existed.

The emitter tests deliberately start at the production function that produces
the event (``api.files.upload_file``, ``AgentExecutor._maybe_trigger_gap_development``,
``SkillRouterSkill._build_missing_skill``) rather than at ``emit_skill_trigger``,
so they prove the whole chain and not just the dispatcher's own input handling.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import UploadFile

from skills.base_skill import DeclarativeSkill
from skills.builtin.autonomous_skill_development import AutonomousSkillDevelopmentSkill
from skills.builtin.document_analysis import DocumentAnalysisSkill
from skills.gap_detector import GapTrigger, SkillGapDetector
from skills.manager import SkillManager
from skills.registry import SkillRegistry
from skills.trigger_dispatcher import (
    EMITTED_TRIGGERS,
    PENDING_EMITTER_TRIGGERS,
    declared_event_triggers,
    emit_skill_trigger,
    resolve_trigger_targets,
)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only."""
    return "asyncio"


@pytest.fixture
def registry(monkeypatch):
    """An isolated registry wired into the dispatcher in place of the singleton."""
    fresh = SkillRegistry()
    manager = SkillManager(registry=fresh)
    monkeypatch.setattr("skills.trigger_dispatcher.get_skill_registry", lambda: fresh)
    monkeypatch.setattr("skills.trigger_dispatcher.get_skill_manager", lambda: manager)
    return fresh


def _enabled(registry, skill_class):
    """Register *skill_class* and return the enabled instance."""
    registry.register(skill_class)
    skill = registry.get(skill_class.get_manifest().name)
    skill.enable()
    return skill


# ---------------------------------------------------------------------------
# The dispatcher itself: does emitting an event reach the handler?
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_emitting_a_declared_trigger_runs_the_declaring_skills_handler(registry):
    """The core claim: dispatch reaches the handler, with the emitted params."""
    _enabled(registry, DocumentAnalysisSkill)
    params = {"file_path": "/tmp/report.pdf"}  # nosec B108

    handler = AsyncMock(return_value={"success": True, "reached": True})
    with patch.object(DocumentAnalysisSkill, "_analyze", new=handler):
        results = await emit_skill_trigger("document_uploaded", params)

    handler.assert_awaited_once()
    assert handler.await_args.args[0] == params
    assert results == [{"success": True, "reached": True}]


@pytest.mark.anyio
async def test_a_disabled_skill_is_not_dispatched(registry):
    """A declared trigger must not run a skill the operator has not enabled."""
    registry.register(DocumentAnalysisSkill)  # registered but left disabled

    handler = AsyncMock(return_value={"success": True})
    with patch.object(DocumentAnalysisSkill, "_analyze", new=handler):
        results = await emit_skill_trigger("document_uploaded", {"file_path": "/tmp/x.pdf"})  # nosec B108

    handler.assert_not_awaited()
    assert results == []


@pytest.mark.anyio
async def test_an_undeclared_event_reaches_nobody(registry):
    """An event no manifest declares must not reach any skill."""
    _enabled(registry, DocumentAnalysisSkill)

    handler = AsyncMock(return_value={"success": True})
    with patch.object(DocumentAnalysisSkill, "_analyze", new=handler):
        assert await emit_skill_trigger("not_a_declared_event", {}) == []
    handler.assert_not_awaited()


def test_a_declared_trigger_with_no_bound_action_is_not_dispatchable(registry):
    """An unbound declaration resolves to no target rather than a silent guess."""
    _enabled(registry, DocumentAnalysisSkill)
    with patch.object(DocumentAnalysisSkill, "get_trigger_actions", return_value={}):
        assert resolve_trigger_targets("document_uploaded") == []


# ---------------------------------------------------------------------------
# Emitters — asserted from the producing function, not from the dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_file_upload_endpoint_emits_document_uploaded(registry, monkeypatch, tmp_path):
    """Uploading a document through the real endpoint runs the analysis skill."""
    import api.files as files_api

    _enabled(registry, DocumentAnalysisSkill)
    monkeypatch.setattr(files_api, "SANDBOXED_ROOT", tmp_path)
    monkeypatch.setattr(files_api, "_log_upload_audit", lambda *a, **kw: None)

    auth = MagicMock()
    auth.check_file_permissions.return_value = (True, {"user_id": "tester"})
    monkeypatch.setattr(files_api, "get_auth_middleware", lambda: auth)

    upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello world"))
    request = MagicMock()
    request.state = MagicMock()

    handler = AsyncMock(return_value={"success": True})
    with patch.object(DocumentAnalysisSkill, "_analyze", new=handler):
        await files_api.upload_file(request=request, file=upload, path="", overwrite=False)

    handler.assert_awaited_once()
    assert handler.await_args.args[0]["file_path"] == str(tmp_path / "notes.txt")


@pytest.mark.anyio
async def test_agent_response_signalling_a_gap_emits_explicit_gap_signal(registry):
    """An agent response stating it lacks a tool reaches the gap-development skill."""
    from agents.agent_orchestration.agent_execution import AgentExecutor

    _enabled(registry, AutonomousSkillDevelopmentSkill)
    executor = AgentExecutor.__new__(AgentExecutor)

    pipeline = AsyncMock(return_value={"success": True, "state": "pending"})
    with (
        patch("skills.registry.get_skill_registry", lambda: registry),
        patch("skills.builtin.autonomous_skill_development._get_governance_mode", new=AsyncMock(return_value="semi_auto")),
        patch("skills.builtin.autonomous_skill_development._run_development_pipeline", new=pipeline),
    ):
        await executor._maybe_trigger_gap_development("I don't have a tool to convert FLAC files.\n", {})

    pipeline.assert_awaited_once()
    assert "flac" in pipeline.await_args.args[0].lower()
    assert pipeline.await_args.args[1] == "autobot-self"


@pytest.mark.anyio
async def test_router_finding_no_matching_skill_emits_agent_capability_gap(registry):
    """The router's gap-fill path reaches the gap-development skill by event, not by name."""
    from skills.builtin.skill_router import SkillRouterSkill

    _enabled(registry, AutonomousSkillDevelopmentSkill)
    router = SkillRouterSkill()

    pipeline = AsyncMock(return_value={"success": True, "state": "pending"})
    with (
        patch.object(SkillRouterSkill, "_research_capability", new=AsyncMock(return_value={})),
        patch("skills.builtin.autonomous_skill_development._get_governance_mode", new=AsyncMock(return_value="semi_auto")),
        patch("skills.builtin.autonomous_skill_development._run_development_pipeline", new=pipeline),
    ):
        result = await router._build_missing_skill("summarise a spreadsheet", registry, dry_run=False)

    pipeline.assert_awaited_once()
    assert pipeline.await_args.args[1] == "skill-router"
    assert result["build_triggered"] is True


def test_analyze_agent_output_only_ever_reports_an_explicit_gap():
    """Guards the unconditional ``explicit_gap_signal`` label in the emitter.

    ``_maybe_trigger_gap_development`` labels every gap from this detector call
    ``explicit_gap_signal``.  That is only correct while the detector cannot
    report any other kind, so assert the invariant instead of the one instance.
    """
    detector = SkillGapDetector([])
    samples = [
        "I don't have a tool to convert FLAC files.\n",
        "I cannot render charts because there is no tool.\n",
        "No skill exists to publish releases.\n",
        "capability unavailable: OCR on scanned pages\n",
    ]
    reported = [detector.analyze_agent_output(text) for text in samples]
    assert all(gap is not None for gap in reported), "sample no longer trips the detector"
    assert {gap.trigger for gap in reported} == {GapTrigger.EXPLICIT}


# ---------------------------------------------------------------------------
# Guards — a manifest must not declare a trigger nothing can produce
# ---------------------------------------------------------------------------


def _event_skills():
    """Every registered non-declarative skill, from a real builtin discovery."""
    reg = SkillRegistry()
    reg.discover_builtin_skills()
    return reg, [
        (info["name"], reg.get(info["name"]))
        for info in reg.list_skills()
        if not isinstance(reg.get(info["name"]), DeclarativeSkill)
    ]


def test_every_declared_trigger_is_either_emitted_or_recorded_as_pending(monkeypatch):
    """The two sets must partition the declared triggers exactly.

    Adding a trigger to a manifest without an emitter fails here unless it is
    recorded in ``PENDING_EMITTER_TRIGGERS`` with a reason, and an entry left
    behind after its emitter lands fails too — a stale exemption that quietly
    covers nothing is the failure mode this guard exists to prevent.
    """
    reg, _ = _event_skills()
    monkeypatch.setattr("skills.trigger_dispatcher.get_skill_registry", lambda: reg)

    declared = declared_event_triggers()
    pending = set(PENDING_EMITTER_TRIGGERS)

    assert not (EMITTED_TRIGGERS & pending), "a trigger cannot be both emitted and pending"
    assert declared == EMITTED_TRIGGERS | pending, (
        "declared triggers must be exactly the emitted ones plus the recorded pending ones; "
        f"undeclared entries={sorted((EMITTED_TRIGGERS | pending) - declared)} "
        f"unaccounted declarations={sorted(declared - (EMITTED_TRIGGERS | pending))}"
    )


def test_every_declared_trigger_binds_an_action_the_skill_actually_provides():
    """A declared trigger with no binding, or a binding to a non-tool, is unreachable."""
    _, skills = _event_skills()
    unbound, unknown = [], []
    for name, skill in skills:
        manifest = skill.get_manifest()
        bindings = skill.get_trigger_actions()
        for trigger in manifest.triggers:
            action = bindings.get(trigger)
            if not action:
                unbound.append(f"{name}:{trigger}")
            elif action not in manifest.tools:
                unknown.append(f"{name}:{trigger}->{action}")

    assert not unbound, f"declared triggers with no bound action: {unbound}"
    assert not unknown, f"triggers bound to an action the skill does not provide: {unknown}"


def test_no_binding_names_a_trigger_the_manifest_does_not_declare():
    """A binding for an undeclared trigger is drift in the other direction."""
    _, skills = _event_skills()
    stray = [
        f"{name}:{trigger}"
        for name, skill in skills
        for trigger in skill.get_trigger_actions()
        if trigger not in skill.get_manifest().triggers
    ]
    assert not stray, f"bindings for triggers no manifest declares: {stray}"


@pytest.mark.anyio
async def test_autonomous_skill_development_is_reachable_through_execute_skill(registry):
    """Regression for the ``execute`` signature that broke every canonical path.

    Its ``execute`` took ``(params)`` only, so ``SkillManager.execute_skill`` —
    and therefore ``POST /api/skills/{name}/execute`` and the dispatcher —
    raised ``TypeError`` against this skill while the two hand-written direct
    callers worked.
    """
    _enabled(registry, AutonomousSkillDevelopmentSkill)
    manager = SkillManager(registry=registry)

    pipeline = AsyncMock(return_value={"success": True, "state": "pending"})
    with (
        patch("skills.builtin.autonomous_skill_development._get_governance_mode", new=AsyncMock(return_value="semi_auto")),
        patch("skills.builtin.autonomous_skill_development._run_development_pipeline", new=pipeline),
    ):
        result = await manager.execute_skill(
            "autonomous-skill-development",
            "trigger_gap_development",
            {"capability": "convert FLAC"},
        )

    assert result["success"] is True
    pipeline.assert_awaited_once()
