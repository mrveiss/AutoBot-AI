#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A blocked push shows the failing test, not the last 25 lines (#17961).

vitest prints its failures BEFORE its summary, and the hook appends the
dependency-floor report after it, so `tail -25` of a real failure showed only
"Start at", "Duration" and the floor list. That hid the #18495 failure through
five blocked pushes. These tests run the hook's own `failure_excerpt` on
recorded output shapes, rather than a copy of it.
"""

from __future__ import annotations

import re
import subprocess

from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_FUNC = re.compile(r"^failure_excerpt\(\) \{\n(?:.*\n)*?\}$", re.MULTILINE)

#: The 22-line floor report the hook prints after vitest's summary.
_FLOOR = "".join(f"[dependency-floor]   pkg{i}: installed 1.0.0, declared ^2.0.0\n" for i in range(22))

#: Shape of the run that blocked #18495 (load-a, 2026-10-16), ANSI colour kept.
_VITEST_FAILURE = (
    " \x1b[31mFAIL\x1b[39m  src/components/schedule/__tests__/SchedulePickerField.i18n.test.ts"
    " > SchedulePickerField i18n (#18432) > en: every summary renders as prose\n"
    "Error: Test timed out in 10000ms.\n"
    " ❯ src/components/schedule/__tests__/SchedulePickerField.i18n.test.ts:50:32\n"
    + "     48|   })\n" * 30
    + " Test Files  5 failed | 257 passed (262)\n"
    "      Tests  15 failed | 2756 passed (2771)\n"
    "   Start at  08:20:06\n"
    "   Duration  376.71s (transform 647.88s, environment 3516.82s)\n" + _FLOOR
)

#: Every test passed, but an unhandled error makes vitest exit 1.
_UNHANDLED = (
    " ✓ src/a.test.ts (3 tests) 12ms\n"
    "⎯⎯⎯⎯⎯⎯ Unhandled Errors ⎯⎯⎯⎯⎯⎯\n"
    "Vitest caught 1 unhandled error during the test run.\n"
    "⎯⎯⎯⎯ Unhandled Rejection ⎯⎯⎯⎯\n"
    "TypeError: Cannot read properties of undefined (reading 'x')\n"
    " ❯ src/components/workflow/WorkflowCanvas.vue:120:5\n"
    'This error originated in "src/components/workflow/__tests__/WorkflowCanvas.search.test.ts" test file.\n'
    " Test Files  262 passed (262)\n"
    "      Tests  2881 passed (2881)\n"
    "     Errors  1 error\n" + _FLOOR
)

_PYTEST_FAILURE = (
    "...F..\n"
    "FAILED repo_tests/x_test.py::test_y - AssertionError: expected 1 got 2\n"
    "========== 1 failed, 5 passed in 2.1s ==========\n" + _FLOOR
)


def _excerpt(output: str) -> str:
    match = _FUNC.search(_HOOK.read_text(encoding="utf-8"))
    assert match, "the hook no longer defines failure_excerpt -- move this test with it, do not delete it"
    script = f'{match.group(0)}\nfailure_excerpt "$(cat)"'
    done = subprocess.run(["bash", "-c", script], input=output, capture_output=True, text=True, check=True)
    return done.stdout


def test_the_failing_test_name_and_its_error_reach_the_output() -> None:
    out = _excerpt(_VITEST_FAILURE)
    assert "SchedulePickerField.i18n.test.ts > SchedulePickerField i18n (#18432) > en:" in out
    assert "Test timed out in 10000ms" in out
    assert "5 failed | 257 passed" in out


def test_the_old_tail_would_have_hidden_it() -> None:
    """Contrast: the shape really does defeat a fixed tail, so the test above is not vacuous."""
    tail = "\n".join(_VITEST_FAILURE.splitlines()[-25:])
    assert "SchedulePickerField" not in tail


def test_an_unhandled_error_with_every_test_passing_is_shown() -> None:
    out = _excerpt(_UNHANDLED)
    assert "Cannot read properties of undefined" in out
    assert "WorkflowCanvas.search.test.ts" in out
    assert "Errors  1 error" in out


def test_the_per_group_pytest_output_shows_the_failed_test() -> None:
    out = _excerpt(_PYTEST_FAILURE)
    assert "FAILED repo_tests/x_test.py::test_y - AssertionError" in out


def test_an_unknown_shape_falls_back_to_the_tail_rather_than_nothing() -> None:
    out = _excerpt("something went wrong\nexit 3\n")
    assert "something went wrong" in out


def test_pytest_assertion_detail_and_a_cross_mark_failure_are_shown() -> None:
    out = _excerpt(_PYTEST_FAILURE.replace("FAILED", "E   assert 1 == 2\nFAILED", 1))
    assert "E   assert 1 == 2" in out
    assert "✗ src/b.test.ts > broke" in _excerpt(" ✗ src/b.test.ts > broke\n" + _FLOOR)


def test_the_excerpt_is_bounded_and_keeps_the_summary_past_the_cap() -> None:
    noisy = "".join(f" FAIL  src/t{i}.test.ts > case\n" for i in range(500))
    out = _excerpt(noisy + " Test Files  500 failed (500)\n      Tests  500 failed (500)\n" + _FLOOR)
    assert len(out.splitlines()) <= 64
    assert "Tests  500 failed (500)" in out


def test_every_report_site_uses_the_excerpt() -> None:
    """Reverting one site to a fixed tail fails here, not silently."""
    source = _HOOK.read_text(encoding="utf-8")
    calls = re.findall(r'failure_excerpt "\$(\w+)" >&2', source)
    assert sorted(calls) == ["group_output", "kit_output", "vitest_output"]
    body = _FUNC.search(source).group(0)
    assert source.count("tail -25") == body.count("tail -25") == 1
