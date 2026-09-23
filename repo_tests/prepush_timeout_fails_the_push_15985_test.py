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

import os
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
exit "$EXIT_CODE"
"""


def _did_not_run_body() -> str:
    """The helper's source, lifted from the hook so the test runs the real thing."""
    text = _HOOK.read_text(encoding="utf-8")
    start = text.index("did_not_run() {")
    end = text.index("\n}", start) + 2
    return text[start:end]


def _run(env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the harness and hand back the PROCESS, not a transcript of it.

    Returning `stdout + stderr` was the same defect these tests exist to catch,
    one level up: the harness ended in `echo`, so `bash -c` exited 0 however
    `did_not_run` had set `EXIT_CODE`, and every assertion read a line of text
    *about* the exit status instead of the status. A test for "the push fails"
    that cannot observe a failing process is checking the message again.
    """
    script = _HARNESS.format(body=_did_not_run_body())
    env = dict(os.environ)
    env.pop("AUTOBOT_PREPUSH_ALLOW_TIMEOUT", None)
    env.update(env_extra or {})
    return subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _text(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_a_timeout_fails_the_push():
    """The regression: a timeout used to leave EXIT_CODE at 0 and the push proceeded."""
    result = _run()
    assert result.returncode != 0, (
        f"a timed-out check exited {result.returncode} -- the push was permitted:\n{_text(result)}"
    )
    assert "EXIT_CODE=1" in _text(result)


def test_the_timeout_message_does_not_read_like_a_pass():
    """`WARN ... skipping` is the shape that made "did not run" look like "ran"."""
    output = _text(_run())
    assert "DID NOT RUN" in output, f"the timeout message does not say it did not run:\n{output}"
    assert "NOT verified" in output


def test_the_opt_out_works_and_names_itself():
    """An escape hatch invisible in the transcript is indistinguishable from the bug."""
    result = _run({"AUTOBOT_PREPUSH_ALLOW_TIMEOUT": "1"})
    output = _text(result)
    assert result.returncode == 0, f"the opt-out did not permit the push:\n{output}"
    assert "EXIT_CODE=0" in output
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
