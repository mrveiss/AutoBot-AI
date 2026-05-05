#!/usr/bin/env python3
"""
Unwired-tracker audit for AutoBot.

Scans the source tree for production modules whose top-of-file docstring
cites an `Issue #N` tracker that is CLOSED on GitHub, but whose module has
zero production callers (only test imports or none at all). These are
features whose tracker was closed prematurely — code complete, integration
skipped — the pattern surfaced by the orchestration audit (#4048 → #6836).

Usage:
    pipeline-scripts/audit-unwired-trackers.py [--json]
        Print findings to stdout (human-readable or JSON).

    pipeline-scripts/audit-unwired-trackers.py --file-issues
        File a GitHub discovery issue for each finding (deduped against
        existing open issues by tracker number).

Exit codes:
    0  no findings
    1  findings present (use --json for parseable output)
    2  internal error (gh unavailable, etc.)

Conservative by design:
    - Only flags files with explicit `Issue #N` docstring references
    - Only flags when tracker is CLOSED (open trackers are deliberately in-flight)
    - Skips ambiguous module names (__init__, types, utils, common, base)
    - Never deletes or modifies code; only reports
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
# #6927: include slm-backend, infrastructure, npu-worker. Original list missed
# 731 issue refs in autobot-slm-backend and 556 in autobot-infrastructure —
# the audit silently skipped half the codebase. autobot-ai-stack is excluded
# because it currently has zero source files (READMEs only).
SCAN_DIRS = [
    "autobot-backend",
    "autobot-frontend",
    "autobot_shared",
    "autobot-slm-backend",
    "autobot-infrastructure",
    "autobot-npu-worker",
]
SOURCE_GLOBS = ("*.py", "*.ts", "*.vue")

# Module stems too common to grep reliably. Skip — false-positive risk too high.
AMBIGUOUS_STEMS = frozenset(
    {
        "__init__",
        "types",
        "utils",
        "common",
        "base",
        "config",
        "constants",
        "helpers",
        "main",
        "index",
    }
)

# Files we never want to scan as potentially-orphaned modules.
SKIP_PATH_FRAGMENTS = (
    "/__pycache__/",
    "/node_modules/",
    "/.worktrees/",
    "/dist/",
    "/build/",
    "/migrations/",
)
TEST_PATH_FRAGMENTS = ("_test.", ".test.", "/tests/", "/__tests__/")

DOCSTRING_HEAD_LINES = 40  # how many lines from top of file to scan for tracker refs
# Match common docstring tracker-reference shapes (#6928 widened the set).
# Single regex with multiple alternations — each branch captures into its own
# numbered group; extract_tracker_refs() picks whichever matched.
#
#   Issue #N                 — formal prose ("Issue #1234")
#   Closes/Fixes/Resolves #N — git/GitHub conventional close-keywords
#   See/Related/Tracking #N  — soft references in docstrings
#   #N: at start of line     — heading-style (\b alone fails because # is non-word)
#   (#N)                     — parenthesized inline citation
#   [#N]                     — markdown reference shape ("[#1234](url)")
#   /issues/N                — direct URL form
ISSUE_REF_RE = re.compile(
    r"(?:^|\W)(?:Issue|Closes|Fixes|Resolves|See|Related|Tracking)\s+#(\d+)\b"
    r"|(?:^|\s)#(\d+):"
    r"|\(#(\d+)\)"
    r"|\[#(\d+)\]"
    r"|/issues/(\d+)\b",
    re.MULTILINE,
)


@dataclass
class Finding:
    file: str
    tracker: int
    tracker_state: str  # CLOSED, OPEN, UNKNOWN
    production_callers: int  # always 0 for findings


def is_test_path(path: Path) -> bool:
    s = str(path)
    return any(frag in s for frag in TEST_PATH_FRAGMENTS)


def should_skip_path(path: Path) -> bool:
    s = str(path)
    return any(frag in s for frag in SKIP_PATH_FRAGMENTS)


def extract_tracker_refs(file_path: Path) -> list[int]:
    """Return list of Issue #N numbers from the first DOCSTRING_HEAD_LINES."""
    try:
        with file_path.open("r", encoding="utf-8") as f:
            head = "".join(line for _, line in zip(range(DOCSTRING_HEAD_LINES), f))
    except (OSError, UnicodeDecodeError):
        return []
    refs: list[int] = []
    for m in ISSUE_REF_RE.finditer(head):
        # 5 alternation branches → 5 capture groups; pick whichever matched.
        n = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
        if n:
            refs.append(int(n))
    return list(dict.fromkeys(refs))  # dedupe, preserve order


