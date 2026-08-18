#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14405 — no script under ``autobot-infrastructure/shared/scripts/`` may reference a name it never binds.

An undefined name is a live ``NameError`` waiting on the code path that reaches
it, not a style preference. Twelve operator scripts in this tree carried 103 of
them — a module logger assigned inside a docstring, ``requests``/``psutil``/
``numpy``/``aiohttp`` used and never imported, a shell ``${VAR:-default}``
substituted into an f-string, and a function-length pass that sliced one
coroutine into eight argument-less helpers, each reading locals the others had
carried away.

WHY NOTHING CAUGHT THEM. Two independent exclusions cover this tree and neither
was the #14419 depth bug:

* ``.pre-commit-config.yaml``'s flake8 hook carries
  ``exclude: ^(tests/|autobot-infrastructure/|autobot-backend/code_analysis/)``.
  It is correctly anchored and excludes ``autobot-infrastructure/`` on purpose,
  so the hook reports ``(no files to check) Skipped`` — exit 0 — for a file full
  of undefined names.
* No CI flake8 invocation passes this tree as an argument. ``.flake8``'s own
  ``exclude`` is beside the point here: flake8 only applies it while recursing,
  so an explicitly-named file under an excluded tree IS linted. Narrowing the
  pre-commit regex is therefore what turns the check on, and this module is what
  the narrowed scope runs.

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
(#14405). Other flake8 codes in this tree (E501, F841, F401, F541, E741) are a
separate, cosmetic backlog and stay out of scope — this selects F821 only, so
the gate is F821-clean today with nothing to ratchet.

The audit reports how many files it reached and fails below a floor, because a
sweep handed an empty file list reports a comfortable zero that is
indistinguishable from success.
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
SELF_REL = "tools/lint/check_infra_scripts_undefined_names.py"

#: The tree this guard covers, repo-relative.
SCRIPTS_DIR_REL = "autobot-infrastructure/shared/scripts"

#: pyflakes code for "undefined name". Only this one: see the module docstring.
SELECTED_CODE = "F821"

#: Floor for the audit's own discovery. The tree held 222 scripts when this
#: landed; a sweep that suddenly reaches a handful has broken, and a clean
#: result from it asserts nothing.
DISCOVERY_FLOOR = 100

#: pre-commit config, whose flake8 hooks decide what a commit is allowed to
#: contain. The audit re-proves that one of them still reaches this tree.
PRE_COMMIT_CONFIG_REL = ".pre-commit-config.yaml"

#: A real file in the guarded tree, used to replay pre-commit's own file
#: selection. Asserting on the regex text would pass a rewritten-but-equivalent
#: regex and fail a stricter one; replaying the selection asks the question that
#: actually matters — would this hook be handed a script from this tree?
PROBE_REL = f"{SCRIPTS_DIR_REL}/diagnose_backend.py"


def repo_root() -> pathlib.Path:
    """Repo root, derived from this file's location (``tools/lint/`` is two deep)."""
    return pathlib.Path(__file__).resolve().parents[2]


def scripts_dir(base: pathlib.Path | None = None) -> pathlib.Path:
    return (base or repo_root()) / SCRIPTS_DIR_REL


def discover_scripts(base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every ``*.py`` under the guarded tree, ``__pycache__`` aside."""
    return sorted(p for p in scripts_dir(base).rglob("*.py") if "__pycache__" not in p.parts)


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
    """Re-prove that some pre-commit flake8 hook still lints this tree for F821.

    Fixing the 12 files by hand while the tree stayed excluded would have left
    nothing stopping a 13th (#14405). That protection lives in a regex in another
    file, so it can be widened back in one line, by someone with no reason to
    connect the edit to this tree — which is precisely the regression this
    function exists to fail on.
    """
    base = base or repo_root()
    config_path = base / PRE_COMMIT_CONFIG_REL
    if not config_path.is_file():
        return [f"{PRE_COMMIT_CONFIG_REL} is missing — the commit-time gate cannot be verified."]

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    hooks = [hook for repo in config.get("repos", []) for hook in repo.get("hooks", []) if hook.get("id") == "flake8"]
    if not hooks:
        return [f"{PRE_COMMIT_CONFIG_REL} declares no flake8 hook at all — nothing lints Python on commit."]

    reaching = [hook for hook in hooks if _hook_receives(hook, PROBE_REL)]
    if not reaching:
        return [
            f"no flake8 hook in {PRE_COMMIT_CONFIG_REL} is handed {PROBE_REL}: every one of "
            f"{len(hooks)} either does not match it or excludes it. The tree is back to "
            f"unlinted, which is the state that let 103 undefined names accumulate (#14405). "
            f"Restore a hook scoped to {SCRIPTS_DIR_REL} with --select={SELECTED_CODE}."
        ]

    if not any(_hook_enforces_undefined_names(hook) for hook in reaching):
        return [
            f"{len(reaching)} flake8 hook(s) in {PRE_COMMIT_CONFIG_REL} reach {PROBE_REL}, but each "
            f"selects {SELECTED_CODE} away, so an undefined name still commits cleanly (#14405)."
        ]

    return []


def audit(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Sweep the whole tree. Returns (files reached, problems)."""
    base = base or repo_root()
    problems: list[str] = []

    directory = scripts_dir(base)
    if not directory.is_dir():
        return 0, [f"{SCRIPTS_DIR_REL} does not exist — the tree moved, so {SELF_REL} now guards nothing."]

    scripts = discover_scripts(base)
    if len(scripts) < DISCOVERY_FLOOR:
        problems.append(
            f"discovery returned only {len(scripts)} script(s) under {SCRIPTS_DIR_REL} "
            f"(floor {DISCOVERY_FLOOR}) — the sweep broke, so a clean result below "
            "would assert nothing."
        )

    problems.extend(commit_gate_problems(base))

    findings = undefined_name_findings(scripts, base)
    if findings:
        problems.append(
            "undefined names (a NameError waiting on the code path that reaches "
            "them) under "
            + SCRIPTS_DIR_REL
            + ":\n"
            + "\n".join(findings)
            + f"\n\nImport or define each name. {SELF_REL} carries no exemption list "
            "on purpose (#14405): grandfathering an undefined name would make the "
            "defect this guard exists for permanently exempt while looking covered."
        )

    return len(scripts), problems


def check_files(paths: list[str], base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Check the subset of *paths* that lie in the guarded tree (pre-commit's entry).

    Returns (files reached, problems). An empty selection is a legitimate zero
    here — pre-commit's ``files:`` regex has already narrowed the list — which is
    exactly why :func:`audit` and not this function is what the required check runs.
    """
    base = base or repo_root()
    directory = scripts_dir(base)
    selected = []
    for raw in paths:
        candidate = pathlib.Path(raw)
        resolved = candidate if candidate.is_absolute() else (base / candidate)
        try:
            resolved.resolve().relative_to(directory.resolve())
        except ValueError:
            continue
        selected.append(resolved)

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
        help=f"sweep every script under {SCRIPTS_DIR_REL}, not only the paths given",
    )
    parser.add_argument("paths", nargs="*", help="files to check (pre-commit passes these)")
    args = parser.parse_args(argv)

    if args.audit:
        reached, problems = audit()
        scope = f"{reached} scripts under {SCRIPTS_DIR_REL}"
    elif args.paths:
        reached, problems = check_files(args.paths)
        scope = f"{reached} staged scripts under {SCRIPTS_DIR_REL}"
    else:
        parser.error("nothing to do — pass --audit or one or more paths")

    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nundefined-name audit FAILED over %s (#14405).", scope)
        return 1
    logger.info("undefined-name audit clean over %s (#14405).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
