# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verifier hardening: timeout class, capped prompt, installed-model check, degraded-pass audit event (#21844)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import verifier_model, verifier_prompt
from autobot_shared.pre_action_verifier_guard import VerifierResult, VerifierVerdict
from autobot_shared.verifier_degradation import VerifierDegradation, failure_observation
from services.verifier_audit import audit_verifier_degraded


def _provider(models, name="ollama") -> MagicMock:
    provider = MagicMock()
    provider.provider_name = name
    provider.list_models = AsyncMock(return_value=models)
    return provider


def test_a_timeout_is_its_own_degradation_class_and_a_transport_error_is_not():
    assert failure_observation(asyncio.TimeoutError()).degradation is VerifierDegradation.TIMEOUT
    assert failure_observation(ConnectionError("x")).degradation is VerifierDegradation.CALL_FAILED


def test_a_huge_argument_is_truncated_with_a_marker_and_the_prompt_is_bounded():
    with (
        patch.object(verifier_prompt, "VERIFIER_ARG_MAX_CHARS", 100),
        patch.object(verifier_prompt, "VERIFIER_PROMPT_MAX_CHARS", 1000),
    ):
        _, user = verifier_prompt._build_verifier_prompt("bash", {"a": "x" * 50_000, "b": "y" * 50_000}, "r" * 50_000)
    assert "[truncated" in user
    assert len(user) <= 1000
    assert "x" * 101 not in user


def test_small_arguments_are_untouched():
    _, user = verifier_prompt._build_verifier_prompt("bash", {"cmd": "ls"}, "list")
    assert "cmd: 'ls'" in user and "truncated" not in user


@pytest.mark.asyncio
async def test_a_missing_model_falls_back_to_the_provider_default_loudly():
    verifier_model._readings.clear()
    with patch.object(verifier_model.logger, "error") as loud:
        assert await verifier_model.resolve_verifier_model(_provider(["other:latest"])) is None
    assert loud.called


@pytest.mark.asyncio
async def test_an_installed_model_is_kept_and_an_unreadable_list_proves_nothing():
    from autobot_shared.ssot_config import config

    with patch.object(config, "verifier_model", "verifier-test:1b"):
        verifier_model._readings.clear()
        assert await verifier_model.resolve_verifier_model(_provider(["verifier-test:1b"])) == "verifier-test:1b"
        verifier_model._readings.clear()
        assert await verifier_model.resolve_verifier_model(_provider([])) == "verifier-test:1b"


def test_a_bare_model_name_matches_its_latest_tag():
    assert verifier_model.model_listed("phi3", ["phi3:latest"]) and not verifier_model.model_listed(
        "phi3:mini", ["phi3"]
    )


@pytest.mark.asyncio
async def test_a_degraded_pass_writes_a_verifier_degraded_audit_event():
    result = VerifierResult(
        verdict=VerifierVerdict.SKIP,
        refutation_probability=0.0,
        rationale="x",
        tool_name="bash",
        degradation=VerifierDegradation.TIMEOUT,
        model_used="m",
    )
    with patch("services.audit_logger.audit_log", AsyncMock(return_value=True)) as log:
        assert await audit_verifier_degraded(result, "task-1", user_id="alice")
    op = log.await_args.args[0]
    assert log.await_args.kwargs["user_id"] == "alice" and log.await_args.kwargs["session_id"] == "task-1"
    details = log.await_args.kwargs["details"]
    assert op == "verifier.degraded" and details["degradation"] == "timeout" and details["tool"] == "bash"
    assert details["model"] == "m"


@pytest.mark.asyncio
async def test_a_real_reading_writes_no_audit_event():
    ok = VerifierResult(VerifierVerdict.PASS, 0.1, "fine", "bash")
    with patch("services.audit_logger.audit_log", AsyncMock()) as log:
        assert not await audit_verifier_degraded(ok)
    log.assert_not_awaited()


