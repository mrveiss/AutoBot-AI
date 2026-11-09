# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The local-only guard (#20843): allowed, refused with the runner never invoked, and the override."""

import pytest

from eval.live import LiveChatCandidate, LiveRunRecord
from eval.live_guard import LOOPBACK, PRIVATE, PUBLIC, RemoteProviderRefused, assert_local_only, endpoint_class
from eval.runner import RecordingUnusable
from eval.store import GoldenTrajectory

_ENV = "AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER"


def _resolver(url):
    async def resolve(model):
        return url

    return resolve


def _golden():
    return GoldenTrajectory("g", "knowledge_qa", {"prompt": "p"}, [], 0.9)


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://127.0.0.1:11434/api/generate", LOOPBACK),
        ("http://localhost:11434", LOOPBACK),
        ("http://[::1]:11434", LOOPBACK),
        ("http://10.1.2.3:11434", PRIVATE),
        ("http://192.168.0.5:11434", PRIVATE),
        ("https://203.0.113.9:443", PUBLIC),
    ],
)
async def test_endpoint_class_never_needs_the_host_string(url, expected):
    assert await endpoint_class(url) == expected


@pytest.mark.asyncio
async def test_a_local_provider_on_loopback_is_allowed_and_stamped():
    found = await assert_local_only(["m1"], "ollama", _resolver("http://127.0.0.1:11434"))
    assert found["m1"].local_only is True and found["m1"].endpoint_class == LOOPBACK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,url", [("openai", "http://127.0.0.1:11434"), ("ollama", "https://203.0.113.9:11434")]
)
async def test_a_hosted_provider_or_a_public_endpoint_is_refused_without_naming_the_host(provider, url):
    with pytest.raises(RemoteProviderRefused) as refused:
        await assert_local_only(["m1"], provider, _resolver(url))
    assert "203.0.113.9" not in str(refused.value)


@pytest.mark.asyncio
async def test_a_refused_run_never_invokes_the_turn_runner():
    calls = []

    async def turn(golden, model, workspace):
        calls.append(model)
        return LiveRunRecord()

    candidate = LiveChatCandidate(["m1"], "openai", turn_runner=turn, resolve_endpoint=_resolver("http://127.0.0.1:1"))
    with pytest.raises(RemoteProviderRefused):
        await candidate.prepare()
    with pytest.raises(RuntimeError, match="guard has not run"):
        await candidate.runner_for("m1")(_golden())
    assert calls == []


@pytest.mark.asyncio
async def test_the_override_runs_it_and_stamps_local_only_false(monkeypatch):
    monkeypatch.setenv(_ENV, "true")
    found = await assert_local_only(["m1"], "openai", _resolver("https://203.0.113.9"))
    assert found["m1"].local_only is False and found["m1"].endpoint_class == PUBLIC


@pytest.mark.asyncio
async def test_the_explicit_allow_flag_also_overrides():
    found = await assert_local_only(["m1"], "openai", _resolver("https://203.0.113.9"), allow_remote=True)
    assert found["m1"].local_only is False


@pytest.mark.asyncio
async def test_a_turn_that_raises_is_not_run_not_a_model_failure():
    async def turn(golden, model, workspace):
        raise ConnectionError("down")

    candidate = LiveChatCandidate(["m1"], "ollama", turn_runner=turn, resolve_endpoint=_resolver("http://127.0.0.1:1"))
    await candidate.prepare()
    with pytest.raises(RecordingUnusable):
        await candidate.runner_for("m1")(_golden())
