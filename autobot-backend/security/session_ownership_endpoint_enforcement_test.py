# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wire a per-endpoint enforcement override into the authorization decision (#15086).

`get_endpoint_enforcement` (`services/feature_flags.py`) read its key correctly
-- it was never part of the `_redis` bug fixed for #15089. Its defect was
narrower and worse: nothing called it. `set_endpoint_enforcement` and
`remove_endpoint_enforcement` (`api/feature_flags.py`) accept and audit-log a
per-endpoint override; `SessionOwnershipValidator._get_enforcement_mode` read
only the global mode. An operator could set an endpoint to `enforced`, see it
accepted, audit-logged, and read back -- and it never reached an authorization
decision. A control that reports being on while being off.

These tests drive `validate_ownership` end-to-end (not just the getter) so a
correct resolver whose *consumer* still ignores it would still be caught here,
one level up -- the same shape #14010's `TestTheDegradedModeStillRunsAndRecordsTheCheck`
pins for the global-mode case.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from security.session_ownership import SessionOwnershipValidator
from services.feature_flags import EnforcementMode

BACKEND_ROOT = pathlib.Path(__file__).parent.parent

SKIP_DIR_PARTS = {
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "archive",
    "migrations",
}


def _validator(global_mode: EnforcementMode, endpoint_override: EnforcementMode | None):
    flags = MagicMock()
    flags.get_enforcement_mode = AsyncMock(return_value=global_mode)
    flags.get_endpoint_enforcement = AsyncMock(return_value=endpoint_override)

    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = MagicMock()
    validator.feature_flags = flags
    validator.metrics_service = None
    validator.get_session_owner = AsyncMock(return_value="alice")
    validator._is_org_admin_access = AsyncMock(return_value=False)
    validator._get_authenticated_user = MagicMock(
        return_value={"username": "bob", "user_id": "bob-id", "auth_disabled": False}
    )
    return validator


def _request(route_path: str = "/api/chat/sessions/{session_id}"):
    request = MagicMock()
    request.scope = {"route": MagicMock(path=route_path)}
    request.url.path = "/api/chat/sessions/abc123"
    request.client.host = "198.51.100.7"
    return request


def _auth_enabled():
    auth = MagicMock()
    auth.enable_auth = True
    return patch("security.session_ownership.get_auth_middleware", return_value=auth)


class TestAPerEndpointOverrideChangesTheDecision:
    """The defect: a written override that never reached authorization."""

    @pytest.mark.asyncio
    async def test_enforced_override_refuses_a_non_owner_the_global_mode_alone_would_allow(self):
        """The exact scenario in #15086: global is `disabled` (would allow
        everyone through the `_resolve_fast_paths` short-circuit), but this
        endpoint has an `enforced` override. The non-owner must be refused --
        asserting the raised 403, not merely that the getter was called.
        """
        validator = _validator(EnforcementMode.DISABLED, EnforcementMode.ENFORCED)

        with _auth_enabled():
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_ownership("sess-1234abcd", _request())

        assert exc_info.value.status_code == 403
        validator.get_session_owner.assert_awaited()

    @pytest.mark.asyncio
    async def test_the_contrast_global_disabled_alone_allows(self):
        """Same global mode, no override -- the pre-#15086 behaviour, so the
        test above cannot be passing because `disabled` always refuses."""
        validator = _validator(EnforcementMode.DISABLED, None)

        with _auth_enabled():
            result = await validator.validate_ownership("sess-1234abcd", _request())

        assert result["authorized"] is True
        assert result["reason"] == "enforcement_disabled"
        assert validator.get_session_owner.await_count == 0, "disabled must still skip the ownership lookup"


