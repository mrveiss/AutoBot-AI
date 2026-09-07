#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14405, #15914 — no tracked Python file may reference a name it never binds.

An undefined name is a live ``NameError`` waiting on the code path that reaches
it, not a style preference. Twelve operator scripts in this tree carried 103 of
them — a module logger assigned inside a docstring, ``requests``/``psutil``/
``numpy``/``aiohttp`` used and never imported, a shell ``${VAR:-default}``
substituted into an f-string, and a function-length pass that sliced one
coroutine into eight argument-less helpers, each reading locals the others had
carried away.

#15914 WIDENED THIS FROM ONE TREE TO THE REPO, because scoping the guard to the
tree where the defect was found reproduces the thing that hid it. The 2026-02
version covered ``autobot-infrastructure/shared/scripts/`` and nothing else, so
five classes in ``autobot-backend/code_analysis/`` — the second tree named in
the same exclusion this guard exists to work around — kept a ``self.config =
config`` whose import had been dropped, and raised ``NameError`` on every
construction for six to nine months. ``CodeQualityDashboard`` and its three
entry-point scripts were never runnable in this repo. A guard bounded by the
exclusion that caused the defect can only ever find the instance you already
knew about.

The sweep is now every tracked ``*.py`` and there is no tree list to keep
current: a directory added tomorrow is covered without anyone remembering.

WHY NOTHING CAUGHT THEM. Three independent exclusions cover these trees and none
was the #14419 depth bug:

* ``.pre-commit-config.yaml``'s flake8 hook carries
  ``exclude: ^(tests/|autobot-infrastructure/|autobot-backend/code_analysis/)``.
  It is correctly anchored and excludes those three trees on purpose, so the
  hook reports ``(no files to check) Skipped`` — exit 0 — for a file full of
  undefined names.
* ``.flake8``'s own ``exclude`` names ``autobot-backend/code_analysis/`` and the
  test trees as well.
* The one CI flake8 invocation (``security.yml``) runs with ``|| true`` and
  writes a report. It cannot fail a build, and 8 undefined names sit under
  23,758 ``E501``\ s in it — present, counted, and invisible.

``.flake8``'s ``exclude`` is beside the point for this module: flake8 only
applies it while recursing, so an explicitly-named file under an excluded tree
IS linted. Naming the files is what turns the check on, and this module is what
names them.

