# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The duplicate scan refuses an unresolvable source instead of scanning AutoBot (#17982).

`duplicates.py` carried a private copy of the source-resolution block that
`shared.resolve_source_root` was extracted for (#2760, which converted
report.py and stats.py and missed this one). The copy swallowed every failure
into `logger.debug` and carried on against AutoBot's own tree, so three
distinct states -- source absent, empty clone_path, lookup raised -- all
produced a COMPLETED scan of the wrong repository, cached under the caller's
source_id. That is why the detector "returned nothing" for the registered
AutoBot source and reported it as success.

Asserted on the REFUSAL, not on the presence of a call: a test that only
checked `resolve_scan_root` was invoked would pass against a version that
called it and then fell back anyway, which is exactly what the old code did.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from api.codebase_analytics.endpoints.shared import UnresolvedSourceError, resolve_scan_root
from api.codebase_analytics.source_storage import RegistryUnavailable


@pytest.mark.asyncio
async def test_a_named_source_that_is_absent_refuses():
    """`strict=True` is the whole point: a scan has no user watching it."""
    with patch("api.codebase_analytics.source_storage.get_source", return_value=None):
        with pytest.raises(UnresolvedSourceError):
            await resolve_scan_root("ghost-source", strict=True)


@pytest.mark.asyncio
async def test_a_lookup_that_raises_is_a_fault_not_an_unknown_id():
    """The state the old code was most wrong about, and the one it hid.

    A raising `get_source` went to `logger.debug` and returned None, so a
    registry fault and an unknown id were the same observable: the refusal said
    "does not resolve to a code source" for a lookup that had THROWN. It is
    `RegistryUnavailable` now -- neither a substitution of AutoBot's tree nor a
    claim that the id is unknown.
    """
    with patch("api.codebase_analytics.source_storage.get_source", side_effect=RuntimeError("db down")):
        with pytest.raises(RegistryUnavailable) as caught:
            await resolve_scan_root("some-source", strict=True)
    assert not isinstance(caught.value, UnresolvedSourceError)
    assert isinstance(caught.value.__cause__, RuntimeError), "the real cause must stay on the chain"


@pytest.mark.asyncio
async def test_an_unreachable_registry_propagates_instead_of_reading_as_no_such_source():
    """`get_source` returned None when it could not build its Redis client (#17982)."""
    from api.codebase_analytics import source_storage

    with patch.object(source_storage, "get_async_redis_client", return_value=None):
        with pytest.raises(RegistryUnavailable):
            await source_storage.get_source("any-id")
        with pytest.raises(RegistryUnavailable):
            await source_storage.get_default_source_id()


@pytest.mark.asyncio
async def test_naming_no_source_still_falls_back():
    """The contrast, and the reason `strict` is not simply "always raise".

    "You did not say which project" and "you named one that is not there" are
    different questions, and only the second is a mistake. Without this, the
    fix above could be a blanket raise and both tests would still pass.
    """
    with patch("api.codebase_analytics.source_storage.get_default_source_id", return_value=None):
        assert await resolve_scan_root(None, strict=bool(None)) is not None


@pytest.mark.asyncio
async def test_an_unresolvable_DEFAULT_source_still_falls_back(monkeypatch):
    """The case the test above could not see (CodeRabbit).

    `resolve_scan_root` assigns the DEFAULT id before the strict check, so with
    `strict=True` a default that exists and does not resolve raises -- 404 for
    a caller who named nothing. The test above passed only because the default
    resolved in the environment it ran in, which is the kind of pass that
    proves the environment rather than the code.

    The call sites now pass `strict=bool(source_id)`, so strictness follows
    what the CALLER supplied, not what the default lookup found.
    """
    import api.codebase_analytics.source_storage as storage

    async def _default_id():
        return "a-default-that-does-not-resolve"

    monkeypatch.setattr(storage, "get_default_source_id", _default_id, raising=False)
    with patch("api.codebase_analytics.source_storage.get_source", return_value=None):
        assert await resolve_scan_root(None, strict=bool(None)) is not None


def test_duplicates_has_no_private_source_resolution_left():
    """The fork itself, asserted gone (#17982).

    Keyed on the swallow, because that is what made it dangerous: resolution
    that falls back on exception is the shape that turns a failure into a
    completed scan of someone else's tree.
    """
    import inspect

    from api.codebase_analytics.endpoints import duplicates

    source = inspect.getsource(duplicates)
    assert "Could not resolve clone_path" not in source, (
        "the private resolution block is back in duplicates.py -- use "
        "shared.resolve_scan_root(source_id, strict=True) (#17982, #2760)"
    )
    assert "resolve_scan_root" in source, "duplicates.py no longer calls the canonical resolver"


def _swallowing_lookups() -> list[str]:
    """Every `try` that calls a source lookup and has a BROAD handler that does not re-raise.

    `except UnresolvedSourceError: return 404` is the refusal working, so only
    `Exception`/bare handlers count -- those are the ones that flatten a fault.

    Structural, because the defect was a SHAPE: `try: get_source(...) except
    Exception: logger.debug(...)` followed by a fall-through to AutoBot's own
    tree. It had already been extracted once (#2760) and the extraction left a
    copy behind, so a guard keyed on one file is how the copy survived.
    """
    import ast

    lookups = {"get_source", "get_default_source_id", "resolve_source_root", "resolve_scan_root"}
    root = Path(__file__).resolve().parents[1]
    found = []
    for path in sorted(root.rglob("*.py")):
        if path.name.endswith("_test.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Try):
                continue
            called = {
                getattr(c.func, "id", getattr(c.func, "attr", ""))
                for stmt in node.body
                for c in ast.walk(stmt)
                if isinstance(c, ast.Call)
            }
            for handler in node.handlers:
                reraises = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
                broad = handler.type is None or getattr(handler.type, "id", "") in {"Exception", "BaseException"}
                if called & lookups and broad and not reraises:
                    found.append(f"{path.relative_to(root).as_posix()}:{handler.lineno}")
    return found


#: The one deliberate swallow: a fire-and-forget background index trigger, which
#: scans nothing and reports nothing -- a failure there is only a missed
#: optimisation. Listed so a SECOND one is a visible decision, not an accident.
_ALLOWED_SWALLOWS = {"endpoints/shared.py"}


def test_no_source_lookup_is_swallowed_into_a_fallback_anywhere_in_the_package():
    """A fourth private copy of the resolution block fails here (#17982 guard)."""
    offenders = [site for site in _swallowing_lookups() if site.split(":")[0] not in _ALLOWED_SWALLOWS]
    assert not offenders, (
        "a source lookup is wrapped in a handler that does not re-raise -- a fault becomes "
        f"'no such source' and the scan falls back to AutoBot's own tree: {offenders}. "
        "Call shared.resolve_scan_root(source_id, strict=True) instead."
    )


def test_the_guard_can_fail_it_sees_the_swallow_it_exists_for():
    """Contrast control: the detector must find the shape, or the test above is vacuous."""
    shared_sites = [s for s in _swallowing_lookups() if s.startswith("endpoints/shared.py")]
    assert shared_sites, "the known best-effort swallow in shared.py was not found: the guard is blind"
