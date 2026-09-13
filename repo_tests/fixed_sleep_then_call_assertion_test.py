# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test decides an assertion with a fixed sleep (#16224, widened by #16255).

``await asyncio.sleep(0.05)`` followed by ``store.write.assert_called_once()`` is
a claim about how much wall clock a shared runner grants a background task. A
loaded runner that has not scheduled the task yet produces exactly the red a real
regression produces, so the red cannot say which one it saw. #16009 found these
sites and #16224 fixed the last of them; this guard names any new one, with the
fix: wait on the observable with ``autobot_shared.eventually.eventually``.

The narrow shape, in a collectable test's OWN body -- never a nested helper, a
fake loop or a lambda, which ``own_nodes`` skips -- is a statement
``await asyncio.sleep(<positive constant>)`` followed within ``_WINDOW_LINES``
lines by a positive call assertion: an ``assert_called*`` / ``assert_awaited*``
call, or an ``assert`` that reads ``.call_count`` / ``.await_count``. The
``assert_not_*`` forms are spared: a slow runner can make them pass vacuously but
cannot turn them red, which is a different defect from the one this guards.

#16255 widened the shape: a fixed sleep followed, within the next
``_ANY_ASSERT_WINDOW_STATEMENTS`` of the test's own statements, by ANY ``assert``
statement -- not only a call assertion. Not every sleep before an assert is the
#16224 defect: a TTL expiry, a debounce window or a rate-limit refill genuinely
needs wall clock to pass, and elapsed time IS the subject there. Such a site is
exempted only by a reasoned comment, ``# fixed sleep on purpose (#16255): <why>``,
on the sleep's own line or the one directly above it -- an empty reason after the
colon does not count, so the exemption cannot be used to silence the guard.