def grep_count_production_callers(stem: str, self_path: Path) -> int:
    """Return number of production import lines referencing `stem`."""
    if stem in AMBIGUOUS_STEMS:
        return -1  # skip
    pattern = rf"from .*\b{stem}\b|import .*\b{stem}\b"
    cmd = [
        "grep",
        "-rn",
        "-E",
        pattern,
        *(str(REPO_ROOT / d) for d in SCAN_DIRS if (REPO_ROOT / d).exists()),
        "--include=*.py",
        "--include=*.ts",
        "--include=*.vue",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
    except subprocess.TimeoutExpired:
        return -1
    if result.returncode > 1:  # 0 = matches, 1 = no matches, >1 = error
        return -1
    self_str = str(self_path)
    count = 0
    for line in result.stdout.splitlines():
        if not line:
            continue
        if "/__pycache__/" in line:
            continue
        if any(frag in line for frag in TEST_PATH_FRAGMENTS):
            continue
        # Strip "path:lineno:" prefix to compare against self_path
        head = line.split(":", 1)[0]
        if head == self_str:
            continue
        count += 1
    return count


def fetch_closed_tracker_set() -> set[int]:
    """One-shot fetch of all CLOSED issues so per-finding lookups are O(1)."""
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "closed",
        "--limit",
        "10000",
        "--json",
        "number",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=True
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"warning: gh unavailable, tracker states will be UNKNOWN ({e})", file=sys.stderr)
        return set()
    try:
        data = json.loads(result.stdout)
        return {item["number"] for item in data}
    except (json.JSONDecodeError, KeyError):
        return set()


def existing_audit_issues_by_tracker() -> set[int]:
    """Return the set of trackers that already have an open audit-discovery issue.

    Convention: audit-discovery issues are titled
    `discovery(unwired-tracker): wire in <module> (tracker #NNNN closed prematurely)`.
    We search by the exact title prefix to avoid filing duplicates.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--search",
        "discovery(unwired-tracker)",
        "--limit",
        "1000",
        "--json",
        "number,title",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        return set()
    out: set[int] = set()
    pat = re.compile(r"tracker #(\d+) closed prematurely")
    for item in data:
        m = pat.search(item.get("title", ""))
        if m:
            out.add(int(m.group(1)))
    return out


def scan() -> list[Finding]:
    closed_set = fetch_closed_tracker_set()
    findings: list[Finding] = []
    for sd in SCAN_DIRS:
        base = REPO_ROOT / sd
        if not base.exists():
            continue
        for pattern in SOURCE_GLOBS:
            for f in base.rglob(pattern):
                if should_skip_path(f) or is_test_path(f):
                    continue
                refs = extract_tracker_refs(f)
                if not refs:
                    continue
                stem = f.stem
                callers = grep_count_production_callers(stem, f)
                if callers != 0:
                    continue  # -1 = ambiguous skip, ≥1 = wired
                for ref in refs:
                    state = "CLOSED" if ref in closed_set else "OPEN_OR_UNKNOWN"
                    if state != "CLOSED":
                        continue
                    findings.append(
                        Finding(
                            file=str(f.relative_to(REPO_ROOT)),
                            tracker=ref,
                            tracker_state=state,
                            production_callers=0,
                        )
                    )
                    break  # one finding per file, prefer first tracker
    return findings


def render_human(findings: list[Finding]) -> str:
    if not findings:
        return "✅ No unwired-tracker findings.\n"
    lines = [
        f"❌ {len(findings)} unwired-tracker finding(s):",
        "",
        f"{'FILE':<70}  {'TRACKER':>10}  {'STATE':<8}  CALLERS",
    ]
    for f in findings:
        lines.append(f"{f.file:<70}  #{f.tracker:<9}  {f.tracker_state:<8}  {f.production_callers}")
    lines += [
        "",
        "Each finding represents a module whose tracker issue is closed but",
        "whose code has zero production callers. Per #6836, file a wire-in",
        "issue for each, or run with --file-issues.",
    ]
    return "\n".join(lines) + "\n"


def render_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2)


def file_discovery_issue(finding: Finding) -> Optional[int]:
    title = (
        f"discovery(unwired-tracker): wire in {Path(finding.file).stem} "
        f"(tracker #{finding.tracker} closed prematurely)"
    )
    body = f"""## Discovered by

