#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression-prevention check for the #5178 datetime migration.

Blocks any new occurrence of three banned patterns that produce
broken or inconsistent timestamp strings:

  1. ``datetime.utcnow().isoformat()`` — produces tz-naive output;
     the unguarded ``fromisoformat`` parsers in #5169's audit then
     return naive datetimes that mis-compare against tz-aware values.
  2. ``datetime.utcnow().isoformat() + "Z"`` — produces invalid
     mixed-format ``2026-04-19T...Z`` (microseconds + Z mutually
     exclusive) which raises ``ValueError`` from ``fromisoformat``
     on Python 3.10.
  3. ``time.strftime("%Y-%m-%dT%H:%M:%S")`` (no time arg) — silently
     uses ``time.localtime()`` (LOCAL time, naive), then gets
     mislabeled as UTC by callers.

Use ``autobot_shared.time_utils.utc_timestamp()`` instead.

This hook covers regression of the #5178 migration (PRs #5213,
#5233, #5236, #5243). The broader DTZ003 enforcement (banning
``datetime.utcnow()`` for non-isoformat purposes) is gated on #5211
completion — adding it here would block on 248 pre-existing sites.

Exit code:
  0 — clean (no banned patterns found in scanned files)
  1 — banned patterns found (PR/commit blocked)
  2 — usage error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

# Files allowed to contain banned patterns (very narrow allowlist)
ALLOWLIST = {
    # The hook itself contains the patterns as strings — exclude it
    "tools/lint/check_no_utcnow_isoformat.py",
    # The hook's test file uses the banned patterns as fixtures by design
    "tools/lint/check_no_utcnow_isoformat_test.py",
    # The audit docs reference the patterns in code blocks
    "docs/developer/audits/datetime-parsing-audit.md",
    "docs/developer/audits/datetime-producer-audit.md",
    # `utc_timestamp()` itself wraps `datetime.now(timezone.utc).isoformat()`
    # — not the banned `utcnow().isoformat()` pattern, but the regex is
    # defensive enough to flag it. Module is exempt by design.
    "autobot_shared/time_utils.py",
    # Test deliberately exercises the recency-score handler against a naive
    # timestamp (the test name is `test_naive_timestamp_handled`). Migrating
    # the fixture would defeat the test purpose. See #5393.
    "autobot-backend/knowledge/knowledge_context_suggestions_test.py",
}

# Path prefixes whose files cannot import `autobot_shared.time_utils` reliably
# (standalone agent on remote nodes, ansible-synced agent code, infra log
# forwarders). For violations in these paths, suggest the inline canonical
# form instead of the helper. See PR #5384 (#5381) and #5397.
INLINE_PATH_PREFIXES: Tuple[str, ...] = (
    "autobot-slm-agent/",
    "autobot-slm-backend/slm/agent/",
    "autobot-slm-backend/ansible/roles/slm_agent/files/",
    "autobot-infrastructure/shared/scripts/",
)


def _suggestion_for(rel_path: str) -> str:
    """Return the canonical fix string appropriate for the file's deployment scope."""
    posix = rel_path.replace("\\", "/")
    if any(posix.startswith(p) for p in INLINE_PATH_PREFIXES):
        return (
            "`datetime.now(timezone.utc).isoformat()` (inline) — this component "
            "lacks `autobot_shared` on path. See PR #5384."
        )
    return "`utc_timestamp()` from `autobot_shared.time_utils`."


# Patterns are intentionally precise — this hook only prevents regression
# of the #5178 migration, not the broader datetime.utcnow() backlog
# tracked by #5211.
PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (
        "isoformat",
        re.compile(r"datetime\.utcnow\(\)\.isoformat\("),
        "`datetime.utcnow().isoformat()` produces tz-naive strings that "
        "mis-compare against tz-aware datetimes (#5178).",
    ),
    (
        "z-suffix-isoformat",
        re.compile(r'datetime\.utcnow\(\)\.isoformat\(\)\s*\+\s*["\']Z["\']'),
        "`datetime.utcnow().isoformat() + \"Z\"` produces invalid ISO-8601 "
        "(microseconds + Z mutually exclusive) — fails `fromisoformat` on "
        "Python 3.10 (#5238).",
    ),
    (
        "naive-strftime-iso",
        # time.strftime("%Y-%m-%dT...")  with no second positional arg
        # → defaults to time.localtime() (LOCAL time, mislabeled UTC).
        # Matches strftime calls with the ISO format and NO comma after
        # the format string (no time tuple passed).
        re.compile(r'time\.strftime\(\s*["\']%Y-%m-%dT[^"\']*["\']\s*\)'),
        "`time.strftime(\"%Y-%m-%dT...\")` with no time argument defaults to "
        "`time.localtime()` (LOCAL time, mislabeled as UTC) (#5178 audit).",
    ),
]


def _is_allowlisted(rel_path: str) -> bool:
    """Check if a file path is in the allowlist (POSIX-normalized)."""
    posix = rel_path.replace("\\", "/")
    return posix in ALLOWLIST


def _scan(path: Path, repo_root: Path) -> List[Tuple[int, str, str]]:
    """Return [(line_no, pattern_id, message)] of banned-pattern hits.

    Message includes the path-aware fix suggestion (utc_timestamp() vs inline
    pattern) so the contributor sees the right replacement for the file's
    deployment scope. See #5397.
    """
    try:
        rel = str(path.resolve().relative_to(repo_root))
    except ValueError:
        # Path is outside the repo (e.g. /tmp test files) — scan as-is
        rel = str(path)
    if _is_allowlisted(rel):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    suggestion = _suggestion_for(rel)
    hits: List[Tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern_id, regex, reason in PATTERNS:
            if regex.search(line):
                hits.append((line_no, pattern_id, f"Use {suggestion} {reason}"))
    return hits


def _iter_target_files(args: List[str], repo_root: Path) -> Iterable[Path]:
    """Yield target files: explicit argv if given, else staged .py files."""
    if args:
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = repo_root / p
            if p.is_file() and p.suffix == ".py":
                yield p
        return
    # Default: scan all repo .py files. Pre-commit will pass changed
    # files via argv, so this branch only runs in manual / CI mode.
    for p in repo_root.rglob("*.py"):
        # Skip vendored / generated / external / vcs-ignored locations
        parts = p.relative_to(repo_root).parts
        if any(
            part
            in {
                ".venv",
                "venv",
                "node_modules",
                "__pycache__",
                ".git",
                "dist",
                "build",
                ".worktrees",  # #5394: parallel-work git worktrees, not vendored code
            }
            for part in parts
        ):
            continue
        yield p


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(_iter_target_files(argv[1:], repo_root))
    total_hits = 0
    for path in files:
        for line_no, pattern_id, message in _scan(path, repo_root):
            try:
                rel = path.resolve().relative_to(repo_root)
            except ValueError:
                rel = path
            print(
                f"[no-utcnow-isoformat] {rel}:{line_no}: {pattern_id} — {message}",
                file=sys.stderr,
            )
            total_hits += 1
    if total_hits:
        print(
            f"\n[no-utcnow-isoformat] {total_hits} banned pattern(s) found. "
            f"See per-line fix suggestions above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
