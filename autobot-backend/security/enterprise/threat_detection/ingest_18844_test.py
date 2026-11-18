# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent tool call reported by the AI-line gate is not an API request, and never a session-id "user" (#18844).

Root cause: ``enforce_line`` audited every allowed tool call with the chat session id as ``user_id``, and the
ingest read any unrecognised bus action as ``api_request``; ``APIAbuseAnalyzer`` then scored each first-seen
"endpoint" for that pseudo-user as ``unusual_endpoint_access`` and rate-limited it.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from security.enterprise.threat_detection.analyzers.api_abuse import APIAbuseAnalyzer
from security.enterprise.threat_detection.ingest import audit_event_to_engine_event, engine_action
from security.enterprise.threat_detection.models import SecurityEvent
from services import ai_line_enforcement as enforcement
from services.ai_line_enforcement import LineVerdict, Outcome


@pytest.mark.parametrize("stored", ["ai_line.run", "ai_line.hold", "ai_line.refuse"])
def test_ai_line_reports_are_not_api_requests(stored: str) -> None:
    assert engine_action(stored) == "agent_action"
    payload = {"id": "e", "action": stored, "actor_id": "alice", "occurred_at": time.time(), "outcome": "success"}
    assert not SecurityEvent(raw_event=audit_event_to_engine_event(payload)).is_api_request()


@pytest.mark.asyncio
async def test_the_api_abuse_analyzer_ignores_an_agent_action_but_still_sees_a_real_request() -> None:
    def event(action: str) -> SecurityEvent:
        payload = {"id": "e", "action": action, "actor_id": "u", "occurred_at": time.time(), "outcome": "success"}
        return SecurityEvent(raw_event=audit_event_to_engine_event(payload))

    ctx = type("Ctx", (), {"config": {"thresholds": {"api_rate_limit_per_minute": 0}}})()
    ctx.count_recent_api_requests = lambda *_: 5
    ctx.get_user_profile = lambda _u: None
    ctx.count_recent_actions = lambda *_: 0
    analyzer = APIAbuseAnalyzer.__new__(APIAbuseAnalyzer)

    assert await analyzer.analyze(event("ai_line.run"), ctx) is None
    assert await analyzer.analyze(event("knowledge.search"), ctx) is not None  # real API abuse stays detected


@pytest.mark.asyncio
@pytest.mark.parametrize(("user", "expected"), [("alice", "alice"), (None, enforcement.REQUESTER_PREFIX)])
async def test_the_report_names_the_user_not_the_session(user, expected) -> None:
    resolution = type("R", (), {"key": "k", "source": "s"})()
    verdict = LineVerdict(Outcome.RUN, resolution)
    with patch.object(enforcement, "audit_log", AsyncMock()) as audit:
        await enforcement._report(verdict, "chat-session-1", "chat_tool", user_id=user)

    assert audit.await_args.kwargs["user_id"] == expected
    assert audit.await_args.kwargs["session_id"] == "chat-session-1"


def _agent_event(user: str = "alice") -> SecurityEvent:
    payload = {"id": "e", "action": "ai_line.run", "actor_id": user, "occurred_at": time.time(), "outcome": "success"}
    return SecurityEvent(raw_event=audit_event_to_engine_event(payload))


def _ctx(recent: int, thresholds: dict | None = None):
    ctx = type("Ctx", (), {"config": {"thresholds": thresholds or {}}})()
    ctx.count_recent_actions = lambda *_: recent
    return ctx


@pytest.mark.asyncio
async def test_a_flood_of_agent_actions_for_one_user_is_a_threat_with_the_configured_limit() -> None:
    analyzer = APIAbuseAnalyzer.__new__(APIAbuseAnalyzer)
    threat = await analyzer.analyze(_agent_event(), _ctx(31, {"agent_action_rate_limit_per_minute": 30}))
    assert threat is not None and threat.details["abuse_patterns"] == ["agent_action_rate_exceeded"]
    assert threat.details["rate_limit"] == 30 and threat.user_id == "alice"
    assert await analyzer.analyze(_agent_event(), _ctx(30, {"agent_action_rate_limit_per_minute": 30})) is None


@pytest.mark.asyncio
async def test_the_default_limit_is_the_env_backed_constant_not_a_literal() -> None:
    from security.enterprise.threat_detection.analyzers.api_abuse import AGENT_ACTION_RATE_LIMIT_PER_MINUTE as LIMIT

    analyzer = APIAbuseAnalyzer.__new__(APIAbuseAnalyzer)
    assert await analyzer.analyze(_agent_event(), _ctx(LIMIT)) is None
    assert await analyzer.analyze(_agent_event(), _ctx(LIMIT + 1)) is not None


def test_the_history_counts_only_this_users_agent_actions_in_the_window() -> None:
    from collections import deque

    from autobot_shared.time_utils import utc_timestamp
    from security.enterprise.threat_detection.models import EventHistory

    now = utc_timestamp()
    rows = [{"timestamp": now, "user_id": u, "action": a} for u, a in [("alice", "agent_action")] * 3]
    rows += [
        {"timestamp": now, "user_id": "bob", "action": "agent_action"},
        {"timestamp": now, "user_id": "alice", "action": "api_request"},
    ]
    assert EventHistory(events=deque(rows)).count_recent_actions("alice", "agent_action", 1) == 3
