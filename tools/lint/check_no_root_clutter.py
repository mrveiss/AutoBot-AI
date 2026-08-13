#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep the repository root free of session reports and test artifacts (#14216).

Background
----------
The repository root is the first screen a visitor sees. By 2026-08 it carried
14 tracked session/audit reports — ``BUG_SWEEP_REPORT.md``,
``UMBRELLA_9931_RECOVERY_REPORT.md``, ``TRIAGE_DELTA_REPORT.md`` and friends —
alongside the actual product docs. They are legitimate work product; they were
simply written to the front door because that is where the writing session
happened to be. #14216 moved them to ``docs/reports/``.

Nothing stopped them landing there in the first place, so this hook is the
stop. Reports go to ``docs/reports/``, research to ``docs/research/``, and the
root keeps only the files a newcomer needs.

The hook also blocks ``MagicMock*`` paths. A path sanitizer promotes an object
repr into a real nested directory tree instead of rejecting it, so a test run
leaves ``MagicMock/mock.settings.backup_dir/<id>/`` behind (#14217). The tree
is gitignored, but an explicit ``git add -f`` would still commit it — this is
the backstop.

Scope
-----
Top-level ``*.md`` and ``*.txt`` files only, plus any path rooted at
``MagicMock``. Files in subdirectories are never in scope: the point is the
front door, not the house.

Adding a genuinely new top-level document is a deliberate act — add it to
``ALLOWED_ROOT_FILES`` in the same commit and the reviewer sees the intent.

Exit code
---------
  0 — clean
  1 — disallowed top-level file(s) found (commit blocked)
  2 — the repository scan itself failed (see "empty is not clean" below)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Top-level *.md / *.txt files a newcomer needs at the front door.
# Anything else belongs under docs/. Extend deliberately, in the commit that
# adds the file, so the addition is visible in review.
ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
    {
        "CHANGELOG.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "CONTRIBUTORS.md",
        "FUNDING.md",
        "INSTALL.md",
        "QUICK_REFERENCE.md",
        "README.md",
        # Machine-read config that happens to carry a .txt extension. Read by
        # pipeline-scripts/check-new-module-callers.sh, which resolves it from
        # the repo root — it is a tooling contract, not a document.
        ".wiring-deferral.txt",
        # Dependency manifests are tooling contracts, not documents; their
        # location is fixed by pip/CI and cannot move under docs/.
        "requirements.txt",
        "requirements-ci.txt",
        "requirements-ci-test.txt",
        "requirements-dev.txt",
        "requirements-gpu.txt",
    }
)

# Extensions treated as "documents" for the purposes of this check.
_DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".txt"})

# Test-artifact directory produced by the #14217 path-sanitizer bug.
_ARTIFACT_ROOT = "MagicMock"

_REPORT_HINT = (
    "session and audit reports belong in docs/reports/ (add a row to its _index.md); "
    "research belongs in docs/research/"
)


def _tracked_paths(repo_root: Path) -> list[str]:
    """Return every tracked path, repo-relative, POSIX-separated.

    Anchored with ``cwd=repo_root`` rather than the caller's CWD: run from a
    subdirectory, ``git ls-files`` succeeds and returns paths re-prefixed
    relative to that subdirectory, so a CWD-relative scan reports a
    confidently wrong result instead of an empty one.
    """
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def find_violations(paths: list[str]) -> list[tuple[str, str]]:
    """Return [(path, reason), …] for disallowed root documents and artifacts."""
    violations: list[tuple[str, str]] = []
    for path in paths:
        if path == _ARTIFACT_ROOT or path.startswith(f"{_ARTIFACT_ROOT}/"):
            violations.append(
                (
                    path,
                    "test artifact from the #14217 path-sanitizer bug — a mock repr "
                    "became a real directory tree; delete it, do not commit it",
                )
            )
            continue
        if "/" in path:
            continue
        if Path(path).suffix.lower() not in _DOC_SUFFIXES:
            continue
        if path in ALLOWED_ROOT_FILES:
            continue
        violations.append((path, f"not an allowlisted top-level document — {_REPORT_HINT}"))
    return violations


def main(argv: list[str] | None = None) -> int:
    """Scan the whole tracked tree; filenames from pre-commit are ignored."""
    del argv  # pass_filenames: false — the root is scanned in full every time.
    repo_root = Path(__file__).resolve().parents[2]

    try:
        paths = _tracked_paths(repo_root)
    except RuntimeError as exc:
        print(f"[no-root-clutter] {exc}", file=sys.stderr)
        return 2

    # An empty result reads as a clean result. A tracked tree without README.md
    # means the scan did not see the repository, not that the root is tidy —
    # fail loudly rather than passing on nothing.
    if "README.md" not in paths:
        print(
            "[no-root-clutter] scan returned no README.md — the repository was not "
            f"scanned (got {len(paths)} tracked paths). Refusing to report clean.",
            file=sys.stderr,
        )
        return 2

    violations = find_violations(paths)
    for path, reason in violations:
        print(f"[no-root-clutter] {path}: {reason}", file=sys.stderr)

    if violations:
        print(
            f"\n[no-root-clutter] {len(violations)} disallowed root path(s). "
            "Move the file, or add it to ALLOWED_ROOT_FILES in this hook if it "
            "genuinely belongs at the front door. Rationale: #14216.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
