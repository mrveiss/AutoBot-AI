#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Print the one-line installer exactly as INSTALL.md documents it (#19403).

The clean-install workflow runs what this prints, so CI exercises the command a reader
copies, not a paraphrase of it. The command is the first ``curl ... install.sh | sudo bash``
line inside a fenced block. ``install_oneliner.expected`` pins it: a doc change that alters
the command without a matching test change fails ``install_oneliner_test.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_ONELINER = re.compile(r"^curl \S.*/install\.sh \| sudo bash$")


def extract_oneliner(markdown: str) -> str:
    """The first documented one-liner, or SystemExit naming what is missing."""
    for block in _FENCE.findall(markdown):
        for line in block.splitlines():
            if _ONELINER.match(line.strip()):
                return line.strip()
    raise SystemExit("no `curl ... install.sh | sudo bash` line in a fenced block of INSTALL.md")


def main(argv: list[str]) -> int:
    doc = Path(argv[1]) if len(argv) > 1 else ROOT / "INSTALL.md"
    sys.stdout.write(extract_oneliner(doc.read_text(encoding="utf-8")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
