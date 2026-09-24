# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue number in, one comment out -- in that order (#17090 AC 1 and AC 4)."""

from __future__ import annotations

import pytest

from agents import ac_verification_run
from agents.ac_poster import IssueUnreadable, PostOutcome
from agents.ac_verification_run import verify_and_post
from agents.ac_verifier import Verdict
from llm_shared.decisions import Calibration, DecisionAnswer, DecisionResult

_BODY = "## Acceptance criteria\n- [ ] `decide` is wired\n- [ ] it works on the live install\n"
_FILE = "autobot-backend/agents/ac_verifier.py"


@pytest.fixture
def wired(monkeypatch):
    """Substitute GitHub and the decision seam; record every write."""
    posted: list[tuple[int, str]] = []
    box = {"post": PostOutcome(posted=True, vault_backed=True), "body": _BODY}

    def _fetch(issue_number, *, repo_root=None):
        if isinstance(box["body"], Exception):
            raise box["body"]
        return box["body"], []

    def _post(issue_number, comment, *, repo_root=None):
        posted.append((issue_number, comment))
        return box["post"]

    async def _decide(state, questions, **kwargs):
        return DecisionResult(
            answers={
                "criterion_verdict": DecisionAnswer(
                    question_id="criterion_verdict",
                    value=Verdict.MET.value,
                    probability=0.8,
                    reasoning=f"see {_FILE}:2",
                    calibration=Calibration.SELF_REPORTED,
                )
            },
            backend="stub",
        )

    monkeypatch.setattr(ac_verification_run, "fetch_issue", _fetch)
    monkeypatch.setattr(ac_verification_run, "post_verification", _post)
    monkeypatch.setattr("agents.ac_verifier.decide", _decide)
    return {"posted": posted, "box": box}


def _read(path: str):
    return "one\ntwo has content\n" if path == _FILE else None


def _search(_terms):
    return f"{_FILE}:2: two has content"


@pytest.mark.asyncio
async def test_a_run_posts_exactly_one_comment(wired):
    outcome = await verify_and_post(17090, search=_search, read=_read)

    assert len(wired["posted"]) == 1
    assert wired["posted"][0][0] == 17090
    assert outcome.post.posted is True


@pytest.mark.asyncio
async def test_the_posted_comment_is_the_rendered_verification(wired):
    outcome = await verify_and_post(17090, search=_search, read=_read)

    assert wired["posted"][0][1] == outcome.comment
    assert "```autobot-ac-verification" in outcome.comment


@pytest.mark.asyncio
async def test_a_preview_run_verifies_but_never_writes(wired):
    outcome = await verify_and_post(17090, publish=False, search=_search, read=_read)

    assert wired["posted"] == []
    assert outcome.post.posted is False and "preview" in outcome.post.reason
    assert outcome.verification.counts()["met"] == 1


@pytest.mark.asyncio
async def test_an_unreadable_issue_stops_the_run_rather_than_posting_nothing_found(wired):
    """The distinction the whole feature rests on: nobody read it is not "no criteria"."""
    wired["box"]["body"] = IssueUnreadable("gh exited 1: HTTP 404")

    with pytest.raises(IssueUnreadable):
        await verify_and_post(17090, search=_search, read=_read)

    assert wired["posted"] == []


@pytest.mark.asyncio
async def test_a_refused_post_is_reported_not_swallowed(wired):
    wired["box"]["post"] = PostOutcome(posted=False, reason="no vault-owned credential", vault_backed=False)

    outcome = await verify_and_post(17090, search=_search, read=_read)

    assert outcome.post.posted is False
    assert outcome.as_payload()["post"]["reason"] == "no vault-owned credential"
    assert outcome.verification.counts()["met"] == 1, "the verification still happened and is still reportable"
