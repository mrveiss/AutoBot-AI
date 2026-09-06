#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SPDX/Apache-2.0 license-header enforcement + backfill (#9840).

The Apache-2.0 relicense (#9826, PR #9830) applied the two-line header

    Copyright 2025-2026 mrveiss
    SPDX-License-Identifier: Apache-2.0

to first-party source files as a *point-in-time* sweep. Files merged in
during the PR's catch-up never got the header, and there was no hook to
stop new files from landing header-less. This check closes both gaps:

* As a pre-commit hook (default mode) it fails when a staged first-party
  source file is missing the SPDX header.
* With ``--fix`` it inserts the header idempotently, preserving any
  shebang / ``# -*- coding -*-`` line, and de-duplicates the legacy
  ``Copyright (c) <year> mrveiss`` line left by older tooling.

Comment style is chosen per extension (``#`` for .py/.sh, ``//`` for
.ts/.tsx/.js/.mjs, ``/* */`` for .css) so the inserted header is valid
in every target language.

Scope is intentionally identical to the original sweep: first-party
``.py/.ts/.tsx/.js/.mjs/.sh/.css`` files only, with vendored, generated,
``.vue``, workflow, and infrastructure paths excluded (see EXCLUDE_RE).

REACH (#15817)
--------------
The per-file test above is correct; what it lacked was any proof it ran.
Before this, no arguments at all, a mistyped path, and an ``xargs`` that
split zero times all exited **0** — the same answer a genuinely clean tree
gives. CI's gate was ``git ls-files -z | xargs -0 <this script>``, so the
whole check rested on that pipeline producing output: a shallow checkout, a
wrong CWD or an edit to the pipeline would have passed having examined
nothing, and kept passing while headers rotted out of the tree (#15816 is
the header that got in; the tree-wide job is the only thing that saw it).

Four changes, and the split between them is the design:

* ``--all`` enumerates the tree itself via :func:`tracked_paths` instead of
  being fed by ``xargs``, and is the ONLY mode carrying :data:`SPDX_FLOOR`.
  The floor is bound to files **examined**, never to violations found. The
  mode is an explicit flag rather than inferred from an empty argv the way
  the sibling guards do it (``MIN_SCANNED_PY_FILES``, #15807): here an empty
  argv is the exact failure being closed, so it cannot also be the spelling
  of "sweep everything". pre-commit passes staged files and meets no floor,
  so a one-file commit still works.
* **An in-scope path that is not a file is an error**, not a skip. A renamed
  or mistyped path used to vanish silently — which is what let a working
  tree seven commits behind base read as clean while diagnosing #15816.
  Out-of-scope paths stay merely uncounted: a wrong extension is not this
  check's business, but a ``.py`` that is not there is.
* **Check mode refuses a verdict it did not earn.** Exit 0 without ``--fix``
  claims that every file asked about carries a header; asked about nothing
  it makes no claim, and exits :data:`EXIT_NO_VERDICT`. ``--fix`` is exempt
  because it is an action, not a verdict — "nothing needed fixing" is a real
  outcome, and the pre-commit hook (the only ``--fix`` caller) must survive a
  staged file EXCLUDE_RE skips but the hook's own filter let through.
* ``examined=N`` on every run makes the reach visible rather than merely
  enforced.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import enforce_reach, tracked_paths  # noqa: E402

#: Repository root. A module-level constant rather than a call inside
#: :func:`_tree_wide_candidates` so the sweep can be pointed at a synthetic
#: tree under test without the test having to fake a git checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]

HOOK_ID = "spdx-header"

#: Floor for the ``--all`` sweep, bound to files **examined** rather than
#: violations found (#15817) — the shape of ``MIGRATION_FLOOR`` (#15776),
#: ``GIT_CALL_FLOOR`` (#15783) and ``MIN_SCANNED_PY_FILES`` (#15807). 6,996
#: tracked files were in scope when this landed, so the floor sits ~28% below
#: the real count: low enough that ordinary churn (or a subtree moving out of
#: scope) never trips it, high enough that a sweep which lost its reach —
#: wrong root, wrong CWD, an enumeration returning nothing — cannot land
#: under it and still look clean.
SPDX_FLOOR = 5000

#: Exit code for a run that examined nothing, or too little, and therefore has
#: no verdict to give. Deliberately not ``1``: that means "headers are
#: missing", a claim about the tree which a check that could not see the tree
#: has no standing to make. An unreadable file and a clean file are different
#: outcomes and must not share an exit code.
EXIT_NO_VERDICT = 2

COPYRIGHT_LINE = "Copyright 2025-2026 mrveiss"
SPDX_LINE = "SPDX-License-Identifier: Apache-2.0"

# Per-extension comment rendering of the two header lines.
HASH_EXTS = {".py", ".sh"}
SLASH_EXTS = {".ts", ".tsx", ".js", ".mjs"}
CSS_EXTS = {".css"}
TARGET_EXTS = HASH_EXTS | SLASH_EXTS | CSS_EXTS

# Paths excluded from the sweep — vendored, generated, build output, and
# line-sensitive canonical-check fixtures. The infrastructure tree is
# first-party (AutoBot-authored scripts/tests/config) and IS swept (#12175);
# only genuinely third-party vendored subtrees under it stay excluded (their
# own licenses govern — see THIRD-PARTY-NOTICES).
EXCLUDE_RE = re.compile(
    r"(^|/)(?:"
    r"node_modules|"
    r"\.venv|venv|__pycache__|\.git|"
    r"dist|"
    r"_generated|generated|"
    r"fixtures"
    r")/"
    r"|^autobot-infrastructure/shared/mcp/tools/(?:context7|mcp-structured-thinking)/"
    r"|^\.github/workflows/"
    r"|^data/file_manager_root/"
    r"|\.min\.(?:js|css)$"
)

# A line that already carries an SPDX identifier — used to detect presence.
SPDX_PROBE = re.compile(r"SPDX-License-Identifier:\s*Apache-2\.0")
# Legacy copyright line emitted by older AutoBot tooling, any year form.
LEGACY_COPYRIGHT = re.compile(r"^\s*(#|//|\*|/\*)\s*Copyright \(c\) \d{4}(-\d{4})? mrveiss")


def _rendered_header(ext: str) -> list[str]:
    if ext in CSS_EXTS:
        return [f"/* {COPYRIGHT_LINE}", f"   {SPDX_LINE} */"]
    prefix = "#" if ext in HASH_EXTS else "//"
    return [f"{prefix} {COPYRIGHT_LINE}", f"{prefix} {SPDX_LINE}"]


def _is_preamble(line: str) -> bool:
    """Lines that must stay at the very top, above the header."""
    return line.startswith("#!") or "coding:" in line or "coding=" in line


def has_header(text: str) -> bool:
    # Only the top of the file counts — a match deep in the body is unrelated.
    head = "\n".join(text.splitlines()[:10])
    return bool(SPDX_PROBE.search(head))


def insert_header(text: str, ext: str) -> str:
    if has_header(text):
        return text
    lines = text.split("\n")
    header = _rendered_header(ext)

    idx = 0
    preamble: list[str] = []
    while idx < len(lines) and _is_preamble(lines[idx]):
        preamble.append(lines[idx])
        idx += 1

    # Drop the legacy "Copyright (c) <year> mrveiss" line if it sits in the
    # next few lines, so we don't end up with two copyright statements.
    body = lines[idx:]
    body = [ln for ln in body[:6] if not LEGACY_COPYRIGHT.match(ln)] + body[6:]

    rebuilt = preamble + header + body
    return "\n".join(rebuilt)


def in_scope(path: Path) -> bool:
    if path.suffix not in TARGET_EXTS:
        return False
    posix = path.as_posix()
    return not EXCLUDE_RE.search(posix)


def _argv_candidates(files: list[str]) -> list[tuple[str, Path]]:
    """In-scope ``(label, path)`` pairs from an explicit file list.

    Out of scope is *uncounted*, never an error: pre-commit hands the hook
    whatever the commit touched, and a wrong extension or an excluded subtree
    is simply not this check's business.
    """
    return [(raw, Path(raw)) for raw in files if in_scope(Path(raw))]


def _tree_wide_candidates() -> list[tuple[str, Path]]:
    """In-scope ``(repo-relative, absolute)`` pairs for every tracked file.

    :func:`in_scope` is applied to the **relative** path because EXCLUDE_RE
    anchors several patterns at ``^`` (``.github/workflows/``,
    ``data/file_manager_root/``, the vendored MCP subtrees); an absolute path
    would slip past every one of them. Opening uses the absolute path so the
    sweep does not depend on the caller's CWD. :func:`tracked_paths` raises
    rather than returning ``[]``, so a failed enumeration cannot arrive here
    disguised as an empty repository.
    """
    return [(rel, REPO_ROOT / rel) for rel in tracked_paths(REPO_ROOT) if in_scope(Path(rel))]


def _split_readable(
    candidates: list[tuple[str, Path]],
) -> tuple[list[tuple[str, Path]], list[str]]:
    """``(targets, unreadable)`` — in-scope candidates that are, and are not, files."""
    targets: list[tuple[str, Path]] = []
    unreadable: list[str] = []
    for label, path in candidates:
        if path.is_file():
            targets.append((label, path))
        else:
            unreadable.append(label)
    return targets, unreadable


def _examine(targets: list[tuple[str, Path]], fix: bool) -> tuple[list[str], list[str]]:
    """``(missing, fixed)`` over already-resolved targets."""
    missing: list[str] = []
    fixed: list[str] = []
    for label, path in targets:
        text = path.read_text(encoding="utf-8")
        if has_header(text):
            continue
        if fix:
            path.write_text(insert_header(text, path.suffix), encoding="utf-8")
            fixed.append(label)
        else:
            missing.append(label)
    return missing, fixed


def _report_unreadable(unreadable: list[str]) -> None:
    print(f"[{HOOK_ID}] path is not a readable file:", file=sys.stderr)
    for f in unreadable:
        print(f"  {f}", file=sys.stderr)
    print("A path the check could not open is not a path that passed.", file=sys.stderr)


def _report_missing(missing: list[str]) -> None:
    print("Missing SPDX/Apache-2.0 license header (run with --fix or the")
    print("insert-license pre-commit hook to add it):")
    for f in missing:
        print(f"  {f}")
    print()
    print("Expected header (comment style per file type):")
    print(f"  {COPYRIGHT_LINE}")
    print(f"  {SPDX_LINE}")


def _no_verdict(examined: int, tree_wide: bool, fix: bool) -> int:
    """Non-zero when the run examined too little to make any claim at all.

    Two gates, both answering :data:`EXIT_NO_VERDICT` rather than ``1``: the
    reach floor, which only a ``--all`` sweep can trip, and an empty check-mode
    run, which is the ``xargs``-split-zero shape #15817 was filed about.
    ``--fix`` is exempt from the second — it is an action, and "nothing needed
    fixing" is a real outcome where "clean, having read nothing" is not.
    """
    if enforce_reach(examined, SPDX_FLOOR, hook=HOOK_ID, full_repo=tree_wide):
        return EXIT_NO_VERDICT
    if not examined and not fix:
        print(f"[{HOOK_ID}] examined no files, so there is no verdict to give.", file=sys.stderr)
        print("Pass files to check, or --all to sweep the whole tree.", file=sys.stderr)
        return EXIT_NO_VERDICT
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    fix = "--fix" in args
    tree_wide = "--all" in args
    files = [a for a in args if a not in {"--fix", "--all"}]

    if tree_wide and files:
        print(f"[{HOOK_ID}] --all sweeps the tree itself; do not also pass files.", file=sys.stderr)
        return EXIT_NO_VERDICT

    targets, unreadable = _split_readable(_tree_wide_candidates() if tree_wide else _argv_candidates(files))
    examined = len(targets)
    print(f"[{HOOK_ID}] examined={examined}", file=sys.stderr)

    if unreadable:
        _report_unreadable(unreadable)
        return EXIT_NO_VERDICT
    if vacuous := _no_verdict(examined, tree_wide, fix):
        return vacuous

    missing, fixed = _examine(targets, fix)
    for f in fixed:
        print(f"inserted SPDX header: {f}")
    if missing:
        _report_missing(missing)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