class TestAnEndpointWithNoOverrideIsUnchanged:
    """The half that must NOT move: no override stored anywhere for this route."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "global_mode,expected_reason",
        [
            (EnforcementMode.DISABLED, "enforcement_disabled"),
            (EnforcementMode.LOG_ONLY, "log_only_mode"),
        ],
    )
    async def test_behaviour_matches_the_pre_wiring_outcome(self, global_mode, expected_reason):
        validator = _validator(global_mode, None)

        with _auth_enabled():
            result = await validator.validate_ownership("sess-1234abcd", _request())

        assert result["authorized"] is True
        assert result["reason"] == expected_reason

    @pytest.mark.asyncio
    async def test_enforced_global_with_no_override_still_refuses(self):
        validator = _validator(EnforcementMode.ENFORCED, None)

        with _auth_enabled():
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_ownership("sess-1234abcd", _request())

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_request_and_a_no_override_request_resolve_identically(self):
        """A caller with no request object (existing call sites, if any) and one
        whose route has no stored override must reach the same mode -- looking
        an override up must never itself be a behaviour change."""
        validator = _validator(EnforcementMode.LOG_ONLY, None)

        without_request = await validator._get_enforcement_mode()
        with_request = await validator._get_enforcement_mode_for_request(_request())

        assert without_request.mode == with_request.mode == "log_only"
        assert without_request.degraded is with_request.degraded is False


class TestPrecedenceInTheDisagreementCase:
    """Stricter side wins -- pinned against the specific case #15086 calls out:
    an endpoint override must not loosen enforcement below the global mode.
    """

    @pytest.mark.asyncio
    async def test_a_disabled_override_cannot_exempt_an_endpoint_the_global_mode_enforces(self):
        """#15086's own words: 'Setting an endpoint to disabled while the global
        mode is enforced reads as an exemption. It is not.' This is that case,
        driven through the real decision path.
        """
        validator = _validator(EnforcementMode.ENFORCED, EnforcementMode.DISABLED)

        with _auth_enabled():
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_ownership("sess-1234abcd", _request())

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_enforced_override_does_win_over_a_log_only_global(self):
        """The tightening direction, contrasted against the loosening one above
        so the precedence rule cannot be mistaken for "override always wins" by
        accident -- both directions must be exercised for it to be pinned.
        """
        validator = _validator(EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED)

        with _auth_enabled():
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_ownership("sess-1234abcd", _request())

        assert exc_info.value.status_code == 403


class TestAnUnreadableOverrideDegradesNoMorePermissivelyThanGlobal:
    @pytest.mark.asyncio
    async def test_a_failing_override_lookup_falls_back_to_the_global_mode(self):
        validator = _validator(EnforcementMode.ENFORCED, None)
        validator.feature_flags.get_endpoint_enforcement = AsyncMock(side_effect=RuntimeError("redis down"))

        with _auth_enabled():
            with pytest.raises(HTTPException) as exc_info:
                await validator.validate_ownership("sess-1234abcd", _request())

        assert exc_info.value.status_code == 403, "an unreadable override must not weaken an enforced global mode"


#: Floor on the swept population, so a collapsed sweep fails by name rather
#: than reporting an absence of references (#14484).
MIN_SWEPT_FILES = 500


def _swept_files():
    """Backend Python files the reference sweep may read.

    #14484: the skip set is tested against the path **relative to the scan
    root**. Testing ``set(path.parts)`` on the absolute path asks whether the
    checkout itself sits under a directory named ``archive``/``venv``/... as
    well as whether the file does, so the sweep's reach depended on the
    directory the tree was cloned into rather than on the tree.
    """
    for path in BACKEND_ROOT.rglob("*.py"):
        if SKIP_DIR_PARTS & set(path.relative_to(BACKEND_ROOT).parts):
            continue
        yield path


def _assert_population() -> None:
    """Raise unless the sweep reached the backend tree it claims to scan."""
    swept = sum(1 for _ in _swept_files())
    assert swept >= MIN_SWEPT_FILES, (
        f"the reference sweep reached only {swept} files under {BACKEND_ROOT} "
        f"(floor {MIN_SWEPT_FILES}). FIX THE SWEEP -- a sweep that reads nothing "
        "finds no references, which reads exactly like a genuinely unused getter."
    )


def test_the_reference_sweep_reached_the_backend_tree():
    """Population floor, evaluated before the reference assertion below."""
    _assert_population()


def _endpoint_enforcement_references() -> tuple[str, ...]:
    """``path:line`` for every textual reference to ``get_endpoint_enforcement``
    across the backend -- the definition, its callers, and its tests alike.
    """
    hits: list[str] = []
    for path in _swept_files():
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "get_endpoint_enforcement" not in source:
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "get_endpoint_enforcement" in line:
                hits.append(f"{path.relative_to(BACKEND_ROOT).as_posix()}:{lineno}")
    return tuple(hits)


_GETTER = "get_endpoint_enforcement"


def _call_lines(source: str, name: str = _GETTER) -> list[int]:
    """Line numbers where *name* is **called** in *source*, by AST.

    #15510: the sweep below used to count any line containing the name, so a
    prose mention in a non-test module's docstring satisfied "has a non-test
    caller" on its own -- removing the single real call site left this guard
    green until the docstring mention was removed too. A call is a call node;
    text is not evidence of one.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if called == name:
            lines.append(node.lineno)
    return sorted(lines)


def _endpoint_enforcement_call_sites() -> tuple[str, ...]:
    """``path:line`` for every AST call of the getter across the backend."""
    hits: list[str] = []
    for path in _swept_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _GETTER not in source:  # cheap prefilter; the AST decides
            continue
        for lineno in _call_lines(source):
            hits.append(f"{path.relative_to(BACKEND_ROOT).as_posix()}:{lineno}")
    return tuple(hits)


def test_a_prose_mention_is_not_counted_as_a_call(tmp_path):
    """The #15510 probe: text mentioning the getter is not a call site, and the
    real call is. Fails if the detector goes back to string matching.
    """
    prose = '"""A docstring naming get_endpoint_enforcement in prose."""\n'
    prose += "# get_endpoint_enforcement in a comment too\n"
    assert _call_lines(prose) == [], "a prose mention was counted as a call"

    real = "async def f(req):\n    return await get_endpoint_enforcement(req)\n"
    assert _call_lines(real) == [2], "the real call site was not detected"

    attribute = "async def f(m, req):\n    return await m.get_endpoint_enforcement(req)\n"
    assert _call_lines(attribute) == [2], "an attribute call was not detected"


def test_get_endpoint_enforcement_has_a_non_test_caller():
    """The regression this issue exists to prevent: a getter that only its own
    definition (and, now, its tests) ever mention is write-only again.
    """
    _assert_population()
    references = _endpoint_enforcement_references()

    # Non-vacuity: the sweep must at least find the definition it is named
    # after, or it swept nothing and every assertion below passes for free.
    assert references, (
        "the sweep found zero references to get_endpoint_enforcement -- FIX THE SWEEP, " "the sweep itself is broken"
    )

    # #15510: callers are resolved as AST call nodes. A definition is not a
    # call, so it drops out without a separate declaration check, and a prose
    # mention never counted in the first place.
    call_sites = _endpoint_enforcement_call_sites()
    non_test_refs = [ref for ref in call_sites if "_test.py" not in ref and "/tests/" not in ref]

    assert non_test_refs, (
        "get_endpoint_enforcement has no non-test caller -- it is write-only "
        f"again (#15086). All call sites: {sorted(call_sites)}. All textual "
        f"references: {sorted(references)}"
    )
