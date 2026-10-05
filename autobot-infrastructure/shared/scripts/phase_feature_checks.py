# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Feature checks that read a declaration rather than a filename (#17674).

STDLIB-ONLY, AND THAT IS THE POINT. `phase_validation_system` imports aiohttp,
psutil, requests and `autobot_shared.redis_client` at module scope, and the
last of those WRITES secret key material when none is configured -- so a guard
cannot import it to test these functions without mutating the tree it guards.
Kept here, beside `phase_score.py`, these load by path like the other
stdlib-only policy modules and can be tested directly.

EXISTENCE IS NOT CAPABILITY. The first version of both validators returned
`path.exists()`, so an empty compose file reported "containerization
implemented" -- the same inversion #17559 removed one layer up, where a feature
with no validator counted as implemented.
"""

from __future__ import annotations

import ast
from pathlib import Path


def declares_compose_services(path: Path) -> bool:
    """True when the compose file declares at least one service.

    EXISTENCE IS NOT CAPABILITY (CodeRabbit, #17674). The first version of this
    validator returned `path.exists()`, which reports "containerization
    implemented" for an empty file -- the same inversion this PR removes one
    layer up, where a feature with no validator counted as implemented.

    This reads a declaration, not a running container. It cannot tell a
    service that starts from one that crashes, and it is not claimed to.
    Parsed by hand because this module is stdlib-only and adding PyYAML to an
    infrastructure script to answer one question is a worse trade.
    """
    if not path.is_file():
        return False
    in_services = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        key = raw.split(":", 1)[0].strip()
        # NO COMMENT TEST HERE, deliberately (#17941). A key must start with an
        # identifier character, so `# services:` and `  # web:` fail the same
        # check that rejects any other non-key line -- one rule instead of a
        # private comment stripper beside it. This module is stdlib-only and
        # loaded by path, so it cannot import the canonical `_comment_syntax`.
        if not key[:1].isalnum() and key[:1] != "_":
            continue
        if not raw[:1].isspace():
            in_services = key == "services"
            continue
        # A service key is the first indent level inside `services:`.
        if in_services and raw.endswith(":") and len(raw) - len(raw.lstrip()) <= 4:
            return True
    return False


def defines_callable(path: Path) -> bool:
    """True when the script parses and defines at least one function.

    Same reasoning: a file that exists but does not parse, or that defines
    nothing, is not deployment automation. A SyntaxError here is a finding, not
    a reason to fall back to "present".
    """
    if not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
