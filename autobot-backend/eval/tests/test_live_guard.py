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


async def _kb():
    return "populated"


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
        ("http://[fe80::1%25eth0]:11434", PRIVATE),
        ("http://[::ffff:10.1.2.3]:11434", PRIVATE),
        ("https://8.8.8.8:443", PUBLIC),
        ("http://0.0.0.0:11434", PUBLIC),
    ],
)
async def test_endpoint_class_never_needs_the_host_string(url, expected):
    assert await endpoint_class(url) == expected


def _answers(monkeypatch, *addresses):
    import ipaddress

    async def resolve(host, timeout):
        return [ipaddress.ip_address(a) for a in addresses]

    monkeypatch.setattr("autobot_shared.url_safety._resolve_addresses", resolve)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answers,expected",
    [
        (["10.1.2.3"], PRIVATE),
        (["127.0.0.1", "::1"], LOOPBACK),
        (["10.1.2.3", "8.8.8.8"], PUBLIC),  # one public answer makes the name public
        ([], PUBLIC),  # does not resolve: fail closed
    ],
)
async def test_a_hostname_is_classified_by_every_address_it_resolves_to(monkeypatch, answers, expected):
    _answers(monkeypatch, *answers)
    assert await endpoint_class("http://some-name.example:11434") == expected


@pytest.mark.asyncio
async def test_an_allowlisted_name_that_resolves_public_is_not_private(monkeypatch):
    """Membership in the internal-origin allowlist no longer decides locality: the addresses do."""
    _answers(monkeypatch, "8.8.8.8")

    async def listed(url):
        return True

    monkeypatch.setattr("autobot_shared.egress_allowlist.is_internal_origin", listed)
    assert await endpoint_class("http://slm-node.example:11434") == PUBLIC


@pytest.mark.asyncio
async def test_a_local_provider_on_loopback_is_allowed_and_stamped():
    found = await assert_local_only(["m1"], "ollama", _resolver("http://127.0.0.1:11434"))
    assert found["m1"].local_only is True and found["m1"].endpoint_class == LOOPBACK


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,url", [("openai", "http://127.0.0.1:11434"), ("ollama", "https://8.8.8.8:11434")])
async def test_a_hosted_provider_or_a_public_endpoint_is_refused_without_naming_the_host(provider, url):
    with pytest.raises(RemoteProviderRefused) as refused:
        await assert_local_only(["m1"], provider, _resolver(url))
    assert "8.8.8.8" not in str(refused.value)


@pytest.mark.asyncio
async def test_a_refused_run_never_invokes_the_turn_runner():
    calls = []

    async def turn(golden, model, workspace):
        calls.append(model)
        return LiveRunRecord()

    candidate = LiveChatCandidate(
        ["m1"],
        "openai",
        turn_runner=turn,
        resolve_endpoint=_resolver("http://127.0.0.1:1"),
        resolve_provider=lambda: "openai",
    )
    with pytest.raises(RemoteProviderRefused):
        await candidate.prepare()
    with pytest.raises(RuntimeError, match="guard has not run"):
        await candidate.runner_for("m1")(_golden())
    assert calls == []


@pytest.mark.asyncio
async def test_the_override_runs_it_and_stamps_local_only_false(monkeypatch):
    monkeypatch.setenv(_ENV, "true")
    found = await assert_local_only(["m1"], "openai", _resolver("https://8.8.8.8"))
    assert found["m1"].local_only is False and found["m1"].endpoint_class == PUBLIC


@pytest.mark.asyncio
async def test_the_explicit_allow_flag_also_overrides():
    found = await assert_local_only(["m1"], "openai", _resolver("https://8.8.8.8"), allow_remote=True)
    assert found["m1"].local_only is False


@pytest.mark.asyncio
async def test_a_turn_that_raises_is_not_run_not_a_model_failure():
    async def turn(golden, model, workspace):
        raise ConnectionError("down")

    candidate = LiveChatCandidate(
        ["m1"],
        "ollama",
        turn_runner=turn,
        resolve_endpoint=_resolver("http://127.0.0.1:1"),
        resolve_provider=lambda: "ollama",
        probe_kb=_kb,
    )
    await candidate.prepare()
    with pytest.raises(RecordingUnusable):
        await candidate.runner_for("m1")(_golden())


@pytest.mark.asyncio
async def test_the_provider_checked_is_the_one_chat_resolves_not_the_typed_label():
    """`--provider ollama` while chat resolves a hosted provider must not pass for a local run."""
    candidate = LiveChatCandidate(
        ["m1"], "ollama", resolve_endpoint=_resolver("http://127.0.0.1:1"), resolve_provider=lambda: "openai"
    )
    with pytest.raises(RemoteProviderRefused, match="chat resolves"):
        await candidate.prepare()


@pytest.mark.asyncio
async def test_an_omitted_label_takes_chats_resolution_and_is_judged_by_it():
    candidate = LiveChatCandidate(
        ["m1"], "", resolve_endpoint=_resolver("http://127.0.0.1:1"), resolve_provider=lambda: "openai"
    )
    with pytest.raises(RemoteProviderRefused):
        await candidate.prepare()  # the resolved hosted provider is refused, whatever the label said


@pytest.mark.asyncio
async def test_a_non_local_fallback_chain_refuses_the_run_and_a_local_one_does_not(monkeypatch):
    def candidate():
        return LiveChatCandidate(
            ["m1"],
            "ollama",
            resolve_endpoint=_resolver("http://127.0.0.1:1"),
            resolve_provider=lambda: "ollama",
            probe_kb=_kb,
        )

    from llm_shared import fallback_chain

    def active_manager():  # the process-wide manager reads the env once; a test needs it read again
        monkeypatch.setattr(fallback_chain, "get_fallback_chain_manager", fallback_chain.FallbackChainManager)

    monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_M1", "ollama:backup")
    active_manager()
    await candidate().prepare()  # a local-to-local hop is fine
    monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_M1", "ollama:backup,openai:gpt-x")
    with pytest.raises(RemoteProviderRefused, match="fail over"):
        await candidate().prepare()
    monkeypatch.setenv(_ENV, "true")
    await candidate().prepare()  # the explicit override still works


@pytest.mark.asyncio
async def test_the_active_fallback_manager_is_the_one_inspected(monkeypatch):
    from llm_shared.fallback_chain import FallbackChain, get_fallback_chain_manager

    monkeypatch.delenv(_ENV, raising=False)
    manager = get_fallback_chain_manager()
    chain = FallbackChain(
        "held-by-active-manager",
        ["hosted-model"],
        fallback_providers=["openai"],
        operator_configured=True,
    )
    manager.register_chain(chain)
    try:
        candidate = LiveChatCandidate(
            ["m1"],
            "ollama",
            resolve_endpoint=_resolver("http://127.0.0.1:1"),
            resolve_provider=lambda: "ollama",
            probe_kb=_kb,
        )
        with pytest.raises(RemoteProviderRefused, match="held-by-active-manager"):
            await candidate.prepare()
        monkeypatch.setenv(_ENV, "true")
        await candidate.prepare()
        assert candidate.remote_chains == ["held-by-active-manager"]  # the run-level pin will say so
    finally:
        manager._chains.pop("held-by-active-manager", None)
