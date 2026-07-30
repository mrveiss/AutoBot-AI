# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: raw ``aiohttp.ClientSession(...)`` constructions must not grow (#12992).

Issue #12979 is converting per-request ``aiohttp.ClientSession(...)`` sites in
``autobot-backend/`` over to the shared pooled client
(``autobot_shared.http_client.get_http_client()``). That sweep is not
converging: two conversion batches landed, yet the remaining count came out
*higher* than simple subtraction predicted, because unrelated PRs merged into
``Dev_new_gui`` kept introducing new raw sessions while the batches were in
flight. Every raw session opens its own connector, bypasses the shared pool's
sizing/utilisation accounting, and re-creates the exact class of leak #12981
and #12992 fixed.

The sweep cannot finish while the backlog refills behind it. This test is the
ratchet: it counts the constructions still present and asserts the count never
*exceeds* the recorded ceiling, so the existing backlog stays green while any
newly added raw session turns the suite red at the point it is introduced.

Measured 2026-07-30 (#12992), on ``Dev_new_gui`` at ``352e07cc7``:
**87** constructions across the walked tree.

Unlike the ``xfail(strict=True)`` guard in
``autobot-slm-backend/tests/test_update_all_applies_roles_12959.py`` — which
marks a single binary gap — this is a monotonically decreasing budget, because
the backlog is drained incrementally by #12979's batches rather than in one
commit.

Refs #12979, #12981, #12989, #12992.
"""

import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Recorded ceiling on raw ``aiohttp.ClientSession(...)`` constructions in the
#: walked tree. This number MUST ONLY EVER BE LOWERED. Converting sites to the
#: shared pooled client (``get_http_client()``) is the only legitimate way to
#: change it. If a change makes this test fail, the fix is to route the new
#: call through the shared client — never to raise the ceiling. See #12979.
#:
#: HOW TO RE-MEASURE WHEN LOWERING THIS — two traps, both already hit once:
#:
#: 1. Do NOT use ``grep -c 'aiohttp.ClientSession('``. Grep reads 90 where this
#:    test reads 87, because three matches are text rather than constructions:
#:    a docstring example in ``code_analysis/scripts/analyze_performance.py``,
#:    a ``print()`` string in ``code_analysis/scripts/analyze_performance_simple.py``,
#:    and a regex replacement template in ``code_analysis/src/patch_generator.py``.
#:    Trusting grep sets the ceiling 3 too high and silently buys slack for
#:    three future raw sessions. Use ``raw_client_session_sites()`` below.
#: 2. Re-measure against a tree freshly synced to ``origin/Dev_new_gui``
#:    IMMEDIATELY BEFORE PUSHING. A count taken in a worktree is a snapshot of
#:    that worktree: the first version of this file recorded 112, measured while
#:    #12994 was still in flight. That PR merged and removed 25 constructions,
#:    so the ceiling shipped ~25 too high — most of a conversion batch's worth
#:    of slack — until it was caught in review. Sync, re-run, then push.
MAX_RAW_CLIENT_SESSIONS = 87

#: Directory names that are never part of the production surface being swept.
EXCLUDED_DIR_NAMES = {"__pycache__", "tests", "test", ".pytest_cache", "node_modules"}

#: Substring marking archived/vendored copies that are not live code.
EXCLUDED_DIR_SUBSTRING = "archive"

#: Files exempt from the ceiling. ``autobot_shared/http_client.py`` is the
#: pooled client itself — constructing the shared session is precisely its job.
#: Matched on the trailing path so a vendored/synced copy is exempt too.
EXEMPT_SUFFIXES = (pathlib.Path("autobot_shared") / "http_client.py",)


def _is_excluded(path: pathlib.Path) -> bool:
    """True when *path* is a test, cache, or archived file rather than live code."""
    for part in path.parts[:-1]:
        if part in EXCLUDED_DIR_NAMES or EXCLUDED_DIR_SUBSTRING in part:
            return True
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _is_exempt(path: pathlib.Path) -> bool:
    """True when *path* is allowed to construct a raw session."""
    return any(path.as_posix().endswith(suffix.as_posix()) for suffix in EXEMPT_SUFFIXES)


def _count_constructions(source: str) -> int:
    """Count ``ClientSession(...)`` call expressions in *source*.

    Parsed with ``ast`` rather than grepped so that the same text appearing in a
    docstring, comment, or code-generator replacement template (for example
    ``code_analysis/src/patch_generator.py``) is not miscounted as a real
    construction.
    """
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "ClientSession":
            count += 1
        elif isinstance(func, ast.Name) and func.id == "ClientSession":
            count += 1
    return count


def walk_backend_sources() -> list[pathlib.Path]:
    """Return every live ``autobot-backend/`` Python file subject to the ceiling."""
    return [path for path in sorted(BACKEND_ROOT.rglob("*.py")) if not _is_excluded(path) and not _is_exempt(path)]


def raw_client_session_sites() -> dict[str, int]:
    """Map each offending file (repo-relative) to its construction count."""
    sites: dict[str, int] = {}
    for path in walk_backend_sources():
        count = _count_constructions(path.read_text(encoding="utf-8"))
        if count:
            sites[path.relative_to(BACKEND_ROOT.parent).as_posix()] = count
    return sites


def test_walker_scans_a_nonempty_tree():
    """The walk must find real files, so the ceiling cannot pass vacuously.

    Without this, a rename of ``autobot-backend/`` or a broadened exclusion rule
    would silently reduce the walk to zero files and the ceiling assertion would
    pass while checking nothing.
    """
    scanned = walk_backend_sources()
    assert len(scanned) > 1000, (
        f"Walker found only {len(scanned)} files under {BACKEND_ROOT}; "
        "expected the full backend tree. The ceiling assertion is meaningless "
        "against an empty or truncated walk — fix the walker, not this bound."
    )
    assert any(path.name == "monitoring_integration.py" for path in scanned), (
        "Walker did not reach integrations/monitoring_integration.py — the walk "
        "is not covering the backend package tree."
    )


def test_raw_client_sessions_do_not_exceed_ceiling():
    """New raw ``aiohttp.ClientSession(...)`` sites must not be added (#12979).

    Route the call through ``autobot_shared.http_client.get_http_client()``
    instead — ``get_json()``/``post_json()`` for JSON, ``tracked_request()`` when
    the raw response must be inspected. Do not raise ``MAX_RAW_CLIENT_SESSIONS``.
    """
    sites = raw_client_session_sites()
    total = sum(sites.values())

    assert total <= MAX_RAW_CLIENT_SESSIONS, (
        f"{total} raw aiohttp.ClientSession(...) constructions found, exceeding the "
        f"recorded ceiling of {MAX_RAW_CLIENT_SESSIONS} (#12992). New raw sessions "
        "bypass the shared connection pool and its active-request accounting. "
        "Use autobot_shared.http_client.get_http_client() — get_json()/post_json(), "
        "or tracked_request() when the response object itself must be inspected. "
        "The ceiling may only ever be LOWERED.\n"
        "Current offenders:\n" + "\n".join(f"  {path}: {count}" for path, count in sorted(sites.items()))
    )
