#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A vitest that ran nothing is COULD NOT RUN, not `vitest failures` (#18406).

Split from `prepush_frontend_projects_17574_test.py` to keep both under the
600-line ceiling. Like that file, these tests run the hook's **own** function
rather than a copy of it: a reimplementation here would agree with itself and
prove nothing.
"""

from __future__ import annotations

import re
import subprocess

from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"


def _source() -> str:
    return _HOOK.read_text(encoding="utf-8")


#: `vitest_ran_nothing`, the #18406 classifier, as shipped.
_RAN_NOTHING = re.compile(r"^vitest_ran_nothing\(\) \{\n(?:.*\n)*?\}$", re.MULTILINE)

#: Verbatim from the push this blocked: an emptied shared node_modules, so vitest
#: died loading its own config and never collected a test (#18406).
_STARTUP_DEATH = """vitest.config.ts (8:16) [UNRESOLVED_IMPORT] Could not resolve '@vitejs/plugin-vue' in vitest.config.ts
failed to load config from /repo/autobot-slm-frontend/vitest.config.ts
⎯⎯⎯⎯⎯⎯⎯ Startup Error ⎯⎯⎯⎯⎯⎯⎯⎯
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'vitest' imported from /repo/autobot-slm-frontend/node_modules/.vite-temp/vitest.config.ts.mjs
"""

_REAL_FAILURE = """ FAIL  src/composables/__tests__/useThing.test.ts > adds
AssertionError: expected 2 to be 3
 Test Files  1 failed (1)
      Tests  1 failed (1)
"""

_REAL_PASS = """ ✓ src/composables/__tests__/useThing.test.ts (3 tests) 12ms
 Test Files  1 passed (1)
      Tests  3 passed (3)
"""


class TestAVitestThatRanNothingIsNotAFailure:
    """#18406: an emptied shared node_modules killed vitest at startup, and the hook
    reported `vitest failures` for tests that never ran. That blocked every push
    touching the SLM frontend, and ALLOW_UNRUNNABLE could not apply, because the
    hook had called it a failure. A run with no "Test Files" summary is COULD NOT
    RUN; a run that reports test files, failed or passed, is unchanged.
    """

    @staticmethod
    def _ran_nothing(output: str) -> bool:
        match = _RAN_NOTHING.search(_source())
        assert match, "the hook no longer defines vitest_ran_nothing — move this test with it, do not delete it"
        script = f'{match.group(0)}\nvitest_ran_nothing "$(cat)"'
        completed = subprocess.run(["bash", "-c", script], input=output, capture_output=True, text=True, check=False)
        return completed.returncode == 0

    def test_a_startup_death_ran_nothing(self) -> None:
        assert self._ran_nothing(_STARTUP_DEATH)

    def test_a_real_test_failure_is_still_a_failure(self) -> None:
        assert not self._ran_nothing(_REAL_FAILURE)

    def test_a_passing_run_ran_something(self) -> None:
        assert not self._ran_nothing(_REAL_PASS)

    def test_a_crash_after_a_failure_is_still_a_failure(self) -> None:
        # A killed worker can lose the summary; the FAIL line it already printed must count.
        crashed = " FAIL  src/composables/__tests__/useThing.test.ts > adds\nError: Worker exited unexpectedly\n"
        assert not self._ran_nothing(crashed)

    def test_the_new_branch_only_fires_on_a_non_zero_exit(self) -> None:
        source = _source()
        assert (
            'elif [ "$vitest_exit" != "0" ] && vitest_ran_nothing "$vitest_output"; then' in source
        ), "the could-not-run branch lost its non-zero-exit guard — a clean run could be reported as unrunnable"

    def test_the_could_not_run_branch_is_checked_before_the_failure_branch(self) -> None:
        source = _source()
        could_not = source.find('vitest_ran_nothing "$vitest_output"')
        failure = source.find('fail "vitest failures')
        assert could_not != -1 and failure != -1, "a branch moved — move this test with it"
        assert could_not < failure, "a startup death would be reported as `vitest failures` again"
