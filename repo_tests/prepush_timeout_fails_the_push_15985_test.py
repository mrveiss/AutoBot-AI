# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pre-push check that times out must FAIL the push, not warn and exit zero (#15985).

The gate's coverage used to be inversely proportional to the risk of the push: a
fixed 120s budget meant a two-file change was verified and a 162-file change timed
out, and `WARN ... skipping` followed by exit 0 spells "did not run" exactly like
"ran and passed". Three sessions pushed unverified changesets this way, and the
only reason anyone noticed was one author reading which line the hook printed
rather than its exit code.

These tests EXECUTE the helper rather than inspecting the script's text, because
the defect was never in what the script said -- it said `skipping`, accurately --
but in what the exit code did afterwards. Grepping for the word would have found
the old code and the new code equally.
"""

from __future__ import annotations

import subprocess

from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"

#: Sources the hook far enough to define its helpers without running the gate, then
#: exercises one path. The hook guards its body behind the `while read` over stdin,
#: so sourcing with no stdin defines functions and does nothing else.
_HARNESS = """
set -uo pipefail
EXIT_CODE=0
RED=''; YEL=''; GRN=''; BLU=''; CLR=''
warn()  {{ printf "[WARN] %s\\n" "$*" >&2; }}
log()   {{ :; }}
ALLOW_TIMEOUT="${{AUTOBOT_PREPUSH_ALLOW_TIMEOUT:-0}}"
{body}
did_not_run "pytest" "120"
echo "EXIT_CODE=$EXIT_CODE"
"""


def _did_not_run_body() -> str:
    """The helper's source, lifted from the hook so the test runs the real thing."""
    text = _HOOK.read_text(encoding="utf-8")
    start = text.index("did_not_run() {")
    end = text.index("\n}", start) + 2
    return text[start:end]


def _run(env_extra: dict[str, str] | None = None) -> str:
    script = _HARNESS.format(body=_did_not_run_body())
    import os

    env = dict(os.environ)
    env.pop("AUTOBOT_PREPUSH_ALLOW_TIMEOUT", None)
    env.update(env_extra or {})
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
    return result.stdout + result.stderr


def test_a_timeout_sets_a_failing_exit_code():
    """The regression: a timeout used to leave EXIT_CODE at 0 and the push proceeded."""
    output = _run()
    assert "EXIT_CODE=1" in output, f"a timed-out check did not fail the push:\n{output}"


def test_the_timeout_message_does_not_read_like_a_pass():
    """`WARN ... skipping` is the shape that made "did not run" look like "ran"."""
    output = _run()
    assert "DID NOT RUN" in output, f"the timeout message does not say it did not run:\n{output}"
    assert "NOT verified" in output


def test_the_opt_out_works_and_names_itself():
    """An escape hatch invisible in the transcript is indistinguishable from the bug."""
    output = _run({"AUTOBOT_PREPUSH_ALLOW_TIMEOUT": "1"})
    assert "EXIT_CODE=0" in output, f"the opt-out did not permit the push:\n{output}"
    assert "AUTOBOT_PREPUSH_ALLOW_TIMEOUT=1" in output, (
        "the opt-out did not name itself in the output, so a reader of the transcript "
        "cannot tell an allowed-unverified push from a verified one"
    )


def test_the_budget_scales_with_the_changeset():
    """A fixed budget is what made coverage inversely proportional to risk."""
    text = _HOOK.read_text(encoding="utf-8")
    assert "changed_count" in text and "TEST_TIMEOUT + (changed_count" in text, (
        "the test budget no longer scales with the changeset; a large push will time "
        "out again and, with the fix above, will now be blocked rather than skipped"
    )
