# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Correlating a delivered approval with its reply (#14068).

Every test here is about a *rejection* path as much as an acceptance one. The
failure that matters is not "a valid reply was missed" — it is "something was
approved that the operator did not approve", so the fail-closed direction is
asserted case by case rather than assumed from the happy path.
"""

from unittest.mock import AsyncMock

import pytest

from services.remote_approval import (
    DeliveredApproval,
    RemoteApprovalStore,
    embed_token,
    extract_token,
    parse_decision,
    resolve_from_reply,
)


class _Store(RemoteApprovalStore):
    """A store with a known content, so tests never touch Redis."""

    def __init__(self, delivery=None):
        self._delivery = delivery

    async def get_delivery(self, approval_id):
        if self._delivery and self._delivery.approval_id == approval_id:
            return self._delivery
        return None


_DELIVERY = DeliveredApproval(approval_id="a1b2c3", platform="slack", channel_id="C42")


class TestToken:
    def test_a_token_round_trips(self):
        assert extract_token(embed_token("Approve deploy?", "a1b2c3")) == "a1b2c3"

    def test_the_body_survives_embedding(self):
        assert "Approve deploy?" in embed_token("Approve deploy?", "a1b2c3")

    def test_an_id_that_cannot_be_tokenised_is_refused_loudly(self):
        """Silently emitting an uncorrelatable message is the worse failure:
        a human would answer a question whose answer goes nowhere."""
        for bad in ("", "has space", "has]bracket", "x" * 100, "[ab:nested]"):
            with pytest.raises(ValueError):
                embed_token("body", bad)

    def test_text_without_a_token_yields_none(self):
        assert extract_token("looks fine to me") is None

    def test_two_tokens_yield_none(self):
        """A reply quoting two approvals names no single decision."""
        two = embed_token(embed_token("body", "aaa"), "bbb")
        assert extract_token(two) is None

    def test_a_non_string_yields_none(self):
        assert extract_token(None) is None
        assert extract_token(12345) is None


class TestDecision:
    @pytest.mark.parametrize("text", ["approve", "Approved", "yes", "LGTM", "👍", "✅ go ahead"])
    def test_approval_signals(self, text):
        assert parse_decision(text) is True

    @pytest.mark.parametrize("text", ["deny", "No", "reject", "stop", "👎", "❌ not this one"])
    def test_denial_signals(self, text):
        assert parse_decision(text) is False

    @pytest.mark.parametrize("text", ["", "   ", "what does this do?", "maybe later", None])
    def test_no_decision_is_none_not_false(self, text):
        """None and False are different outcomes: False *denies*, None leaves the
        approval pending. Collapsing them would let a question deny a request."""
        assert parse_decision(text) is None

    def test_a_contradictory_reply_resolves_nothing(self):
        """'no, do not approve' contains the approve word."""
        assert parse_decision("no, do not approve this") is None
        assert parse_decision("👍👎") is None

    def test_a_word_inside_another_word_does_not_count(self):
        """'okay' is a decision; 'okaying' should not be matched by substring."""
        assert parse_decision("I am not okaying anything without review") is None


class TestResolveFromReply:
    @pytest.mark.asyncio
    async def test_a_well_formed_reply_resolves(self):
        reply = embed_token("👍", "a1b2c3")
        got = await resolve_from_reply(reply, platform="slack", channel_id="C42", store=_Store(_DELIVERY))
        assert got is not None and got.approval_id == "a1b2c3" and got.approved is True

    @pytest.mark.asyncio
    async def test_a_denial_resolves_as_a_denial(self):
        reply = embed_token("👎", "a1b2c3")
        got = await resolve_from_reply(reply, platform="slack", channel_id="C42", store=_Store(_DELIVERY))
        assert got is not None and got.approved is False

    @pytest.mark.asyncio
    async def test_an_unknown_token_resolves_nothing(self):
        reply = embed_token("👍", "neversent")
        assert await resolve_from_reply(reply, platform="slack", channel_id="C42", store=_Store(_DELIVERY)) is None

    @pytest.mark.asyncio
    async def test_a_reply_with_no_decision_resolves_nothing(self):
        reply = embed_token("what would this do?", "a1b2c3")
        assert await resolve_from_reply(reply, platform="slack", channel_id="C42", store=_Store(_DELIVERY)) is None

    @pytest.mark.asyncio
    async def test_a_reply_on_the_wrong_channel_resolves_nothing(self):
        """The reply must return where the question was asked.

        Without this, anyone able to post the token in any channel the bot reads
        could answer on the operator's behalf.
        """
        reply = embed_token("👍", "a1b2c3")
        assert await resolve_from_reply(reply, platform="slack", channel_id="OTHER", store=_Store(_DELIVERY)) is None

    @pytest.mark.asyncio
    async def test_a_reply_on_the_wrong_platform_resolves_nothing(self):
        reply = embed_token("👍", "a1b2c3")
        assert await resolve_from_reply(reply, platform="discord", channel_id="C42", store=_Store(_DELIVERY)) is None

    @pytest.mark.asyncio
    async def test_an_unavailable_store_resolves_nothing(self):
        """Redis down must not approve by default."""
        reply = embed_token("👍", "a1b2c3")
        assert await resolve_from_reply(reply, platform="slack", channel_id="C42", store=_Store(None)) is None


class TestStoreDegradesWithoutRedis:
    @pytest.mark.asyncio
    async def test_recording_without_redis_reports_failure_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr("services.remote_approval.get_async_redis_client", AsyncMock(return_value=None))
        assert await RemoteApprovalStore().record_delivery(_DELIVERY) is False

    @pytest.mark.asyncio
    async def test_reading_without_redis_returns_none(self, monkeypatch):
        monkeypatch.setattr("services.remote_approval.get_async_redis_client", AsyncMock(return_value=None))
        assert await RemoteApprovalStore().get_delivery("a1b2c3") is None

    @pytest.mark.asyncio
    async def test_a_partial_record_is_not_a_delivery(self, monkeypatch):
        """A hash missing a field must not resolve to a half-known delivery."""
        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={"platform": "slack"})
        monkeypatch.setattr("services.remote_approval.get_async_redis_client", AsyncMock(return_value=redis))
        assert await RemoteApprovalStore().get_delivery("a1b2c3") is None

    @pytest.mark.asyncio
    async def test_byte_encoded_fields_are_read(self, monkeypatch):
        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={b"platform": b"slack", b"channel_id": b"C42"})
        monkeypatch.setattr("services.remote_approval.get_async_redis_client", AsyncMock(return_value=redis))
        got = await RemoteApprovalStore().get_delivery("a1b2c3")
        assert got is not None and got.platform == "slack"
