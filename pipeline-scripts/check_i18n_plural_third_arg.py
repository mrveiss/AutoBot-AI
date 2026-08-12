#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pre-commit hook: flag t(plural-key, {count}) calls missing the 3rd positional arg.

vue-i18n's plural form requires three positional arguments for keys whose value
contains the `|` plural separator:

    t('chat.messages.attachments', { count: n }, n)   -- OK
    t('chat.messages.attachments', { count: n })       -- VIOLATION

The plural-key set is derived dynamically from
``autobot-frontend/src/i18n/locales/en.json`` on every run, so new plural keys
added to that file are automatically covered without touching this script.

Closes GH#7155. Prevents recurrence of the #6976 AC3 plural-form regression.
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate en.json relative to the repo root.
# pre-commit runs hooks with cwd = repo root, so this relative path is stable.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_EN_JSON = _REPO_ROOT / "autobot-frontend" / "src" / "i18n" / "locales" / "en.json"


def _collect_plural_keys(data: dict, prefix: str = "") -> set[str]:
    """Recursively walk a nested JSON dict and collect dotted keys whose
    string value contains the vue-i18n plural separator ``|``."""
    keys: set[str] = set()
    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _collect_plural_keys(v, full_key)
        elif isinstance(v, str) and "|" in v:
            keys.add(full_key)
    return keys


def _load_plural_keys() -> set[str]:
    """Load plural keys from en.json.  Returns empty set on any I/O error so
    the hook degrades gracefully rather than blocking all commits."""
    try:
        raw = _EN_JSON.read_text(encoding="utf-8")
        data = json.loads(raw)
        return _collect_plural_keys(data)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"i18n-plural-third-arg: WARNING — could not load {_EN_JSON}: {exc}", file=sys.stderr)
        return set()


# ---------------------------------------------------------------------------
# Regex patterns
#
# We look for  [$]t(  followed by a single-/double-quoted string key  then
# capture everything up to the first closing paren at depth-0 so we can
# count the top-level comma-separated arguments.
#
# Limitation: the regex does NOT handle multi-line calls that span more than
# ~5 lines, but all known plural calls in the codebase are single-line.
# A simpler approach: scan each file line by line and also a sliding window
# of up to 6 lines joined to catch typical wrapped calls.
# ---------------------------------------------------------------------------

# Matches the start of a t() or $t() call together with the key argument.
# Group 1: the quote char (' or ")
# Group 2: the key string
_CALL_START = re.compile(
    r"""
    \$?t\s*\(\s*          # t( or $t(  (optional leading $)
    (['"])                 # opening quote — group 1
    ([^'"]+?)             # key — group 2
    \1                    # closing quote (same as opening)
    \s*,                  # comma separating key from next arg
    """,
    re.VERBOSE,
)

# After the key+comma we need to check whether there is a 3rd positional arg.
# A 3rd arg is present when, after the 2nd argument (which may be an object
# literal  {...}  or a plain expression), there is another comma followed by
# something other than optional whitespace and a closing paren.
#
# Strategy: from the position after the comma following the key, find the
# end of the 2nd argument by tracking brace depth, then check for a 3rd comma.


def _has_third_arg(text: str, pos: int) -> bool:
    """Given *text* and *pos* pointing to the start of the 2nd argument
    (after the key comma), return True if a 3rd top-level argument exists.

    Handles nested braces/brackets/parens and single-/double-quoted strings.
    Returns True (safe/OK) on any parse ambiguity.
    """
    depth = 0  # brace/bracket/paren nesting depth
    in_str: str | None = None  # current quote char if inside a string literal
    i = pos
    length = len(text)

    while i < length:
        ch = text[i]

        if in_str:
            if ch == "\\" and i + 1 < length:
                i += 2  # skip escaped character
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch in ("{", "[", "("):
                depth += 1
            elif ch in ("}", "]", ")"):
                if depth == 0:
                    # End of the t() call itself — no 3rd arg found
                    return False
                depth -= 1
            elif ch == "," and depth == 0:
                # Top-level comma — this separates the 2nd arg from a 3rd
                return True

        i += 1

    # Reached end of text without closing paren — treat as OK (no violation)
    return True


def check_file(path: Path, plural_keys: set[str]) -> list[str]:
    """Return a list of violation messages for *path*."""
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    lines = source.splitlines()

    # We scan three representations to catch single-line and short multi-line calls:
    #  1. Each line individually (most calls are single-line)
    #  2. A sliding window of up to 6 consecutive lines joined with a space
    #     (handles calls that wrap across a few lines)
    # To report accurate line numbers we record line offsets.

    # Build character offset -> line number map for the full source
    line_start_offsets: list[int] = []
    offset = 0
    for line in lines:
        line_start_offsets.append(offset)
        offset += len(line) + 1  # +1 for the newline

    def lineno_for_offset(o: int) -> int:
        # Binary search for the line containing character offset o
        lo, hi = 0, len(line_start_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_start_offsets[mid] <= o:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1  # 1-based

    # Scan the full source text in one pass
    for m in _CALL_START.finditer(source):
        key = m.group(2)
        if key not in plural_keys:
            continue

        # pos points to the start of the 2nd argument
        pos = m.end()
        if not _has_third_arg(source, pos):
            line = lineno_for_offset(m.start())
            violations.append(
                f"{path}:{line}: t('{key}', ...) — plural key requires a 3rd "
                f"positional count arg: t('{key}', {{ count: n }}, n)"
            )

    return violations


def main(argv: list[str]) -> int:
    plural_keys = _load_plural_keys()
    if not plural_keys:
        # en.json unreadable — skip silently to avoid blocking unrelated commits
        return 0

    all_violations: list[str] = []

    for arg in argv:
        path = Path(arg)
        if path.suffix not in {".ts", ".vue"}:
            continue
        all_violations.extend(check_file(path, plural_keys))

    if all_violations:
        print("i18n-plural-third-arg: t(plural-key, …) calls missing the required " "3rd count argument:\n")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nFix: pass the count as a 3rd positional argument to enable plural selection:\n"
            "  t('chat.messages.attachments', { count: n }, n)\n"
            "  $t('ui.offlineBanner.queuedForRetry', { count: n }, n)\n"
            "\nSee: https://vue-i18n.intlify.dev/guide/essentials/pluralization"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
