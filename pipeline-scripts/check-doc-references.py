#!/usr/bin/env python3
"""
Doc reference linter for AutoBot developer guides.

Checks that file paths referenced (as backtick-quoted identifiers ending in
.py/.ts/.yml/.yaml/.sh/.md) in the canonical developer workflow docs still
exist somewhere in the repository source trees.

Only the docs engineers follow daily are checked.  Historical assessment and
implementation-report docs are intentionally excluded to avoid false positives
from files that were consolidated or deleted as part of past refactors.

Exit code: 0 if all references resolve, 1 otherwise.
"""

import re
import sys
from pathlib import Path

# Docs to validate — add new canonical guides here as they are created.
CHECKED_DOCS = [
    "CLAUDE.md",
    "docs/developer/CLAUDE_RULES.md",
    "docs/developer/CLAUDE_WORKFLOW.md",
    "docs/developer/AUTOBOT_REFERENCE.md",
    "docs/developer/DEVELOPER_SETUP.md",
    "docs/developer/SSOT_CONFIG_GUIDE.md",
    "docs/developer/REDIS_CLIENT_USAGE.md",
    "docs/developer/LOGGING_STANDARDS.md",
    "docs/developer/ERROR_CODE_CONVENTIONS.md",
]

# Source trees to search when a reference is not found by its full path.
SOURCE_TREES = [
    "autobot-backend",
    "autobot-slm-backend",
    "autobot-frontend",
    "autobot_shared",
    "autobot-infrastructure",
    "docs",
    "scripts",
    "pipeline-scripts",
    ".github",
]

# Pattern: backtick-quoted token that looks like a file path
_REF_RE = re.compile(r"`([a-zA-Z_/][a-zA-Z0-9_/.-]+\.(?:py|ts|yml|yaml|sh|md))`")


def check_reference(ref: str) -> bool:
    """Return True if *ref* resolves to an existing file."""
    clean = ref.lstrip("/")
    if Path(clean).exists():
        return True
    # Fall back to filename search across known source trees.
    name = Path(clean).name
    return any(list(Path(tree).glob(f"**/{name}")) for tree in SOURCE_TREES if Path(tree).exists())


def main() -> int:
    errors: list[str] = []
    checked = 0

    for doc_path in CHECKED_DOCS:
        md = Path(doc_path)
        if not md.exists():
            print(f"WARNING: canonical doc not found: {doc_path}", file=sys.stderr)
            continue
        text = md.read_text(encoding="utf-8")
        for match in _REF_RE.finditer(text):
            ref = match.group(1)
            checked += 1
            if not check_reference(ref):
                errors.append(f"{doc_path}: stale reference {ref!r}")

    print(f"Checked {checked} file references across {len(CHECKED_DOCS)} canonical docs.")

    if errors:
        print(f"\n{len(errors)} stale reference(s) found — update the doc or add the missing file:\n")
        for err in errors:
            print(f"  {err}")
        return 1

    print("All references resolve to existing files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
