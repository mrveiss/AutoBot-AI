# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17137: a PRE-FLIGHT task may not run a script out of the installed tree.

#16310 added a ``[PRE-FLIGHT] Ensure code_source has full history`` task that
called ``sync_deletion_planner.py`` by its INSTALLED path. Pre-flight runs
before the deploy step that refreshes that install, so on any node whose
install predated #16310 the interpreter found an older script with no
``ensure-full-history`` subcommand, argparse exited 2, and the whole play
aborted -- a first-run failure that could not be fixed by re-running, because
the thing that would install the fix was the step being gated.

Asserted on the property rather than on that one subcommand: a pre-flight task
may only execute code from the tree the sync just refreshed
(``{{ git_repo_root }}``), never from the install directory, so the next
subcommand added to a pre-flight script cannot reintroduce this silently.

The later ``roles/_shared/tasks/sync_deletions.yml`` call sites are deliberately
out of scope -- they run after the deploy, when the installed copy IS current.

Lives in ``repo_tests/`` because CI's shard command passes an explicit path list
and ``autobot-slm-backend/ansible`` is not on it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK_DIR = REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks"

#: The three plays that carry pre-flight tasks (#16310, #17137).
_PLAYBOOKS = (
    "provision-fleet-roles.yml",
    "pre-flight-code-sync.yml",
    "update-all-nodes.yml",
)

#: A task name marks the pre-flight phase; everything under it until the next
#: ``- name:`` belongs to that task.
_TASK_NAME_RE = re.compile(r"^\s*-\s*name:\s*(.+?)\s*$")

#: Any absolute path into the install tree. `autobot.base_dir` renders to the
#: same place, so a task that dodges the literal by templating the variable is
#: caught too -- what matters is which tree the code comes from, not its spelling.
_INSTALLED_TREE_RE = re.compile(r"(/opt/autobot/|\{\{\s*autobot\.base_dir\s*\}\})")

#: Only the SCRIPT matters, not the interpreter. Two deliberate exclusions:
#: `--repo-root /opt/autobot/code_source` is an argument naming the directory to
#: operate on, which is exactly what these tasks are for; and the installed
#: venv's `bin/python3` is the interpreter, which pre-flight has no alternative
#: to and which the failure in #17137 was not about -- argparse rejected the
#: subcommand because the SCRIPT was old, not because the interpreter was.
_EXECUTABLE_LINE_RE = re.compile(r"\.(py|sh)\b")


def _preflight_task_bodies(path: Path) -> list[tuple[str, list[str]]]:
    """(task name, its lines) for every task whose name starts with [PRE-FLIGHT]."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        match = _TASK_NAME_RE.match(line)
        if match:
            starts.append((i, match.group(1)))
    found = []
    for n, (start, name) in enumerate(starts):
        if not name.lstrip("\"'").startswith("[PRE-FLIGHT]"):
            continue
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        found.append((name, lines[start:end]))
    return found


def test_no_preflight_task_executes_code_from_the_installed_tree() -> None:
    offenders: list[str] = []
    seen = 0
    for filename in _PLAYBOOKS:
        path = PLAYBOOK_DIR / filename
        assert path.is_file(), f"playbook missing, this guard's scope is stale: {filename}"
        for name, body in _preflight_task_bodies(path):
            seen += 1
            for line in body:
                if _INSTALLED_TREE_RE.search(line) and _EXECUTABLE_LINE_RE.search(line):
                    offenders.append(f"{filename}: {name.strip()}\n      {line.strip()}")

    # A scan that finds nothing because it looked at nothing is the failure this
    # guard exists to avoid reporting as a pass (MEASUREMENT_DISCIPLINE.md).
    assert seen >= len(_PLAYBOOKS), f"only {seen} pre-flight tasks found across {len(_PLAYBOOKS)} playbooks -- the scan is broken"

    assert not offenders, (
        "a PRE-FLIGHT task executes code from the install tree, which the deploy it gates has not "
        "refreshed yet (#17137) -- run it from {{ git_repo_root }} instead:\n  " + "\n  ".join(offenders)
    )
