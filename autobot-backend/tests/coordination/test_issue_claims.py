# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One registry for "who is working on issue N": cross-refusal both ways (#17098).

The session ledger writes through ``issue_claims`` into ``work_claims``; the dev loop claims the
same ``issue:<n>`` scope. Real ``EVAL`` via fakeredis[lua], as in ``test_work_claims.py``.
"""

from __future__ import annotations

import json
import logging

import pytest
import pytest_asyncio

from autobot_shared.coordination import issue_claims, work_claims
from autobot_shared.coordination.work_claims import ClaimConflict, try_acquire

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(work_claims, "get_async_redis_client", _client)
    yield client
    await client.flushall()


@pytest.mark.asyncio
async def test_session_claim_refuses_the_dev_loop_naming_the_session(redis):
    code, body = await issue_claims.claim_issue(17098, "autobot-ai-9a", "de-fork")
    assert code == issue_claims.EXIT_OK and body["granted"]

    from agents.dev_loop_issue_gate import IssueClaimSkipped, run_dev_loop_action

    ran: list[int] = []

    async def action():
        ran.append(1)

    outcome = await run_dev_loop_action(17098, intent="verify ACs", estimated_tokens=1, action=action)
    assert isinstance(outcome, IssueClaimSkipped) and not ran
    assert outcome.holder.holder.agent_id == "autobot-ai-9a"


@pytest.mark.asyncio
async def test_dev_loop_claim_refuses_the_session_naming_the_dev_loop(redis):
    held = await try_acquire("issue:17098", agent_id="autobot-dev-loop", task_id="t1", intent="verify")
    assert not isinstance(held, ClaimConflict)

    code, body = await issue_claims.claim_issue(17098, "autobot-ai-9a")
    assert code == issue_claims.EXIT_HELD and not body["granted"]
    assert body["holder"]["agent_id"] == "autobot-dev-loop" and "autobot-dev-loop" in body["message"]


@pytest.mark.asyncio
async def test_same_owner_renews_and_other_owner_cannot_release(redis):
    assert (await issue_claims.claim_issue(5, "a"))[0] == issue_claims.EXIT_OK
    assert (await issue_claims.claim_issue(5, "a"))[0] == issue_claims.EXIT_OK
    code, body = await issue_claims.release_issue(5, "b")
    assert code == issue_claims.EXIT_HELD and body["holder"]["agent_id"] == "a"
    assert (await issue_claims.who_issue(5))[1]["held"]
    assert (await issue_claims.release_issue(5, "a"))[0] == issue_claims.EXIT_OK
    assert (await issue_claims.who_issue(5))[1] == {"held": False}


@pytest.mark.asyncio
async def test_other_issue_and_other_kinds_are_independent(redis):
    await issue_claims.claim_issue(1, "a")
    assert (await issue_claims.claim_issue(2, "b"))[0] == issue_claims.EXIT_OK
    assert len((await issue_claims.list_issue_claims())[1]["claims"]) == 2


@pytest.mark.parametrize("failure", [ConnectionError("down"), OSError("socket gone")])
def test_unreadable_registry_refuses_and_logs_class_name(monkeypatch, caplog, capsys, failure):
    async def _broken(database: str = "main"):
        raise failure

    monkeypatch.setattr(work_claims, "get_async_redis_client", _broken)
    caplog.set_level(logging.ERROR)
    code = issue_claims.main(["claim", "9", "--owner", "a"])
    out = json.loads(capsys.readouterr().out)
    assert code == issue_claims.EXIT_UNREADABLE and out["granted"] is False
    assert type(failure).__name__ in caplog.text and "down" not in caplog.text


def test_no_client_at_all_is_unreadable_not_empty(monkeypatch, capsys):
    async def _none(database: str = "main"):
        return None

    monkeypatch.setattr(work_claims, "get_async_redis_client", _none)
    assert issue_claims.main(["who", "9"]) == issue_claims.EXIT_UNREADABLE
    assert json.loads(capsys.readouterr().out)["error_class"] == "ClaimUnavailable"


@pytest.mark.asyncio
async def test_an_omitted_ttl_uses_the_session_ttl(redis):
    code, body = await issue_claims.claim_issue(4242, "autobot-ai-a0", "ttl")
    assert code == issue_claims.EXIT_OK
    holder = body["holder"]
    from datetime import datetime

    lifetime = datetime.fromisoformat(holder["expires_at"]) - datetime.fromisoformat(holder["acquired_at"])
    assert round(lifetime.total_seconds()) == issue_claims.SESSION_CLAIM_TTL_S


@pytest.mark.parametrize(
    "argv",
    [
        ["claim", "0", "--owner", "s"],
        ["claim", "-5", "--owner", "s"],
        ["claim", "7", "--owner", "  "],
        ["claim", "7", "--owner", "s", "--ttl-s", "0"],
        ["claim", "7", "--owner", "s", "--ttl-s", "-1"],
        ["claim", "7", "--owner", "s", "--ttl-s", str(issue_claims.TTL_MAX_S + 1)],
        ["release", "0", "--owner", "s"],
    ],
)
def test_an_invalid_request_is_a_usage_error_not_held(argv, capsys):
    """Bad input must never read as "someone holds it" (exit 1): it is EXIT_USAGE (4)."""
    assert issue_claims.main(argv) == issue_claims.EXIT_USAGE
    body = json.loads(capsys.readouterr().out.strip())
    assert body["error"] == "bad-request" and body["granted"] is False
