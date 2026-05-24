#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Codemod: remove parseApiResponse<T>(x) wrappers in Vue components.

Transforms the 2-line pattern:

    const response = await apiClient.METHOD(url, ...)    # or ApiClient.METHOD(...)
    const data = await parseApiResponse<T>(response)

into a single typed call:

    const data = await apiClient.METHOD<T>(url, ...)

Also drops the `import { parseApiResponse } from '@/utils/apiResponseHelpers'`
line once no parseApiResponse usage remains in the file.

Key design: only the *opener* of the apiClient call is patched (add `<T>`
and rename the binding) — args are left untouched. This makes multi-line
calls like `apiClient.post(url, { a, b, c })` work without needing a
multi-line paren matcher.

Used in PR #5177 to migrate 49 call sites across 17 Vue files (#5033).

Usage:
    python3 tools/codemods/parse_api_response_vue_migration.py \\
      $(grep -rln "parseApiResponse" autobot-frontend/src/components \\
        --include='*.vue')
"""

import re
import sys
from pathlib import Path

# Match the start of `const VAR = await (apiClient|ApiClient).METHOD(`.
# Works for single-line AND multi-line call bodies because we only patch
# the opener — the `(args)` span is left alone.
RESPONSE_OPEN = re.compile(r"^(\s*)const (\w+) = await " r"(apiClient|ApiClient)\.(get|post|put|delete|patch)\(")

# Match `const NEW_VAR = await parseApiResponse<TYPE>(PREV_VAR)` on one line.
# TYPE captures everything up to the final `(` — handles nested generics
# like `Record<string, any>` without needing brace counting.
PARSE_LINE = re.compile(r"^(\s*)const (\w+) = await parseApiResponse<([^(]+)>\((\w+)\)\s*$")

PARSE_IMPORT = re.compile(
    r"^import \{ parseApiResponse \} from '@/utils/apiResponseHelpers'\s*\n",
    flags=re.MULTILINE,
)


def transform(text: str) -> tuple[str, int]:
    """Return (transformed_text, number_of_migrations_applied)."""
    lines = text.splitlines(keepends=True)
    out_lines = list(lines)
    deletes: set[int] = set()
    count = 0

    for i, line in enumerate(out_lines):
        if i in deletes:
            continue
        pm = PARSE_LINE.match(line.rstrip("\n"))
        if not pm:
            continue

        new_var = pm.group(2)
        type_arg = pm.group(3).strip()
        prev_var = pm.group(4)

        # Walk back up to ~15 lines to find the matching
        # `const PREV_VAR = await ...METHOD(` opener.
        match_idx: int | None = None
        for j in range(i - 1, max(i - 15, -1), -1):
            if j in deletes:
                continue
            rm = RESPONSE_OPEN.match(out_lines[j])
            if rm and rm.group(2) == prev_var:
                match_idx = j
                break

        if match_idx is None:
            continue  # Pattern doesn't match cleanly; skip this site.

        # Patch only the opener: rename the binding and type the method.
        original = out_lines[match_idx]
        patched = RESPONSE_OPEN.sub(
            lambda m: (f"{m.group(1)}const {new_var} = await " f"{m.group(3)}.{m.group(4)}<{type_arg}>("),
            original,
            count=1,
        )
        out_lines[match_idx] = patched
        deletes.add(i)
        count += 1

    new_lines = [line for idx, line in enumerate(out_lines) if idx not in deletes]
    text2 = "".join(new_lines)

    # Drop `import { parseApiResponse }` if no uses remain.
    if "parseApiResponse" not in text2.replace("import { parseApiResponse }", ""):
        text2 = PARSE_IMPORT.sub("", text2)

    return text2, count


def main(paths: list[str]) -> None:
    total = 0
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"SKIP (missing): {p}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        new_text, n = transform(text)
        if n > 0:
            path.write_text(new_text, encoding="utf-8")
            print(f"  {n:3d} migrated: {p}")
            total += n
    print(f"Total: {total}")


if __name__ == "__main__":
    main(sys.argv[1:])
