# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No dotted config key may be read through ConfigManager's flat ``get`` (#15575).

``ConfigManager.get`` is a flat top-level dict lookup; ``get_nested`` is the one
that walks a dotted path. Passing ``"logging.log_level"`` to ``get`` therefore
misses and returns the caller's fallback, silently, forever.

That defect produced two wrong fixes before this guard existed. #15575 first
renamed the key (``logging.level`` -> ``logging.log_level``) and shipped, because
the accompanying test stubbed the config manager with a fake implementing a
*correct flat-key contract* -- so it exercised the mock, not ``ConfigManager``,
and would have passed against any key name at all.

This guard reads the source rather than the behaviour precisely because the
behaviour can be mocked into agreeing. A dotted literal reaching ``.get(`` is a
syntactic fact no fixture can dress up.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Files that read config through a manager exposing both accessors.
_SCANNED = (
    "autobot_shared/logging_manager.py",
    "autobot-backend/services/config_service.py",
)

_DOTTED = re.compile(r"^[a-z_]+(\.[a-z_{}]+)+$", re.IGNORECASE)


def _dotted_flat_reads(source: str) -> list[tuple[int, str]]:
    """Every ``.get("a.b")`` call whose first argument looks like a dotted path."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get" or not node.args:
            continue
        first = node.args[0]
        text = None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            text = first.value
        elif isinstance(first, ast.JoinedStr):
            text = "".join(
                part.value if isinstance(part, ast.Constant) else "{}" for part in first.values
            )
        if text and _DOTTED.match(text):
            found.append((node.lineno, text))
    return found


def test_no_dotted_key_is_read_through_the_flat_get():
    """The defect #15575 shipped twice: a dotted key handed to a flat lookup."""
    offenders: list[str] = []
    for relative in _SCANNED:
        path = _REPO_ROOT / relative
        assert path.is_file(), f"FIX THE SWEEP: {relative} is not in the tree"
        for line, key in _dotted_flat_reads(path.read_text(encoding="utf-8")):
            offenders.append(f"{relative}:{line} reads {key!r} through .get()")

    assert offenders == [], (
        "dotted config keys read through ConfigManager.get, which is a FLAT lookup "
        "and returns the fallback instead: " + "; ".join(offenders) + ". Use get_nested()."
    )


def test_the_sweep_actually_parsed_the_files():
    """A vacuity floor: a scan that parsed nothing would pass silently."""
    total = sum(
        len(list(ast.walk(ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8")))))
        for rel in _SCANNED
    )
    assert total > 500, f"FIX THE SWEEP: only {total} AST nodes across {len(_SCANNED)} files"