`pipeline-scripts/audit-unwired-trackers.py` — automated tracker cross-reference (#6836 process gate).

## Finding

[`{finding.file}`]({finding.file}) cites tracker #{finding.tracker} in its docstring.
Tracker is **{finding.tracker_state}**, but the module has **{finding.production_callers} production callers**.

## Evidence

```bash
grep -rn 'from .*\\b{Path(finding.file).stem}\\b' \\
    autobot-backend autobot-frontend autobot_shared --include="*.py" --include="*.ts" --include="*.vue" \\
  | grep -v __pycache__ | grep -vE '(_test\\.|\\.test\\.|/tests/)'
```
returns 0 production-caller hits.

## Decision needed

Per CLAUDE.md "Issue Closure Verification Gate" + #6836: closed feature trackers must have ≥1 production caller. Either:

1. **Wire the module in** to a production code path, OR
2. **Reopen #{finding.tracker}** if integration was unfinished, OR
3. **Document deliberate deferral** (Protocol/scaffold/future-feature) and convert this finding into a tracking-only note.

## Acceptance criteria

- [ ] Production caller exists: `grep` returns ≥1 non-test hit
- [ ] Or tracker #{finding.tracker} is reopened
- [ ] Or this issue is closed with a `### Wire-in deferred` note

## Priority

P2 — closure-verification process gap, blocks credibility of "closed" tracker counts.
"""
    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--label",
        "tech-debt,not-wired,architecture",
        "--body",
        body,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )
    except subprocess.SubprocessError as e:
        print(f"warning: failed to file issue for {finding.file}: {e}", file=sys.stderr)
        return None
    # gh issue create prints the URL; extract the trailing issue number
    m = re.search(r"/issues/(\d+)", result.stdout)
    return int(m.group(1)) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--file-issues",
        action="store_true",
        help="file GitHub discovery issues for findings (dedupes against open ones)",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=20,
        help="cap the number of issues filed in one run (default 20)",
    )
    args = parser.parse_args()

    findings = scan()

    if args.file_issues:
        already_filed = existing_audit_issues_by_tracker()
        new = [f for f in findings if f.tracker not in already_filed]
        capped = new[: args.max_issues]
        skipped_dupes = len(findings) - len(new)
        skipped_cap = len(new) - len(capped)
        print(
            f"findings={len(findings)}  new={len(new)}  filing={len(capped)}  "
            f"deduped={skipped_dupes}  cap-deferred={skipped_cap}",
            file=sys.stderr,
        )
        for f in capped:
            num = file_discovery_issue(f)
            if num:
                print(f"filed #{num} for {f.file} (tracker #{f.tracker})")

    if args.json:
        print(render_json(findings))
    else:
        print(render_human(findings))

    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # pragma: no cover
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
