#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550 post-merge incident — a composite action step key GitHub silently rejects.

A composite action's own ``runs.steps`` accept only ``run``, ``shell``,
``working-directory``, ``env``, ``id``, ``if``, ``name`` (plus ``uses``/``with``
for a step that calls another action). ``timeout-minutes`` — valid on a *job*,
and on a *workflow* step — is NOT valid there. Adding it to one step of
``.github/actions/setup-python-suite/action.yml`` made GitHub's template
validator reject the WHOLE file before a single step ran:

.. code-block:: text

    ##[error]/.github/actions/setup-python-suite/action.yml (Line: 56, Col: 7):
    Unexpected value 'timeout-minutes'
    ##[error]GitHub.DistributedTask.ObjectTemplating.TemplateValidationException:
    The template is not valid.

Every shard that used the action failed identically, not only the one the
change was meant to protect — and nothing local caught it. ``code-quality``
installs linters, not a YAML-schema validator for GitHub's own template
engine, and no unit test in this repo executes a composite action the way
GitHub's runner does. The gap is real: only GitHub's own server-side
validation, at workflow-run time, would have caught this before this guard
existed.

This does not depend on ``actionlint`` or any other external tool being
installed — it re-implements the (small, stable) allowed-key set as a plain
Python check, so ``code-quality`` (linters only, no application deps, no
network) can catch it before a push ever reaches a runner.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The failure direction needs a
REQUIRED check: a composite action gaining a new step, or an existing step
gaining an unsupported key, both make this scan find nothing to report
*unless it re-derives the allowed-key set correctly on every run* — nothing
about a merely-informational pytest run would block the push that breaks
every shard using the action. ``.github/workflows/code-quality.yml`` calls
this module with ``--audit``. ``repo_tests/ci_system_package_provisioning_test.py``
carries a narrower, pre-existing pin on ``setup-python-suite/action.yml``
specifically; this module generalises the check to every composite action in
the repo, present and future.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys

# Plain stdlib logging (matching the other tools/lint/check_*.py modules in
# this repo): runs inside `code-quality`, which installs linters only.
logger = logging.getLogger(__name__)

#: Keys GitHub's template validator accepts on a COMPOSITE ACTION'S OWN step.
#: Anything else (`timeout-minutes`, `continue-on-error`, ...) is a workflow-
#: or job-level key that happens to look plausible on a step, and silently
#: invalidates the WHOLE action.yml, not just the offending step.
ALLOWED_STEP_KEYS = frozenset({"name", "run", "shell", "working-directory", "env", "id", "if", "uses", "with"})

#: Glob, relative to the repo root, for every composite action definition.
_ACTION_GLOB = ".github/actions/*/action.yml"

#: This checker's own guard-reach declaration (see
#: tools/lint/check_code_quality_guard_reach.py) -- the glob itself, since the
#: exact set of composite actions changes over time and the filter must cover
#: the DIRECTORY, not today's snapshot of files in it.
GUARD_INPUT_PATHS = (_ACTION_GLOB,)

#: Minimal YAML mapping-key extractor for one step-list item. Deliberately
#: not a real YAML parser (code-quality installs no third-party YAML lib):
#: this only needs the TOP-LEVEL key names of each `- key: value` block
#: under `runs.steps`, which line-anchored regexes are sufficient for given
#: this repo's consistent 4-space step indentation. Two separate patterns,
#: not one: this repo's own style inlines the first key on the dash line
#: itself (`    - uses: actions/checkout@v7`), which a single "N-to-M spaces
#: then a key" pattern would miss entirely -- silently dropping exactly the
#: key this checker exists to catch, if it were ever written as the first
#: (dash-line) key of a step instead of a later line.
_STEP_START_RE = re.compile(r"^ {4}- ")
_INLINE_KEY_RE = re.compile(r"^ {4}- ([A-Za-z][A-Za-z0-9_-]*):")
_CONT_KEY_RE = re.compile(r"^ {6}([A-Za-z][A-Za-z0-9_-]*):")
_RUNS_STEPS_RE = re.compile(r"^runs:\s*$")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def action_files(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    base = root if root is not None else repo_root()
    return sorted(base.glob(_ACTION_GLOB))


def step_key_sets(text: str) -> list[set[str]]:
    """One ``set[str]`` of top-level keys per step under ``runs: / steps:``.

    Scoped to lines at 4- or 6-space step indentation so a same-named key
    inside a nested ``with:`` block (indented deeper still) is never
    mistaken for a step-level key.
    """
    lines = text.splitlines()
    steps: list[set[str]] = []
    in_runs = False
    for line in lines:
        if _RUNS_STEPS_RE.match(line):
            in_runs = True
            continue
        if not in_runs:
            continue
        if _STEP_START_RE.match(line):
            steps.append(set())
            inline = _INLINE_KEY_RE.match(line)
            if inline:
                steps[-1].add(inline.group(1))
            continue
        if steps:
            cont = _CONT_KEY_RE.match(line)
            if cont:
                steps[-1].add(cont.group(1))
    return steps


def offending_keys(steps: list[set[str]]) -> list[set[str]]:
    """Per-step key sets that include something outside ALLOWED_STEP_KEYS."""
    return [keys - ALLOWED_STEP_KEYS for keys in steps if keys - ALLOWED_STEP_KEYS]


def audit_composite_actions(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant to every composite action. Returns ``(steps_checked, problems)``."""
    base = root if root is not None else repo_root()
    files = action_files(base)
    if not files:
        return 0, [f"{_ACTION_GLOB} matched zero files — the guard checked nothing."]

    total_steps = 0
    problems: list[str] = []
    for path in files:
        steps = step_key_sets(path.read_text(encoding="utf-8"))
        if not steps:
            problems.append(f"{path.relative_to(base)}: parsed zero steps under `runs:` — the parser may be stale.")
            continue
        total_steps += len(steps)
        bad = offending_keys(steps)
        if bad:
            problems.append(
                f"{path.relative_to(base)}: step key(s) not valid on a composite action's own steps: {bad}. "
                "GitHub's template validator rejects the WHOLE file for this — one offending key breaks every "
                "step, on every job that uses this action (#14550)."
            )

    return total_steps, problems


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    reached, problems = audit_composite_actions()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\ncomposite-action step-key audit FAILED over %d step(s) (#14550).", reached)
        return 1
    logger.info("composite-action step-key audit clean over %d step(s) (#14550).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="verify every composite action's steps use only GitHub-supported keys",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.error("nothing to do — pass --audit")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
