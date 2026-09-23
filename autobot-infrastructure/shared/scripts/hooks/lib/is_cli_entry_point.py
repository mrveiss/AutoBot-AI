# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exit 0 if the file has a top-level `if __name__ == "__main__"` NODE (#16008).

Parsed rather than matched. `grep -E '^if __name__ == .__main__.:'` reads raw
text, so a library module whose docstring happens to contain that line at column
zero read as a standalone entry point, became exempt from the print guard, and
had its real `print()` calls go unscanned. That is #16011's finding -- a
line-oriented scanner cannot see that a line is inside a string -- occurring
inside the change that cited it.

Every failure exits 1, which means NOT exempt, which means SCANNED. A file this
cannot parse is a file whose shape is unknown, and the safe answer to an unknown
shape is to look at it rather than to wave it through.
"""

from __future__ import annotations

import ast
import sys

_GUARD = '__name__ == "__main__"'


def is_entry_point(source: str) -> bool:
    """Whether a top-level `if __name__ == "__main__"` guard exists in *source*."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    # `tree.body` only -- a guard nested inside a function or class is not the
    # module-level entry point this exemption is about, and matching one would
    # re-open the hole through a different door.
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test).replace("'", '"') == _GUARD:
            return True
    return False


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 1
    try:
        source = open(argv[1], encoding="utf-8").read()  # noqa: SIM115
    except OSError:
        return 1
    return 0 if is_entry_point(source) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
