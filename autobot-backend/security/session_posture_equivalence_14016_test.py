# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One validator, two postures: each posture reproduces its old verdict, bar one row (#14016).

``OLD_STRICT`` is what the conversation-file routes' private validator returned; ``OLD_DEFAULT`` is
what the canonical dependency returned. Both columns were read from the code before it was merged
(issue decision table) and are frozen here. ``NEW_DEFAULT`` differs from ``OLD_DEFAULT`` in exactly
the unreadable-owner rows (#14033): they used to claim the session for the caller.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from security.enforcement_mode import ResolvedEnforcementMode
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_ownership import validate_session_ownership
from security.session_posture import SessionPosture
from testkit.canonical_gate import install_canonical_resolver

ALLOW, DENY, ERROR, UNOWNED, UNREADABLE, BROKEN = "allow", "deny", "error", None, "unreadable", "broken"
NONSTR = object()  # a stored owner that is not a name


def _case(
    name,
    *,
    role="user",
    user="alice",
    redis=UNOWNED,
    file=UNOWNED,
    mode="enforced",
    auth=True,
    shared=False,
    org=None,
    old_strict,
    old_default,
    new_default=None,
    new_strict=None,
    ctx_org=None,
):
    return pytest.param(
        dict(
            role=role,
            user=user,
            redis=redis,
            file=file,
            mode=mode,
            auth=auth,
            shared=shared,
            org=org,
            ctx_org=ctx_org,
            old_strict=old_strict,
            old_default=old_default,
            new_default=new_default or old_default,
            new_strict=new_strict or old_strict,
        ),
        id=name,
    )


CASES = [
    _case("owner matches", redis="alice", file="alice", old_strict=ALLOW, old_default=ALLOW),
    _case("stranger, enforced", redis="carol", file="carol", old_strict=DENY, old_default=DENY),
    _case("no role, is owner", role=None, redis="alice", file="alice", old_strict=DENY, old_default=ALLOW),
    _case("global admin, not owner", role="admin", redis="carol", file="carol", old_strict=ALLOW, old_default=DENY),
    _case(
        "org admin of the session's org",
        role="org_admin",
        org="o1",
        ctx_org="o1",
        redis="carol",
        file="carol",
        old_strict=DENY,
        old_default=ALLOW,
    ),
    _case("shared with the user", shared=True, redis="carol", file="carol", old_strict=DENY, old_default=ALLOW),
    _case("stranger, log_only", mode="log_only", redis="carol", file="carol", old_strict=DENY, old_default=ALLOW),
    _case(
        "stranger, enforcement disabled",
        mode="disabled",
        redis="carol",
        file="carol",
        old_strict=DENY,
        old_default=ALLOW,
    ),
    _case("stranger, auth disabled", auth=False, redis="carol", file="carol", old_strict=DENY, old_default=ALLOW),
    _case("expired cache, file names another", file="carol", old_strict=DENY, old_default=DENY),
    _case("unowned everywhere", old_strict=ALLOW, old_default=ALLOW),
    _case("owner unreadable, enforced", file=UNREADABLE, old_strict=DENY, old_default=ALLOW, new_default=DENY),
    _case(
        "owner unreadable, log_only",
        file=UNREADABLE,
        mode="log_only",
        old_strict=DENY,
        old_default=ALLOW,
        new_default=DENY,
    ),
    _case(
        "owner lookup breaks (not the typed error)",
        file=BROKEN,
        old_strict=ERROR,
        old_default=ALLOW,
        new_strict=DENY,
        new_default=DENY,
    ),
    _case(
        "owner lookup breaks, log_only",
        file=BROKEN,
        mode="log_only",
        old_strict=ERROR,
        old_default=ALLOW,
        new_strict=DENY,
        new_default=DENY,
    ),
    _case("owner recorded as a non-name", file=NONSTR, old_strict=DENY, old_default=ALLOW, new_default=DENY),
    _case("owner recorded as empty", file="", old_strict=DENY, old_default=ALLOW),
]


class _Redis:
    def __init__(self, owner, shared, ctx_org):
        self.owner, self.shared, self.ctx_org = owner, shared, ctx_org
        self.set = AsyncMock()
        self.sadd = AsyncMock()
        self.expire = AsyncMock()
        self.hset = AsyncMock()

    async def get(self, key):
        return self.owner

    async def sismember(self, key, member):
        return self.shared

    async def hgetall(self, key):
        return {"org_id": self.ctx_org} if self.ctx_org else {}


def _drive(monkeypatch, c):
    redis = _Redis(c["redis"], c["shared"], c["ctx_org"])
    user = {"username": c["user"], "user_id": c["user"], "role": c["role"], "org_id": c["org"]}
    middleware = SimpleNamespace(
        enable_auth=c["auth"], get_user_from_request=lambda r: user, security_layer=MagicMock()
    )
    manager = MagicMock()
    if c["file"] == UNREADABLE:
        manager.get_session_owner = AsyncMock(side_effect=SessionOwnerUnreadable("s"))
    elif c["file"] is NONSTR:
        manager.get_session_owner = AsyncMock(return_value=12345)
    elif c["file"] == BROKEN:
        manager.get_session_owner = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        manager.get_session_owner = AsyncMock(return_value=c["file"])
    monkeypatch.setattr("security.session_ownership.get_auth_middleware", lambda: middleware)
    install_canonical_resolver(monkeypatch, "security.session_posture.resolve_human_user", middleware)
    monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda r: manager)
    # #20025: these rows are a write on an id with no session; an existing ownerless one is covered there.
    monkeypatch.setattr("chat_history.session_file.session_file_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "security.session_ownership.resolve_enforcement_mode_for_request",
        AsyncMock(return_value=ResolvedEnforcementMode(c["mode"])),
    )
    monkeypatch.setattr("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=redis))
    monkeypatch.setattr("services.feature_flags.get_feature_flags", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr("services.access_control_metrics.get_metrics_service", AsyncMock(return_value=None))
    return redis


async def _verdict(posture, request=None):
    request = request or MagicMock()
    try:
        await validate_session_ownership("session-0001", request, posture=posture)
    except HTTPException as exc:
        return DENY if exc.status_code == 403 else f"http-{exc.status_code}"
    return ALLOW


@pytest.mark.asyncio
@pytest.mark.parametrize("c", CASES)
async def test_strict_posture_equals_the_old_file_route_verdict(monkeypatch, c) -> None:
    _drive(monkeypatch, c)
    request = MagicMock()
    verdict = await _verdict(SessionPosture.STRICT, request)
    assert verdict == c["new_strict"]


@pytest.mark.asyncio
@pytest.mark.parametrize("c", CASES)
async def test_default_posture_equals_the_old_canonical_verdict_except_the_unreadable_rows(monkeypatch, c) -> None:
    _drive(monkeypatch, c)
    assert await _verdict(SessionPosture.DEFAULT) == c["new_default"]


def _is_lookup_failure(case_id: str) -> bool:
    """The rows whose owner lookup fails -- selected by name so a reordered CASES cannot swap them."""
    return "unreadable" in case_id or "lookup breaks" in case_id or "non-name" in case_id


def _row(case_id: str) -> dict:
    """The CASES row named *case_id*, as a fresh dict."""
    return dict(next(p.values[0] for p in CASES if p.id == case_id))


_LOOKUP_FAILURE_IDS = [p.id for p in CASES if _is_lookup_failure(p.id)]


def test_the_only_intended_deltas_are_the_owner_lookup_failures() -> None:
    ids = {p.id: p.values[0] for p in CASES}
    default = sorted(i for i, c in ids.items() if c["old_default"] != c["new_default"])
    strict = sorted(i for i, c in ids.items() if c["old_strict"] != c["new_strict"])
    failures = sorted(i for i in ids if _is_lookup_failure(i))
    assert default == failures
    assert strict == ["owner lookup breaks (not the typed error)", "owner lookup breaks, log_only"]


@pytest.mark.asyncio
@pytest.mark.parametrize("posture", list(SessionPosture))
@pytest.mark.parametrize("case_id", _LOOKUP_FAILURE_IDS)
async def test_an_owner_lookup_failure_is_denied_and_the_session_is_not_claimed(monkeypatch, posture, case_id) -> None:
    case = _row(case_id)
    redis = _drive(monkeypatch, case)
    assert await _verdict(posture) == DENY
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_contrast_a_genuinely_unowned_session_is_still_allowed_under_both(monkeypatch) -> None:
    redis = _drive(monkeypatch, _row("unowned everywhere"))
    assert await _verdict(SessionPosture.STRICT) == ALLOW
    redis.set.assert_not_awaited()  # strict never claims
    assert await _verdict(SessionPosture.DEFAULT) == ALLOW
    redis.set.assert_awaited()  # default claims it for the caller


def test_the_lookup_failure_selection_is_not_vacuous() -> None:
    """Five failure rows today; a filter that matched nothing would make the test above vacuous."""
    assert len(_LOOKUP_FAILURE_IDS) == 5


def test_the_posture_is_not_a_client_controllable_parameter() -> None:
    from fastapi.dependencies.utils import get_dependant

    dependant = get_dependant(path="/chat/sessions/{session_id}", call=validate_session_ownership)
    assert [p.name for p in dependant.query_params] == []
    assert [p.name for p in dependant.path_params] == ["session_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["strict", "STRICT", None, 1, True])
async def test_a_posture_that_is_not_a_session_posture_is_a_type_error_not_default(bad) -> None:
    with pytest.raises(TypeError):
        await validate_session_ownership("session-0001", MagicMock(), posture=bad)
