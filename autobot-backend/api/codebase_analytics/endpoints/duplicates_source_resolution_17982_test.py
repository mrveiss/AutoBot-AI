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

from unittest.mock import patch

import pytest

from api.codebase_analytics.endpoints.shared import UnresolvedSourceError, resolve_scan_root


@pytest.mark.asyncio
async def test_a_named_source_that_is_absent_refuses():
    """`strict=True` is the whole point: a scan has no user watching it."""
    with patch("api.codebase_analytics.source_storage.get_source", return_value=None):
        with pytest.raises(UnresolvedSourceError):
            await resolve_scan_root("ghost-source", strict=True)


@pytest.mark.asyncio
async def test_a_lookup_that_raises_refuses_rather_than_substituting():
    """The state the old code was most wrong about.

    A raising `get_source` went to `logger.debug` and left `project_root` as
    AutoBot's own tree -- invisible at normal log level, and indistinguishable
    in the result from a genuine scan of the requested project.
    """
    with patch("api.codebase_analytics.source_storage.get_source", side_effect=RuntimeError("db down")):
        with pytest.raises(UnresolvedSourceError):
            await resolve_scan_root("some-source", strict=True)


@pytest.mark.asyncio
async def test_naming_no_source_still_falls_back():
    """The contrast, and the reason `strict` is not simply "always raise".

    "You did not say which project" and "you named one that is not there" are
    different questions, and only the second is a mistake. Without this, the
    fix above could be a blanket raise and both tests would still pass.
    """
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
