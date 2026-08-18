#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14517 — no Python string constant may carry an unexpanded shell project-root placeholder.

Python does not interpolate shell syntax inside a string literal, so a pasted
``${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}`` stays exactly that: a path
whose first component is the literal text ``${AUTOBOT_PROJECT_ROOT:-``. A read
through it matches nothing and returns a comfortable empty list; a write through
it either raises ``FileNotFoundError`` on the missing parent or, under
``mkdir(parents=True)``, creates a junk tree actually named after the expression.
Neither outcome names the real defect at the point it happens — which is why
#14507's report run logged ``MISSION COMPLETED SUCCESSFULLY`` having discovered
nothing at all.

WHY NO EXISTING LINT SEES THIS. #14405/#14504 could only reach the *f-string*
form, because ``f"${AUTOBOT_PROJECT_ROOT:-...}"`` parses ``{AUTOBOT_PROJECT_ROOT:-...}``
as a replacement field naming an undefined name, and pyflakes reports F821 for
it. A **plain** literal is a perfectly well-formed string: no flake8 code, no
bandit check and no type checker has anything to say about it. 32 sites
accumulated across 25 files that way (#14517), on top of the one #14507 named.

WHY A REQUIRED CHECK. The same directional argument as ``check_flake8_exclude_anchoring``
(#14419), ``check_infra_scripts_undefined_names`` (#14405) and
``check_bandit_exclude_anchoring`` (#14489): every one of these sites fails
*quietly*, so a job that stops looking at them goes greener, not redder.
``.github/workflows/code-quality.yml`` calls this module with ``--audit``, in the
same shape as its siblings.

WHY THE GUARD LANDS AFTER THE SWEEP. Written first it would have needed a
32-entry baseline on day one, and this repository's experience with dormant
exemption lists is that such a list becomes the permanent home of the very defect
the guard exists for. The sweep landed first; this arrives with the tree already
clean, so there is nothing to ratchet.

THE EXEMPTIONS ARE DERIVED, NOT GRANDFATHERED. Three sites keep the literal on
purpose and cannot be rewritten around it: ``compliance_manager`` must locate the
junk tree the original bug created in order to migrate the audit records inside
it (#13658), and two test files pin that behaviour. #13658 proved by test that
hand-splitting the literal into components silently drops the ``}`` that belongs
to ``code_source}``, producing a path that never matches — so "assemble it from
fragments" is not available here the way it is for an ordinary fixture. Each
exemption therefore names a **file, an anchor symbol and an exact site count**,
and all three are re-proved on every run: an exemption whose file moved, whose
anchor was renamed, or whose literal count changed fails the audit instead of
quietly covering something new. A stranded exemption is a finding, not a pass.

The audit reports how many files it reached and fails below a floor, because a
sweep handed an empty file list reports a comfortable zero that is
indistinguishable from success. An unparseable file fails for the same reason —
skipping it would let a syntax error hide a placeholder.
"""

from __future__ import annotations

import argparse
import ast
import logging
import pathlib
import sys
from dataclasses import dataclass

# Plain stdlib logging, deliberately (#1082). This runs as a bare script inside a
# lint job, and `autobot_shared.logging_manager` would drag config loading into
# that path. Same trade as `tools/lint/check_infra_scripts_undefined_names.py`.
logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_no_shell_placeholder_paths.py"

#: The canonical replacement every finding is told to use.
RESOLVER = "autobot_shared.paths.project_root()"

#: The banned text, assembled from fragments so this module does not report
#: itself. A guard whose own source trips it either needs an exemption entry --
#: the exact dormant-exemption shape #14517 exists to avoid -- or gets narrowed
#: until it stops matching, which is worse.
PLACEHOLDER = "${" + "AUTOBOT_PROJECT_ROOT"

#: Directories that are never repository source.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".worktrees",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

#: Floor for the audit's own discovery. The repository held 4,986 tracked ``.py``
#: files when this landed; a sweep that suddenly reaches a fraction of that has
#: broken, and a clean result from a broken sweep asserts nothing.
DISCOVERY_FLOOR = 4000


@dataclass(frozen=True)
class Exemption:
    """One site that keeps the literal on purpose, with everything needed to re-prove it.

    ``anchor`` is the symbol the literal is bound to (or the test that pins it).
    ``sites`` is how many placeholder constants the file is allowed to hold. Both
    are checked on every run: naming only the path would let the file be rewritten
    around the exemption, and naming no count would let a fresh defect land inside
    an already-exempt file and inherit its pass.
    """

    path: str
    anchor: str
    sites: int
    reason: str


#: The complete set. Every entry is justified in the module docstring; nothing is
#: here because it was inconvenient to fix.
EXEMPTIONS: tuple[Exemption, ...] = (
    Exemption(
        path="autobot-backend/security/enterprise/compliance_manager.py",
        anchor="_LEGACY_AUDIT_ROOT",
        sites=1,
        reason=(
            "the literal names the junk tree the original bug created; the migration "
            "guard has to find it to avoid orphaning up to 2,555 days of encrypted "
            "audit records (#13658)"
        ),
    ),
    Exemption(
        path="repo_tests/compliance_audit_path_test.py",
        anchor="_PLACEHOLDER",
        sites=2,
        reason="pins the round trip that proves hand-splitting the literal drops a brace (#13658)",
    ),
    Exemption(
        path="scripts/check_ansible_file_references_test.py",
        anchor="test_paths_that_cannot_be_resolved_statically_are_skipped",
        sites=1,
        reason="a parametrised case asserting the ansible guard skips paths it cannot resolve statically",
    ),
)


def repo_root() -> pathlib.Path:
    """Repo root, derived from this file's location (``tools/lint/`` is two deep)."""
    return pathlib.Path(__file__).resolve().parents[2]


def discover_python_files(base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every ``*.py`` in the repository that is not build output or a nested checkout."""
    base = base or repo_root()
    return sorted(p for p in base.rglob("*.py") if not (set(p.relative_to(base).parts) & SKIP_DIRS))


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Identify every ``Constant`` that is a module/class/function docstring.

    Prose describing this defect is not the defect. Excluding docstrings
    structurally rather than by allowlisting the files that hold them is what
    keeps ``autobot_shared/paths.py`` -- whose whole docstring is about this bug --
    out of the findings without an exemption entry that could go stale.
    """
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def placeholder_sites(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every non-docstring string constant in *path* holding the placeholder.

    Raises:
        SyntaxError: the file does not parse. Deliberately propagated: a sweep
            that skips what it cannot read reports a clean zero for it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_constant_ids(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if PLACEHOLDER not in node.value or id(node) in docstrings:
            continue
        found.append((node.lineno, node.value.strip().splitlines()[0][:100]))
    return sorted(found)


def exemption_problems(base: pathlib.Path | None = None) -> list[str]:
    """Re-prove every exemption still describes what it claims to describe.

    An allowlist entry naming a moved file exempts nothing while still reading as
    coverage, and an entry whose file grew a second literal silently covers a
    fresh defect. Both are failures here, in the same direction as a finding.
    """
    base = base or repo_root()
    problems = []
    for exemption in EXEMPTIONS:
        path = base / exemption.path
        if not path.is_file():
            problems.append(
                f"{SELF_REL} exempts {exemption.path}, which does not exist. The file moved or "
                "was deleted, so this entry now exempts nothing while still reading as coverage. "
                "Repoint it or delete it."
            )
            continue
        source = path.read_text(encoding="utf-8")
        if exemption.anchor not in source:
            problems.append(
                f"{SELF_REL} exempts {exemption.path} for its `{exemption.anchor}`, which the file "
                "no longer defines. A rename must not strand the exemption: update the anchor, or "
                "drop the entry if the deliberate literal is gone."
            )
            continue
        actual = len(placeholder_sites(path))
        if actual == 0:
            problems.append(
                f"{SELF_REL} exempts {exemption.path}, which no longer holds any placeholder literal. "
                "The exemption is dormant — delete it, so the file is guarded like every other."
            )
        elif actual != exemption.sites:
            problems.append(
                f"{SELF_REL} exempts {exemption.sites} placeholder literal(s) in {exemption.path}, "
                f"but the file now holds {actual}. A new one inherited an existing exemption. "
                f"Resolve the new site through {RESOLVER}, or justify and raise the count here."
            )
    return problems


def _format_findings(findings: dict[str, list[tuple[int, str]]]) -> str:
    lines = []
    for rel in sorted(findings):
        for lineno, text in findings[rel]:
            lines.append(f"  {rel}:{lineno}  {text}")
    return "\n".join(lines)


def check_paths(paths: list[pathlib.Path], base: pathlib.Path) -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    """Scan *paths*, skipping exempt files. Returns (findings by path, parse problems)."""
    exempt = {e.path for e in EXEMPTIONS}
    findings: dict[str, list[tuple[int, str]]] = {}
    problems: list[str] = []
    for path in paths:
        rel = path.relative_to(base).as_posix()
        if rel in exempt or rel == SELF_REL:
            continue
        try:
            sites = placeholder_sites(path)
        except SyntaxError as exc:
            problems.append(
                f"{rel} does not parse ({exc.msg} at line {exc.lineno}), so it could not be scanned. "
                "A file the sweep cannot read is not a file the sweep found clean — fix the syntax."
            )
            continue
        if sites:
            findings[rel] = sites
    return findings, problems


def audit(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Sweep the whole repository. Returns (files reached, problems)."""
    base = base or repo_root()
    problems: list[str] = []

    files = discover_python_files(base)
    if len(files) < DISCOVERY_FLOOR:
        problems.append(
            f"discovery returned only {len(files)} Python file(s) (floor {DISCOVERY_FLOOR}) — "
            "the sweep broke, so a clean result below would assert nothing."
        )

    problems.extend(exemption_problems(base))

    findings, parse_problems = check_paths(files, base)
    problems.extend(parse_problems)
    if findings:
        total = sum(len(v) for v in findings.values())
        problems.append(
            f"{total} unexpanded shell placeholder(s) in Python string constants across "
            f"{len(findings)} file(s):\n"
            + _format_findings(findings)
            + f"\n\nPython never expands shell syntax in a string literal, so each of these names a "
            f"directory that cannot exist: reads return empty and writes create a junk tree literally "
            f'named "{PLACEHOLDER}:-". Resolve each through {RESOLVER} — not through an open-coded '
            f"os.environ.get, which is the same defect one layer down (#13149). {SELF_REL} carries no "
            "growable baseline on purpose (#14517)."
        )

    return len(files), problems


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
        help="sweep every Python file in the repository, not only the paths given",
    )
    parser.add_argument("paths", nargs="*", help="files to check")
    args = parser.parse_args(argv)

    base = repo_root()
    if args.audit:
        reached, problems = audit(base)
        scope = f"{reached} Python file(s)"
    elif args.paths:
        selected = [pathlib.Path(p) if pathlib.Path(p).is_absolute() else base / p for p in args.paths]
        findings, problems = check_paths([p for p in selected if p.suffix == ".py" and p.is_file()], base)
        if findings:
            problems.append(
                "unexpanded shell placeholder(s) in the given files:\n"
                + _format_findings(findings)
                + f"\n\nResolve each through {RESOLVER} (#14517)."
            )
        reached = len(selected)
        scope = f"{reached} given file(s)"
    else:
        parser.error("nothing to do — pass --audit or one or more paths")

    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nshell-placeholder audit FAILED over %s (#14517).", scope)
        return 1
    logger.info("shell-placeholder audit clean over %s (#14517).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
