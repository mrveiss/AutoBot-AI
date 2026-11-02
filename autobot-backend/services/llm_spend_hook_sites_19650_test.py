# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The router escalation and the verifier report spend through the hook; startup registers it (#19650)."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import pre_action_verifier_guard as guard
from autobot_shared import spend_recording as hook
from initialization import background_workers as bw
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.tiered_routing.complexity_router import ESCALATION_SPEND_SITE, ComplexityRouter
from llm_shared.tiered_routing.tier_config import TierConfig, TierModels

_USAGE = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


@pytest.fixture(autouse=True)
def _clean_hook():
    hook._reset_for_tests()
    yield
    hook._reset_for_tests()


def _recorder():
    seen = []

    async def record(response, *, endpoint, metadata):
        seen.append((response, endpoint, metadata))

    return record, seen


def _router() -> ComplexityRouter:
    return ComplexityRouter(
        TierConfig(enabled=True, complexity_threshold=3.0, models=TierModels(simple="a", complex="b"))
    )


async def _escalate(response: LLMResponse):
    provider = MagicMock()
    provider.chat_completion = AsyncMock(return_value=response)
    registry = MagicMock()
    registry.get_provider = AsyncMock(return_value=provider)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with patch("llm_shared.tiered_routing.complexity_router.ssot_config") as cfg:
        cfg.llm.claude_escalation_enabled = True
        cfg.llm.claude_escalation_threshold = 0.0
        with patch("llm_shared.provider_registry.get_provider_registry", return_value=registry):
            return await _router().route_with_escalation(request)


async def _verify(response: LLMResponse):
    provider = MagicMock()
    provider.provider_name = "fake"
    provider.chat_completion = AsyncMock(return_value=response)
    with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)):
        return await guard._call_verifier_once("bash", {}, "reason", None)


def _reply() -> LLMResponse:
    return LLMResponse(
        content="REFUTATION_PROBABILITY: 0.3\nRATIONALE: ok", model="m", provider="anthropic", usage=dict(_USAGE)
    )


@pytest.mark.asyncio
async def test_escalation_reports_its_usage_to_the_registered_recorder():
    record, seen = _recorder()
    hook.register_spend_recorder(record)
    response = _reply()

    assert await _escalate(response) is response
    assert [(r, e) for r, e, _ in seen] == [(response, ESCALATION_SPEND_SITE)]


@pytest.mark.asyncio
async def test_verifier_reports_its_usage_to_the_registered_recorder():
    record, seen = _recorder()
    hook.register_spend_recorder(record)
    response = _reply()

    await _verify(response)
    assert [(r, e) for r, e, _ in seen] == [(response, guard.VERIFIER_SPEND_SITE)]
    assert seen[0][2]["purpose"] == "pre_action_verifier"


@pytest.mark.asyncio
async def test_without_a_recorder_both_sites_warn_once_and_still_answer(caplog):
    response = _reply()
    with caplog.at_level(logging.WARNING, logger=hook.logger.name):
        assert await _escalate(response) is response
        assert await _escalate(response) is response
        observation = await _verify(response)

    assert observation.probability == pytest.approx(0.3)
    warned = [r.getMessage() for r in caplog.records if "no spend recorder" in r.getMessage()]
    assert len(warned) == 2


@pytest.mark.asyncio
async def test_a_failing_recorder_loses_neither_answer_and_is_logged(caplog):
    async def broken(response, *, endpoint, metadata):
        raise RuntimeError("tracker down")

    hook.register_spend_recorder(broken)
    response = _reply()
    with caplog.at_level(logging.ERROR, logger=hook.logger.name):
        assert await _escalate(response) is response
        observation = await _verify(response)

    assert observation.probability == pytest.approx(0.3)
    assert len([r for r in caplog.records if "Spend recorder failed" in r.getMessage()]) == 2


def test_startup_registers_the_canonical_recorder():
    """Fails if ``start_background_workers`` stops calling ``wire_llm_spend_recorder`` or it registers something else."""
    from services.llm_usage_recording import record_response_usage

    assert hook.spend_recorder_registered() is False
    bw.wire_llm_spend_recorder()
    assert hook._recorder is record_response_usage


@pytest.mark.asyncio
async def test_the_startup_entry_point_wires_the_recorder(monkeypatch):
    from services.llm_usage_recording import record_response_usage

    for name in ("start_doc_sync_queue_worker", "start_vector_reconciler", "start_telegram_poller"):
        monkeypatch.setattr(bw, name, AsyncMock())
    monkeypatch.setattr(bw, "start_schedule_reconciler", AsyncMock())
    monkeypatch.setattr(bw, "wire_llm_service", MagicMock())

    await bw.start_background_workers(SimpleNamespace(state=SimpleNamespace()))

    assert hook._recorder is record_response_usage