WHY A REQUIRED CHECK AND NOT ONLY A HOOK OR A TEST. A pre-commit hook sees
staged files only, so it can never prove the whole tree is clean, and the pytest
copy runs in ``python-suite``, which gates nothing (#14353). The direction of
this failure is what makes placement matter: re-widening the exclusion lints
*fewer* files, so every lint job reports fewer violations and goes greener.
``.github/workflows/code-quality.yml`` — a required check — therefore calls this
module with ``--audit``, the same shape as ``check_flake8_exclude_anchoring.py
--audit-excludes`` and ``check_python_file_size.py --audit-ceilings``.

THERE IS NO EXEMPTION LIST, DELIBERATELY. Grandfathering an undefined name would
make the defect this guard exists for permanently exempt while looking covered
(#14405). The other flake8 codes (E501, F841, F401, F541, E741) are a separate,
cosmetic backlog and stay out of scope — this selects F821 only, so the gate is
F821-clean repo-wide today with nothing to ratchet.

The audit reports how many files it reached and fails below a floor, because a
sweep handed an empty file list reports a comfortable zero that is
indistinguishable from success. The floor is bound to files *examined*, never to
findings, and the file list comes from ``git ls-files`` rather than from the
lint configuration — a denominator drawn from the mechanism under test cannot
show that mechanism going missing (#15908).
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import subprocess  # nosec B404  # fixed argv, no shell, paths come from the repo tree
import sys

import yaml

# Plain stdlib logging, deliberately (#1082). This runs as a bare script inside a
# lint job, and `autobot_shared.logging_manager` would drag config loading into
# that path. Same trade as `tools/lint/check_flake8_exclude_anchoring.py`; it is
# what CLAUDE.md's pattern table allows for exactly this case.
logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_undefined_names.py"

#: pyflakes code for "undefined name". Only this one: see the module docstring.
SELECTED_CODE = "F821"

#: Floor for the audit's own discovery. The repo held 5,567 tracked ``*.py``
#: files when #15914 widened this sweep from one tree to all of them; a run that
#: suddenly reaches a few hundred has broken, and a clean result from it asserts
#: nothing. Bound to files examined, never to findings — a floor that tracked
#: findings would relax itself as the tree improved.
DISCOVERY_FLOOR = 5_000

#: pre-commit config, whose flake8 hooks decide what a commit is allowed to
#: contain. The audit re-proves that they still reach every tracked file.
PRE_COMMIT_CONFIG_REL = ".pre-commit-config.yaml"

#: Cap on how many uncovered paths a gate failure lists before it summarises, so
#: a hook that stops reaching thousands of files does not bury its own message.
_MAX_LISTED = 15


def repo_root() -> pathlib.Path:
    """Repo root, derived from this file's location (``tools/lint/`` is two deep)."""
    return pathlib.Path(__file__).resolve().parents[2]


def discover_scripts(base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every tracked ``*.py`` in the repo, other checkouts' worktrees aside.

    Read from ``git ls-files`` rather than from the lint configuration on
    purpose: those exclusions are what this guard exists to work around, so a
    file list derived from them could never show a tree falling out of coverage.
    A denominator drawn from the mechanism under test cannot show that mechanism
    going missing — ``git`` and the linter must be able to disagree (#15908).
    """
    base = base or repo_root()
    completed = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=str(base),
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        base / name
        for name in completed.stdout.split("\n")
        if name and not name.startswith(".worktrees/") and "__pycache__" not in name
    ]


def undefined_name_findings(paths: list[pathlib.Path], base: pathlib.Path | None = None) -> list[str]:
    """Every ``F821`` flake8 reports for *paths*, one finding per line.

    ``--isolated``: the repo's ``.flake8`` sets ``count``/``statistics`` for the
    pre-commit hook's human-readable output, which appends a bare count line
    after the real violations. Reading it here would make every clean file look
    broken (its trailing ``0``), and ``show-source`` would interleave source
    echoes that parse as findings too.
    """
    if not paths:
        return []
    result = subprocess.run(  # nosec B603  # fixed argv, no shell, repo-tree paths
        [sys.executable, "-m", "flake8", "--isolated", f"--select={SELECTED_CODE}", *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        cwd=str(base or repo_root()),
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"flake8 failed to run ({result.returncode}): {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _hook_receives(hook: dict, path: str) -> bool:
    """Replay pre-commit's include/exclude filtering for one hook and one path."""
    files = hook.get("files") or ""
    exclude = hook.get("exclude") or "^$"
    return bool(re.search(files, path)) and not re.search(exclude, path)


def _hook_enforces_undefined_names(hook: dict) -> bool:
    """True unless the hook's own args select F821 away.

    No ``--select`` at all means the full ruleset, which includes F821 — that is
    an enforcing hook, not a gap.
    """
    args = [str(a) for a in (hook.get("args") or [])]
    for arg in args:
        for flag in ("--ignore=", "--extend-ignore="):
            if arg.startswith(flag) and any(
                SELECTED_CODE.startswith(code.strip()) for code in arg.split("=", 1)[1].split(",") if code.strip()
            ):
                return False
        if arg.startswith("--select="):
            return any(SELECTED_CODE.startswith(code.strip()) for code in arg.split("=", 1)[1].split(","))
    return True


def commit_gate_problems(base: pathlib.Path | None = None) -> list[str]:
    """Re-prove that some pre-commit flake8 hook lints EVERY tracked file for F821.

    Fixing the files by hand while the trees stayed excluded would have left
    nothing stopping the next one (#14405) — and that is not hypothetical: the
    2026-02 version of this guard proved coverage of one tree with a single
    probe path, and five classes in a *different* excluded tree stayed dead for
    months (#15914). One probe answers "is this tree covered", never "is
    anything uncovered".

    So the question is asked of every discovered path. Replaying pre-commit's
    own include/exclude selection, rather than asserting on the regex text: the
    text test passes a rewritten-but-equivalent regex and fails a stricter one,
    while the replay asks what actually matters — would any enforcing hook be
    handed this file?
    """
    base = base or repo_root()
    config_path = base / PRE_COMMIT_CONFIG_REL
    if not config_path.is_file():
        return [f"{PRE_COMMIT_CONFIG_REL} is missing — the commit-time gate cannot be verified."]

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    hooks = [hook for repo in config.get("repos", []) for hook in repo.get("hooks", []) if hook.get("id") == "flake8"]
    if not hooks:
        return [f"{PRE_COMMIT_CONFIG_REL} declares no flake8 hook at all — nothing lints Python on commit."]

    enforcing = [hook for hook in hooks if _hook_enforces_undefined_names(hook)]
    if not enforcing:
        return [
            f"all {len(hooks)} flake8 hook(s) in {PRE_COMMIT_CONFIG_REL} select {SELECTED_CODE} "
            "away, so an undefined name commits cleanly (#14405)."
        ]

    uncovered = [
        str(path.relative_to(base))
        for path in discover_scripts(base)
        if not any(_hook_receives(hook, str(path.relative_to(base))) for hook in enforcing)
    ]
    if uncovered:
        listed = "\n".join(f"  {name}" for name in uncovered[:_MAX_LISTED])
        more = f"\n  ... and {len(uncovered) - _MAX_LISTED} more" if len(uncovered) > _MAX_LISTED else ""
        return [
            f"{len(uncovered)} tracked Python file(s) are reached by no flake8 hook that "
            f"enforces {SELECTED_CODE}:\n{listed}{more}\n\n"
            f"An undefined name in any of them commits cleanly. That is the state that let "
            f"103 undefined names accumulate in one tree (#14405) and five dead constructors "
            f"in another (#15914). Widen a hook's `files:` or narrow its `exclude:` in "
            f"{PRE_COMMIT_CONFIG_REL} — do not narrow this sweep to match."
        ]

    return []


def audit(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Sweep the whole tree. Returns (files reached, problems)."""
    base = base or repo_root()
    problems: list[str] = []

    scripts = discover_scripts(base)
    if len(scripts) < DISCOVERY_FLOOR:
        problems.append(
            f"discovery returned only {len(scripts)} tracked Python file(s) "
            f"(floor {DISCOVERY_FLOOR}) — the sweep broke, so a clean result below "
            "would assert nothing."
        )

    problems.extend(commit_gate_problems(base))

    findings = undefined_name_findings(scripts, base)
    if findings:
        problems.append(
            "undefined names (a NameError waiting on the code path that reaches "
            "them):\n"
            + "\n".join(findings)
            + f"\n\nImport or define each name — or delete the reference if, as in "
            "#15914, the assignment has been dead since its import was dropped. "
            f"{SELF_REL} carries no exemption list on purpose (#14405): "
            "grandfathering an undefined name would make the defect this guard "
            "exists for permanently exempt while looking covered."
        )

    return len(scripts), problems


def check_files(paths: list[str], base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Check the given *paths* (pre-commit's entry).

    Returns (files reached, problems). An empty selection is a legitimate zero
    here — pre-commit's ``files:`` regex has already narrowed the list — which is
    exactly why :func:`audit` and not this function is what the required check
    runs. A hook sees staged files only and can never prove the repo is clean.
    """
    base = base or repo_root()
    selected = [pathlib.Path(raw) if pathlib.Path(raw).is_absolute() else base / raw for raw in paths]
    findings = undefined_name_findings(selected, base)
    problems = []
    if findings:
        problems.append(
            "undefined names in the staged scripts:\n"
            + "\n".join(findings)
            + "\n\nImport or define each name — an undefined name is a live NameError (#14405)."
        )
    return len(selected), problems


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the module logger has no handler, and logging's
    last-resort path drops anything below WARNING.
    """
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="sweep every tracked Python file, not only the paths given",
    )
    parser.add_argument("paths", nargs="*", help="files to check (pre-commit passes these)")
    args = parser.parse_args(argv)

    if args.audit:
        reached, problems = audit()
        scope = f"{reached} tracked Python file(s)"
    elif args.paths:
        reached, problems = check_files(args.paths)
        scope = f"{reached} staged file(s)"
    else:
        parser.error("nothing to do — pass --audit or one or more paths")

    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nundefined-name audit FAILED over %s (#14405, #15914).", scope)
        return 1
    logger.info("undefined-name audit clean over %s (#14405, #15914).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
