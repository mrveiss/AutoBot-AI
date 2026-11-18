# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-action verifier runs on its own small model with a short timeout (#21844)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import pre_action_verifier_guard as guard
from autobot_shared.ssot_config import config


def _provider(name: str, chat) -> MagicMock:
    provider = MagicMock()
    provider.provider_name = name
    provider.chat_completion = chat
    return provider


def test_ollama_provider_gets_the_ssot_verifier_model():
    assert guard._verifier_model_for(_provider("ollama", AsyncMock())) == config.verifier_model


def test_other_providers_keep_their_own_default():
    assert guard._verifier_model_for(_provider("anthropic", AsyncMock())) is None


def test_timeout_is_bounded_below_the_old_thirty_seconds():
    assert guard.VERIFIER_TIMEOUT_S < 30.0


@pytest.mark.asyncio
async def test_request_carries_the_model_and_timeout_fails_open_and_is_logged():
    async def slow(_request):
        await asyncio.sleep(5)

    provider = _provider("ollama", slow)
    with (
        patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)),
        patch.object(guard, "VERIFIER_TIMEOUT_S", 0.01),
        patch.object(guard.logger, "warning") as warn,
    ):
        obs = await guard._call_verifier_once("bash", {}, "why", None)
    assert obs.degradation is guard.VerifierDegradation.TIMEOUT
    assert any("degraded (timeout)" in str(c.args[0]) for c in warn.call_args_list)


@pytest.mark.asyncio
async def test_verifier_request_names_the_verifier_model():
    seen = []

    async def chat(request):
        seen.append(request.model_name)
        raise RuntimeError("stop here")

    with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=_provider("ollama", chat))):
        await guard._call_verifier_once("bash", {}, "why", None)
    assert seen == [config.verifier_model]