AC2 of #16255 names every exempted site rather than trusting the comment alone:
``_EXEMPT_SITES`` below lists each ``(repo-relative path, test qualname)`` the
marker is allowed on, with how many exempt sleeps that site carries (1 unless
noted). A marker anywhere else fails loudly as an unlisted exemption, naming the
site -- the marker cannot be used to grow the allowlist by itself. A named entry
whose site no longer carries a marker (the test moved, was renamed, or the sleep
was removed) fails as stale, so the allowlist cannot silently drift out of sync
with the code it describes.
"""

from __future__ import annotations

import ast
import functools
import re
from collections import Counter

from repo_tests.collected_test_model import REPO_ROOT, collectable_tests, own_nodes, parse_module, test_modules

_WINDOW_LINES = 8
#: Measured 2026-09-11 with ``test_modules()``'s own population rules: 2316 test
#: modules holding 30717 collectable tests. The floors sit just below, so an
#: enumeration that silently loses a subtree fails here instead of reading clean.
_MIN_MODULES = 2250
_MIN_TEST_FUNCTIONS = 30000
_CALL_ASSERTION = re.compile(r"\.assert_(?:called|awaited)\w*\(|\.(?:call|await)_count\b")

_ANY_ASSERT_WINDOW_STATEMENTS = 3
_EXEMPTION_MARKER = "# fixed sleep on purpose (#16255):"

#: Every reasoned #16255 exemption in the repo, keyed by ``(repo-relative path,
#: "Class.method" or "function" qualname)`` rather than line number, which drifts
#: on any unrelated edit above it in the same file. The value is how many exempt
#: sleeps that one test carries -- 1 unless the comment says otherwise. Counted by
#: hand from ``git grep -n "fixed sleep on purpose (#16255):"`` on 2026-09-11: 12
#: exempt sleeps across these 10 sites.
_EXEMPT_SITES: dict[tuple[str, str], int] = {
    (
        "autobot-backend/knowledge/embedding_cache_test.py",
        "TestEmbeddingCache.test_ttl_expiration",
    ): 1,  # TTL expiry via time.time() is the subject; no injectable clock
    (
        "autobot-backend/multimodal_processor/multimodal_integration_test.py",
        "TestMultiModalWorkflowIntegration.test_realtime_multimodal_stream",
    ): 1,  # paces the simulated stream; excluded from every timing assert below
    (
        "autobot-backend/security/threat_intelligence_test.py",
        "TestThreatIntelligenceCache.test_cache_expiration",
    ): 1,  # TTL expiry via time.time() is the subject; no injectable clock
    (
        "autobot-backend/security/threat_intelligence_test.py",
        "TestThreatIntelligenceCache.test_clear_expired",
    ): 1,  # TTL expiry via time.time() is the subject; no injectable clock
    (
        "autobot-backend/services/wake_word_detection_test.py",
        "TestCPUOptimization.test_throttle_triggered_when_cpu_high",
    ): 1,  # throttle depends on real sampled host CPU; no observable to wait on
    (
        "autobot-backend/services/wake_word_detection_test.py",
        "TestCPUProfileBaseline.test_idle_listening_cpu_baseline",
    ): 1,  # sustained-operation CPU baseline; wall time is the subject
    (
        "autobot-backend/tests/services/test_concurrent_limiter.py",
        "TestDropOldestCallbackInvoked.test_oldest_workflow_is_evicted_not_newest",
    ): 1,  # eviction order reads time.time(); no injectable clock, must differ
    (
        "autobot-backend/tests/utils/test_pipeline_profiler.py",
        "TestPipelineProfiler.test_profile_records_stage_timing",
    ): 2,  # duration_ms is the value under test, paired across two stages
    (
        "autobot-backend/tests/utils/test_pipeline_profiler.py",
        "TestPipelineProfiler.test_total_duration",
    ): 2,  # total_ms is the value under test, paired across two stages
    (
        "autobot-slm-backend/tests/test_provision_progress.py",
        "TestTaskProgressTracker.test_elapsed_seconds_advances",
    ): 1,  # elapsed_seconds is a time.monotonic() delta -- time IS the subject
}


def _is_fixed_sleep(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)):
        return False
    call = node.value.value
    if not (isinstance(call, ast.Call) and ast.unparse(call.func) == "asyncio.sleep" and call.args):
        return False
    delay = call.args[0]
    return isinstance(delay, ast.Constant) and isinstance(delay.value, (int, float)) and delay.value > 0


def _is_call_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return bool(_CALL_ASSERTION.search(ast.unparse(node)))
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        return bool(_CALL_ASSERTION.search(ast.unparse(node.value.func) + "("))
    return False


def fixed_sleep_call_assertions(tree: ast.Module) -> list[int]:
    """Line of every fixed sleep that a call assertion follows, as the module docstring defines."""
    found: list[int] = []
    for function in collectable_tests(tree):
        statements = sorted(own_nodes(function, (ast.stmt,)), key=lambda node: node.lineno)
        for index, node in enumerate(statements):
            if not _is_fixed_sleep(node):
                continue
            window = [s for s in statements[index + 1 :] if s.lineno <= node.lineno + _WINDOW_LINES]
            if any(_is_call_assertion(s) for s in window):
                found.append(node.lineno)
    return found


def _is_exempted(node: ast.AST, source_lines: list[str]) -> bool:
    """True when the sleep's own or preceding line carries a reasoned #16255 marker."""
    for lineno in (node.lineno, node.lineno - 1):
        if lineno < 1 or lineno > len(source_lines):
            continue
        line = source_lines[lineno - 1]
        if _EXEMPTION_MARKER in line and line.split(_EXEMPTION_MARKER, 1)[1].strip():
            return True
    return False


def fixed_sleep_then_any_assert(tree: ast.Module, source_lines: list[str]) -> list[int]:
    """Line of every non-exempt fixed sleep that ANY assert follows, as the module docstring defines."""
    found: list[int] = []
    for function in collectable_tests(tree):
        statements = sorted(own_nodes(function, (ast.stmt,)), key=lambda node: node.lineno)
        for index, node in enumerate(statements):
            if not _is_fixed_sleep(node) or _is_exempted(node, source_lines):
                continue
            window = statements[index + 1 : index + 1 + _ANY_ASSERT_WINDOW_STATEMENTS]
            if any(isinstance(s, ast.Assert) for s in window):
                found.append(node.lineno)
    return found


