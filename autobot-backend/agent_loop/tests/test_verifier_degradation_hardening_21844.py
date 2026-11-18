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
    assert "[truncated" in user and len(user) < 2000 and "x" * 101 not in user


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

    verifier_model._readings.clear()
    assert await verifier_model.resolve_verifier_model(_provider([config.verifier_model])) == config.verifier_model
    verifier_model._readings.clear()
    assert await verifier_model.resolve_verifier_model(_provider([])) == config.verifier_model


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
        assert await audit_verifier_degraded(result, "task-1")
    op = log.await_args.args[0]
    details = log.await_args.kwargs["details"]
    assert op == "verifier.degraded" and details["degradation"] == "timeout" and details["tool"] == "bash"
    assert details["model"] == "m"


@pytest.mark.asyncio
async def test_a_real_reading_writes_no_audit_event():
    ok = VerifierResult(VerifierVerdict.PASS, 0.1, "fine", "bash")
    with patch("services.audit_logger.audit_log", AsyncMock()) as log:
        assert not await audit_verifier_degraded(ok)
    log.assert_not_awaited()
