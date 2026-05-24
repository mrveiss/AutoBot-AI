#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: reject Python files exceeding MAX_LINES lines.

Extracted from orchestrator.py (#5060) to prevent god-module regressions.
Files listed in KNOWN_LARGE are grandfathered — they are actively being
decomposed and will be removed from this exclusion as they shrink.
"""

import pathlib
import sys

MAX_LINES = 600

# Grandfathered files: currently >600 lines but under active decomposition.
# Remove each entry once the file reaches ≤600 lines.
KNOWN_LARGE = {
    "autobot-backend/orchestrator.py",  # 779 lines (#5060 — target <800)
    "autobot-backend/chat_workflow/manager.py",
    "autobot-backend/chat_workflow/tool_handler.py",
}


def main() -> int:
    violations = []
    for arg in sys.argv[1:]:
        p = pathlib.Path(arg)
        # Normalise to forward-slash relative path for set lookup
        rel = str(p).replace("\\", "/")
        if any(rel.endswith(known.replace("\\", "/")) for known in KNOWN_LARGE):
            continue
        try:
            line_count = sum(1 for _ in p.open(encoding="utf-8"))
        except OSError:
            continue
        if line_count > MAX_LINES:
            violations.append(f"{arg}: {line_count} lines (max {MAX_LINES})")

    if violations:
        print("\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