def _qualname(tree: ast.Module, function: ast.AST) -> str:
    """``"Class.method"`` for a test method, or the bare name for a module-level test."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and function in node.body:
            return f"{node.name}.{function.name}"
    return function.name


def _exempted_sites(tree: ast.Module, source_lines: list[str]) -> list[tuple[str, int]]:
    """``(qualname, line)`` for every fixed sleep this module marks exempt (#16255)."""
    found: list[tuple[str, int]] = []
    for function in collectable_tests(tree):
        for node in own_nodes(function, (ast.stmt,)):
            if _is_fixed_sleep(node) and _is_exempted(node, source_lines):
                found.append((_qualname(tree, function), node.lineno))
    return found


def _named_exemption_findings(
    exempted: list[tuple[str, str, int]], named: dict[tuple[str, str], int]
) -> tuple[list[str], list[str]]:
    """``(unlisted, stale)`` for ``exempted`` markers against the ``named`` allowlist.

    Takes both as plain arguments, independent of the real repo sweep, so the
    self-tests below can drive it with planted data. An occurrence beyond a
    site's named count is unlisted too -- a known site quietly growing its
    exemption count is exactly the drift the allowlist exists to catch.
    """
    seen: Counter[tuple[str, str]] = Counter()
    unlisted: list[str] = []
    for path, qualname, line in exempted:
        key = (path, qualname)
        seen[key] += 1
        if seen[key] > named.get(key, 0):
            unlisted.append(f"{path}:{line} ({qualname})")
    stale = [
        f"{path} ({qualname}): named for {count}, only {seen.get((path, qualname), 0)} found"
        for (path, qualname), count in named.items()
        if seen.get((path, qualname), 0) < count
    ]
    return unlisted, stale


@functools.lru_cache(maxsize=1)
def _sweep() -> tuple[int, int, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    modules = test_modules()
    tests = 0
    narrow_offenders: list[str] = []
    wide_offenders: list[str] = []
    exempted: list[tuple[str, str, int]] = []
    for path in modules:
        tree = parse_module(path)
        tests += len(collectable_tests(tree))
        relative = str(path.relative_to(REPO_ROOT))
        narrow_offenders.extend(f"{relative}:{line}" for line in fixed_sleep_call_assertions(tree))
        source_lines = path.read_text(encoding="utf-8").splitlines()
        wide_offenders.extend(f"{relative}:{line}" for line in fixed_sleep_then_any_assert(tree, source_lines))
        exempted.extend((relative, qualname, line) for qualname, line in _exempted_sites(tree, source_lines))
    unlisted, stale = _named_exemption_findings(exempted, _EXEMPT_SITES)
    return len(modules), tests, tuple(narrow_offenders), tuple(wide_offenders), tuple(unlisted), tuple(stale)


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    modules, tests, *_ = _sweep()
    assert modules >= _MIN_MODULES, f"only {modules} test modules found (floor {_MIN_MODULES}): a subtree went missing"
    assert tests >= _MIN_TEST_FUNCTIONS, f"only {tests} tests (floor {_MIN_TEST_FUNCTIONS}): a subtree went missing"


def test_no_test_decides_a_call_assertion_with_a_fixed_sleep() -> None:
    _, _, offenders, _, _, _ = _sweep()
    assert not offenders, (
        "These tests sleep a fixed interval and then assert that a call happened. A loaded runner "
        "fails them exactly as a regression would (#16224):\n  "
        + "\n  ".join(offenders)
        + "\nWait on the observable instead, e.g. `await eventually(task.done)` or "
        "`await eventually(lambda: mock.called)` from autobot_shared.eventually."
    )


def test_no_test_decides_any_assertion_with_a_fixed_sleep() -> None:
    _, _, _, offenders, _, _ = _sweep()
    assert not offenders, (
        "These tests sleep a fixed interval and then make some assertion. A loaded runner fails "
        "them exactly as a regression would (#16255):\n  "
        + "\n  ".join(offenders)
        + "\nWait on the observable with `await eventually(...)` from autobot_shared.eventually, "
        "or -- only when elapsed time IS the subject (a TTL, a debounce, a rate limit) -- leave the "
        "sleep and mark it `# fixed sleep on purpose (#16255): <why>` on its own or the preceding line."
    )


def test_no_marker_exempts_a_site_outside_the_named_allowlist() -> None:
    *_, unlisted, _ = _sweep()
    assert not unlisted, (
        "These fixed sleeps carry the #16255 exemption marker but are not in _EXEMPT_SITES "
        "(repo_tests/fixed_sleep_then_call_assertion_test.py):\n  "
        + "\n  ".join(unlisted)
        + "\nEither this is a genuinely new deliberate-time site -- add it to _EXEMPT_SITES with a "
        "one-phrase reason -- or the marker is being used to dodge the guard, in which case wait on "
        "the observable instead."
    )


def test_every_named_exemption_still_carries_its_marker() -> None:
    *_, stale = _sweep()
    assert not stale, (
        "These _EXEMPT_SITES entries no longer match a marked sleep in the code (the test moved, was "
        "renamed, or the sleep was removed):\n  "
        + "\n  ".join(stale)
        + "\nUpdate the entry's (path, qualname) to match the current test, or delete the entry if the "
        "sleep is gone."
    )


_PLANTED = (
    "import asyncio\n\n"
    "async def test_flagged_count():\n    await asyncio.sleep(0.05)\n    assert worker.call_count == 2\n\n"
    "async def test_flagged_method():\n    await asyncio.sleep(0.2)\n    store.write.assert_called_once()\n\n"
    "async def test_spared_negative():\n    await asyncio.sleep(0.05)\n    store.write.assert_not_called()\n\n"
    "async def test_spared_nested_loop():\n    async def loop():\n        await asyncio.sleep(0.1)\n"
    "    await wait_until(lambda: check.await_count >= 2, loop=loop)\n\n"
    "async def test_spared_observable():\n    await eventually(lambda: store.write.called)\n"
    "    store.write.assert_called_once()\n\n"
    "async def test_spared_zero_yield():\n    await asyncio.sleep(0)\n    store.write.assert_called_once()\n\n"
    "async def test_spared_far_away():\n    await asyncio.sleep(0.05)\n"
    + "    pass\n" * _WINDOW_LINES
    + "    store.write.assert_called_once()\n"
)


def test_the_detector_flags_the_planted_shapes_and_spares_the_rest() -> None:
    tree = ast.parse(_PLANTED)
    lines = fixed_sleep_call_assertions(tree)
    flagged = {fn.name for fn in collectable_tests(tree) if any(fn.lineno <= ln <= fn.end_lineno for ln in lines)}
    assert flagged == {"test_flagged_count", "test_flagged_method"}, flagged


_PLANTED_ANY_ASSERT = (
    "import asyncio\n\n"
    "async def test_flagged_plain_assert():\n    await asyncio.sleep(0.05)\n    x = 1\n    assert x == 1\n\n"
    "async def test_spared_reasoned_comment():\n"
    "    # fixed sleep on purpose (#16255): planted reason for the self-test\n"
    "    await asyncio.sleep(0.05)\n    assert True\n\n"
    "async def test_flagged_empty_reason():\n"
    "    # fixed sleep on purpose (#16255):\n"
    "    await asyncio.sleep(0.05)\n    assert True\n"
)


def test_the_wide_detector_honours_the_reasoned_exemption_only() -> None:
    tree = ast.parse(_PLANTED_ANY_ASSERT)
    lines = fixed_sleep_then_any_assert(tree, _PLANTED_ANY_ASSERT.splitlines())
    flagged = {fn.name for fn in collectable_tests(tree) if any(fn.lineno <= ln <= fn.end_lineno for ln in lines)}
    assert flagged == {"test_flagged_plain_assert", "test_flagged_empty_reason"}, flagged


_PLANTED_NAMED = (
    "import asyncio\n\n"
    "async def test_named_and_marked():\n"
    "    # fixed sleep on purpose (#16255): named and allowed\n"
    "    await asyncio.sleep(0.05)\n"
    "    assert True\n\n"
    "async def test_marked_but_not_named():\n"
    "    # fixed sleep on purpose (#16255): not in the allowlist\n"
    "    await asyncio.sleep(0.05)\n"
    "    assert True\n"
)


def test_the_named_allowlist_flags_an_unlisted_marker_and_a_stale_entry() -> None:
    tree = ast.parse(_PLANTED_NAMED)
    source_lines = _PLANTED_NAMED.splitlines()
    exempted = [("planted.py", qualname, line) for qualname, line in _exempted_sites(tree, source_lines)]
    named = {
        ("planted.py", "test_named_and_marked"): 1,  # in-set marker: must pass
        ("planted.py", "test_stale_and_gone"): 1,  # no matching marker anywhere: must report stale
    }
    unlisted, stale = _named_exemption_findings(exempted, named)
    assert unlisted == ["planted.py:10 (test_marked_but_not_named)"], unlisted
    assert stale == ["planted.py (test_stale_and_gone): named for 1, only 0 found"], stale
