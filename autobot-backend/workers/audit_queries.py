# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""External queries the audit worker makes, and whether they observed anything (#13570).

The incident this module exists for: `gh` was unauthenticated for the service
account, so audit findings came back "deferred to the dead-letter queue" while
the queue held nothing. The reassuring message was worse than an error, because
it stated the findings were preserved when they were not.

The same shape survived one level down, in the queries the tasks make *before*
they file. Both returned an empty list on failure — the identical value a
successful query returns when there is genuinely nothing:

* `gh issue list` failing returned `[]`, which empties the dedupe set. A run that
  could not see the open issues then looked exactly like a run against a repo
  with no open issues, and would happily re-file every finding already filed;
* `vulture` failing to start returned `[]`, and the task reported
  `total_findings: 0`, `new_findings: 0`, `status: "success"` — a clean bill of
  health from a scan that never ran.

Every function here therefore returns ``(result, observed)``. ``observed`` is
False whenever the query did not actually happen, and callers must treat that as
"no information", never as "no findings".

Both take the subprocess runner as an argument rather than importing it, so the
worker keeps a single canonical ``_run`` and these stay independently testable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Max characters of CLI output kept in logs on failure.
MAX_LOG_CHARS = 500

# (returncode, stdout, stderr)
Runner = Callable[..., "tuple[int, str, str]"]


def _tail(text: str) -> str:
    """The trimmed CLI output, or an explicit note that there was none."""
    return (text or "").strip()[:MAX_LOG_CHARS] or "no output"


def list_open_issue_titles(
    repo: str,
    label: str | None,
    env: dict[str, str],
    runner: Runner,
) -> tuple[list[str], bool]:
    """Titles of open GitHub issues, and whether the listing actually happened.

    ``(titles, observed)``. ``observed`` False means the caller is BLIND to
    duplicates for this run — it must not conclude "nothing is open" and file
    everything again.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--json",
        "title",
        "--limit",
        "500",
    ]
    if label:
        cmd += ["--label", label]
    code, out, err = runner(cmd, env=env)
    if code != 0:
        logger.error(
            "audit: `gh issue list` for %s exited %d — this run cannot see which "
            "issues are already open, so it is blind to duplicates and will defer "
            "rather than re-file. gh said: %s",
            repo,
            code,
            _tail(err),
        )
        return [], False
    try:
        return [item["title"] for item in json.loads(out)], True
    except (ValueError, TypeError, KeyError) as exc:
        logger.error(
            "audit: `gh issue list` for %s returned output this worker cannot read "
            "(%s) — treating the listing as unobserved rather than as an empty repo.",
            repo,
            type(exc).__name__,
        )
        return [], False


def vulture_scan(repo_root: Path, runner: Runner, python_executable: str) -> tuple[list[str], bool]:
    """Dead-code lines from vulture, and whether the scan actually ran.

    vulture exits 0 when it finds nothing and 1 when it finds dead code. Exit 1
    with an EMPTY stdout is neither outcome: it is the interpreter refusing to
    run the module at all — not installed, or an import error inside it. That
    case used to return the same empty list a clean scan returns, and the task
    reported success for a scan that never happened.
    """
    cmd = [
        python_executable,
        "-m",
        "vulture",
        "autobot-backend",
        "--min-confidence",
        "80",
        "--exclude",
        "*/migrations/*,*/__pycache__/*,*/tests/*",
    ]
    code, out, err = runner(cmd, cwd=str(repo_root))
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if code not in (0, 1) or (code == 1 and not lines):
        logger.error(
            "audit: vulture could not run (exit %d) — this run made NO dead-code "
            "observation, which is not the same as finding none. vulture said: %s",
            code,
            _tail(err),
        )
        return [], False
    return lines, True