def test_an_empty_verifier_model_resolves_to_the_light_processing_model(monkeypatch) -> None:
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config, "verifier_model", "")
    assert verifier_model.configured_verifier_model(_provider([])) == config.light_processing_model
    assert verifier_model.configured_verifier_model(_provider([], name="anthropic")) is None


def test_the_whole_prompt_stays_within_a_limit_the_reason_alone_would_exceed():
    with (
        patch.object(verifier_prompt, "VERIFIER_ARG_MAX_CHARS", 2000),
        patch.object(verifier_prompt, "VERIFIER_PROMPT_MAX_CHARS", 1000),
    ):
        _, user = verifier_prompt._build_verifier_prompt("bash", {}, "r" * 2000)
        _, with_args = verifier_prompt._build_verifier_prompt("bash", {"a": "x" * 5000}, "r" * 2000)
    assert len(user) <= 1000 and len(with_args) <= 1000


def test_a_tiny_limit_imports_and_the_prompt_is_still_valid():
    import importlib

    with patch.dict("os.environ", {"AUTOBOT_VERIFIER_PROMPT_MAX_CHARS": "10"}):
        importlib.reload(verifier_prompt)  # must not raise
    importlib.reload(verifier_prompt)
    with patch.object(verifier_prompt, "VERIFIER_PROMPT_MAX_CHARS", 10):
        _, user = verifier_prompt._build_verifier_prompt("bash", {"a": "b"}, "why")
    assert "Proposed agent action" in user and "REFUTATION_PROBABILITY" in user


def test_a_huge_tool_name_is_capped_inside_the_prompt_limit():
    _, user = verifier_prompt._build_verifier_prompt("t" * 100_000, {"a": "b"}, "why")
    assert len(user) <= verifier_prompt.VERIFIER_PROMPT_MAX_CHARS


@pytest.mark.asyncio
async def test_the_model_lookup_runs_under_the_verifier_deadline_and_a_failed_pass_names_the_model():
    from autobot_shared import pre_action_verifier_guard as guard
    from autobot_shared.ssot_config import config

    async def slow_list():
        await asyncio.sleep(5)

    provider = _provider([])
    provider.list_models = slow_list
    verifier_model._readings.clear()
    with (
        patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)),
        patch.object(guard, "VERIFIER_TIMEOUT_S", 0.05),
        patch.object(config, "verifier_model", "verifier-test:1b"),
    ):
        obs = await guard._call_verifier_once("bash", {}, "why", None)
    assert obs.degradation is VerifierDegradation.TIMEOUT
    assert obs.provider_used == "ollama" and obs.model_used == "verifier-test:1b"


@pytest.mark.asyncio
async def test_the_health_probe_is_not_applicable_when_the_verifier_is_disabled():
    from api import verifier_model_health
    from autobot_shared import pre_action_verifier_guard as guard

    with patch.object(guard, "VERIFIER_ENABLED", False):
        health = await verifier_model_health._verifier_model_health_probe()
    assert health.status == "not_applicable"


def test_a_long_tool_name_cannot_push_the_prompt_past_a_tight_limit():
    limit = verifier_prompt._TEMPLATE_MIN_CHARS + 4
    with patch.object(verifier_prompt, "VERIFIER_PROMPT_MAX_CHARS", limit):
        _, user = verifier_prompt._build_verifier_prompt("execute_command", {"a": "b"}, "why")
    assert len(user) <= limit


@pytest.mark.asyncio
async def test_a_provider_default_request_that_times_out_does_not_claim_the_configured_model():
    from autobot_shared import pre_action_verifier_guard as guard
    from autobot_shared.ssot_config import config

    provider = _provider(["other:latest"])
    provider.chat_completion = AsyncMock(side_effect=asyncio.TimeoutError())
    verifier_model._readings.clear()
    with (
        patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)),
        patch.object(config, "verifier_model", "verifier-test:1b"),
    ):
        obs = await guard._call_verifier_once("bash", {}, "why", None)
    assert obs.model_used is None
