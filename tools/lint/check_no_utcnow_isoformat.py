#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from typing import List, Tuple

# tools/lint/ is not a Python package; ensure sibling module is importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

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


# Patterns prevent regression of prior migrations (#5178) and enforce the
# canonical UTC helper going forward (#7436). The bare datetime.utcnow()
# pattern (#7436) was added to replace the deprecated Python 3.12 call
# with the tz-aware canonical helper from autobot_shared.datetime_utils.
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
        '`datetime.utcnow().isoformat() + "Z"` produces invalid ISO-8601 '
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
        '`time.strftime("%Y-%m-%dT...")` with no time argument defaults to '
        "`time.localtime()` (LOCAL time, mislabeled as UTC) (#5178 audit).",
    ),
    (
        "bare-utcnow",
        re.compile(r"datetime\.utcnow\(\)"),
        "`datetime.utcnow()` is deprecated (Python 3.12) and returns tz-naive datetimes. "
        "Use `datetime_now()` from `autobot_shared.datetime_utils` instead (#7436).",
    ),
]


# A generic pattern must not re-report a line a more specific pattern already
# caught (#12670). `bare-utcnow` matches the `datetime.utcnow()` prefix of every
# `utcnow().isoformat()` line, so before this every such line was reported twice
# — once with the correct `utc_timestamp()` fix and once with the unrelated
# `datetime_now()` fix, which made the hook's output actively misleading about
# how many violations a file has and which replacement to use.
SUBSUMED_BY: dict = {
    "bare-utcnow": {"isoformat", "z-suffix-isoformat"},
}

# Patterns whose own reason text already names the correct replacement, so the
# path-aware timestamp suggestion must not be prepended (#12670).
SELF_DESCRIBING_FIX = frozenset({"bare-utcnow"})


def _dedupe_subsumed(pattern_ids: List[str]) -> List[str]:
    """Drop generic pattern ids when a more specific one matched the same line."""
    matched = set(pattern_ids)
    return [pid for pid in pattern_ids if not (SUBSUMED_BY.get(pid, set()) & matched)]


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
    reasons = {pattern_id: reason for pattern_id, _, reason in PATTERNS}
    for line_no, line in enumerate(text.splitlines(), start=1):
        line_ids = [pattern_id for pattern_id, regex, _ in PATTERNS if regex.search(line)]
        for pattern_id in _dedupe_subsumed(line_ids):
            reason = reasons[pattern_id]
            # Patterns in SELF_DESCRIBING_FIX already name their own replacement;
            # prefixing the timestamp-string suggestion produced a message telling
            # the contributor to use two different helpers in one breath (#12670).
            message = reason if pattern_id in SELF_DESCRIBING_FIX else f"Use {suggestion} {reason}"
            hits.append((line_no, pattern_id, message))
    return hits


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
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
            f"\n[no-utcnow-isoformat] {total_hits} banned pattern(s) found. " f"See per-line fix suggestions above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
