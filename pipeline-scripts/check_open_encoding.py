#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail on text-mode ``open()`` / ``aiofiles.open()`` calls without ``encoding=``.

CLAUDE.md: "Encoding | Always ``encoding='utf-8'`` explicitly". Without it Python
falls back to the platform locale, which silently mis-decodes non-ASCII content on
a non-UTF-8 system.

AST-based on purpose. A grep for ``open(`` matches documentation strings such as
``print("with open(file_path) as f:")`` and unrelated names like ``urlopen``, which
is why the earlier regex measurement of this rule was mostly false positives.

Binary modes are skipped — ``encoding=`` is invalid for them.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Bare `open(...)`.
_BARE = "open"

# Attribute-form calls that are text-capable and default to the locale.
# Deliberately an allow-list: `tarfile.open(p, "r:gz")` and `zipfile`/`gzip`/`bz2`/
# `lzma`/`shelve`/`dbm` also expose `.open`, are binary, and take no text
# `encoding` — matching every `*.open` flagged them (verified: 8 tarfile call
# sites). A miss is preferable to a gate that blocks correct code.
_ATTR_BASES = {"aiofiles", "io"}


def _mode_of(node: ast.Call) -> str:
    """Return the literal mode string for a call, or '' when not a literal."""
    if len(node.args) > 1:
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            return second.value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            return value if isinstance(value, str) else ""
    return ""


def _is_target(node: ast.Call) -> bool:
    """True for `open(...)`, `aiofiles.open(...)`, `io.open(...)` only."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _BARE
    if isinstance(func, ast.Attribute) and func.attr == _BARE:
        return isinstance(func.value, ast.Name) and func.value.id in _ATTR_BASES
    return False


def violations(path: Path) -> list[int]:
    """Return the line numbers of offending calls in ``path``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        # Unparseable or unreadable files are not this hook's concern; the
        # formatter and flake8 hooks report them with better messages.
        return []

    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_target(node):
            continue
        if "b" in _mode_of(node):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        found.append(node.lineno)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="files to check")
    args = parser.parse_args(argv)

    failed = False
    for name in args.filenames:
        path = Path(name)
        for lineno in violations(path):
            print(
                f"{path}:{lineno}: open() without encoding= — "
                f"add encoding='utf-8' (binary modes are exempt)"
            )
            failed = True

    if failed:
        print(
            "\nCLAUDE.md requires an explicit encoding on text-mode file I/O; "
            "the locale default corrupts non-ASCII content. See #13151."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
