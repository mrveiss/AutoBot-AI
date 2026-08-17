#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``no-literal-ttl-seconds`` pre-commit hook (#14206).

Before this widening, the checker matched ``setex``/``expire``/``pexpire``
and ``.set(ttl=N)`` only. It could not see ``redis.set(key, value, ex=N)`` —
redis-py's own native TTL kwarg, and the most common TTL-setting shape in
this tree. Passing on that shape is exactly the failure mode this file
guards against: a test that only shows the checker passes on clean input
would reproduce the bug, not catch it.

Review on the original #14206 PR found the widened checker still missed `ex`
passed *positionally* (``set(name, value, ex, ...)`` / ``getex(name, ex,
...)``) because both ``check_file`` and the reach counter walked
``node.keywords`` only. `set(key, value, 3600)` is semantically identical to
`ex=3600` and was caught by nothing — the exact drift shape this checker
exists to prevent, reopened through a spelling the PR's own framing claimed
to have closed. The ``*-ex-positional-*`` fixtures below cover that.

Fixture sources are assembled from string fragments rather than written as
literal ``.set(..., ex=100)`` calls in this file's own source, so this test
file does not trip the very lint it exercises.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("check_no_literal_ttl_seconds.py")
_spec = importlib.util.spec_from_file_location("check_no_literal_ttl_seconds", _MODULE_PATH)
assert _spec and _spec.loader
check_no_literal_ttl_seconds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_no_literal_ttl_seconds)


def _check(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return check_no_literal_ttl_seconds.check_file(target)


def _call(receiver: str, method: str, *args: str, **kwargs: str) -> str:
    """Build ``receiver.method(args, kw=val, ...)`` from fragments."""
    parts = list(args) + [f"{k}={v}" for k, v in kwargs.items()]
    return f"{receiver}.{method}(" + ", ".join(parts) + ")\n"


# ---------------------------------------------------------------------------
# The gap #14206 closed: redis-py's native `.set()`/`.getex()` TTL kwargs.
# ---------------------------------------------------------------------------

FLAGGED = [
    pytest.param(_call("redis_client", "set", '"k"', '"v"', ex="3600"), id="set-ex-literal"),
    pytest.param(_call("redis_client", "set", '"k"', '"v"', px="3600000"), id="set-px-literal"),
    pytest.param(_call("redis_client", "set", '"k"', '"v"', exat="1999999999"), id="set-exat-literal"),
    pytest.param(_call("redis_client", "set", '"k"', '"v"', pxat="1999999999000"), id="set-pxat-literal"),
    pytest.param(_call("redis_client", "getex", '"k"', ex="3600"), id="getex-ex-literal"),
    pytest.param(
        _call("redis_client", "set", '"k"', '"v"', ex="90 * 86400"), id="set-ex-binop-literal"
    ),
    pytest.param(_call("redis_client", "psetex", '"k"', "3600000", '"v"'), id="psetex-literal"),
    pytest.param(_call("redis_client", "expireat", '"k"', "1999999999"), id="expireat-literal"),
    pytest.param(_call("redis_client", "pexpireat", '"k"', "1999999999000"), id="pexpireat-literal"),
    # redis-py accepts `ex` positionally too — set(name, value, ex, ...) /
    # getex(name, ex, ...). A keyword-only check missed this shape entirely
    # (review finding on the original #14206 PR): `set(key, value, 3600)` is
    # semantically identical to `ex=3600` and was caught by nothing.
    pytest.param(_call("redis_client", "set", '"k"', '"v"', "3600"), id="set-ex-positional-literal"),
    pytest.param(_call("redis_client", "getex", '"k"', "3600"), id="getex-ex-positional-literal"),
    # The methods the checker already covered before #14206 stay covered.
    pytest.param(_call("redis_client", "setex", '"k"', "3600", '"v"'), id="setex-literal-preexisting"),
    pytest.param(_call("redis_client", "expire", '"k"', "3600"), id="expire-literal-preexisting"),
    pytest.param(_call("redis_client", "pexpire", '"k"', "3600000"), id="pexpire-literal-preexisting"),
    pytest.param(_call("cache", "set", '"k"', '"v"', ttl="3600"), id="cache-set-ttl-literal-preexisting"),
]


@pytest.mark.parametrize("source", FLAGGED, ids=[p.id for p in FLAGGED])
def test_flags_literal_ttl(tmp_path: Path, source) -> None:
    """Each fixture is the exact shape #14206 says the checker must catch."""
    violations = _check(tmp_path, source)
    assert violations, f"expected a violation for: {source!r}"


# ---------------------------------------------------------------------------
# The false-positive trap the issue calls out explicitly: a *computed*
# expression is not a literal, and the checker must keep permitting it.
# ---------------------------------------------------------------------------

CLEAN = [
    pytest.param(
        _call("redis_client", "set", '"k"', '"v"', ex="self.retention_days * 86400"),
        id="set-ex-computed-attr-expr",
    ),
    pytest.param(_call("redis_client", "set", '"k"', '"v"', ex="ttl"), id="set-ex-named-variable"),
    pytest.param(
        _call("redis_client", "set", '"k"', '"v"', ex="TTL_1_HOUR"), id="set-ex-named-constant"
    ),
    pytest.param(_call("redis_client", "getex", '"k"', ex="dynamic_ttl"), id="getex-ex-named-variable"),
    pytest.param(_call("redis_client", "get", '"k"'), id="unrelated-get-call"),
    # Same false-positive trap, for `ex` passed positionally.
    pytest.param(
        _call("redis_client", "set", '"k"', '"v"', "self.retention_days * 86400"),
        id="set-ex-positional-computed-attr-expr",
    ),
    pytest.param(
        _call("redis_client", "set", '"k"', '"v"', "TTL_1_HOUR"), id="set-ex-positional-named-constant"
    ),
    pytest.param(_call("redis_client", "getex", '"k"', "dynamic_ttl"), id="getex-ex-positional-named-variable"),
]


@pytest.mark.parametrize("source", CLEAN, ids=[p.id for p in CLEAN])
def test_does_not_flag_computed_or_named_ttl(tmp_path: Path, source) -> None:
    """A computed/named TTL is exactly what the rule exists to permit."""
    violations = _check(tmp_path, source)
    assert not violations, f"unexpected violation(s) for: {source!r}: {violations}"


def test_scan_reach_does_not_silently_collapse(tmp_path: Path) -> None:
    """Presence check: count the call sites this checker actually inspects.

    A checker that stops matching its subject (a rename, a broken AST walk)
    still returns an empty violation list and reads as clean. This asserts
    the scan really is looking at every shape it claims to cover, not just
    that it found zero problems in one of them.
    """
    source = "".join(p.values[0] for p in FLAGGED)
    target = tmp_path / "all_shapes.py"
    target.write_text(source, encoding="utf-8")

    inspected = check_no_literal_ttl_seconds.count_ttl_call_sites(target)
    assert inspected == len(FLAGGED), (
        f"expected the reach counter to see all {len(FLAGGED)} call sites, saw {inspected} "
        "— the scan's subject narrowed silently"
    )

    violations = check_no_literal_ttl_seconds.check_file(target)
    assert len(violations) == len(FLAGGED), (
        f"expected {len(FLAGGED)} violations, got {len(violations)}: {violations}"
    )
