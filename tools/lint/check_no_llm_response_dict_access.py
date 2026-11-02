#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression-prevention check for the #6940 LLMResponse dict-style access pattern.

Background
----------
PR #6881 (#3185 LLMInterface retirement) found 7 production files calling
``response.get("content")`` / ``response_data.get("response")`` /
``response["content"]`` on objects whose runtime type is ``LLMResponse`` —
a Pydantic ``BaseModel``. Dict-style access on a model instance raises
``AttributeError`` at runtime, but tests were masking it via ``MockLLMInterface``
which accepted both shapes.

This hook prevents the regression by AST-scanning files that import
``LLMResponse`` for variable assignments like::

    response = await llm_service.chat(...)

…then flagging subsequent ``response.get(...)`` or ``response[key]`` access on
the assigned name. Files that don't import ``LLMResponse`` are exempt — the
``.get(...)`` access there is on a real dict.

Allowlist
---------
``autobot-backend/judges/__init__.py`` is exempt: it has an *intentional*
triple-fallback (``hasattr(.., 'content') -> .content``,
``isinstance(str)``, else legacy-dict ``.get('content', '')``) that supports
all three return shapes documented in #3185 Phase 2D. The else-branch dict
access is gated by the ``hasattr`` check above it, so the runtime path is
safe.

Exit code
---------
  0 — clean
  1 — banned patterns found
  2 — vacuous scan: root not a git toplevel, git failed, nothing reached,
      or a full-repo sweep landed under its floor (#14896)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# tools/lint/ is not a Python package; ensure sibling module is importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _check_harness import format_finding, run_anchored  # noqa: E402
from _scan_helpers import PY_FLOOR, scan_python_files  # noqa: E402

# LLM-service method names whose return value is LLMResponse. Variables
# assigned from these calls are tracked.
LLM_CHAT_METHODS = frozenset(
    {
        "chat",
        "chat_optimized",
        "achat_completion",
        "chat_completion",
        "generate",
        "complete",
    }
)

# Subscript/attr keys that signify the dict-shape access bug. ``.get("content")``
# on an LLMResponse hits AttributeError; on a dict it works.
DICT_ACCESS_KEYS = frozenset({"content", "response", "text", "message"})

# Files exempt from the check — see module docstring for rationale.
ALLOWLIST = frozenset(
    {
        # Intentional triple-fallback for LLMResponse | str | legacy-dict.
        "autobot-backend/judges/__init__.py",
        # The hook itself + tests reference the patterns as strings.
        "tools/lint/check_no_llm_response_dict_access.py",
        "tools/lint/check_no_llm_response_dict_access_test.py",
    }
)


def _imports_llm_response(tree: ast.AST) -> bool:
    """Return True if file imports ``LLMResponse`` from any module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "LLMResponse":
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(".LLMResponse"):
                    return True
    return False


def _is_llm_call(node: ast.AST) -> bool:
    """Return True if node is a call like ``svc.chat(...)``,
    ``await svc.chat_optimized(...)``, etc.
    """
    if isinstance(node, ast.Await):
        node = node.value
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in LLM_CHAT_METHODS
    return False


def _scan_file(path: Path, source: str) -> list[tuple[int, str]]:
    """Return [(line_no, message), …] for any banned access pattern."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # let other linters handle

    if not _imports_llm_response(tree):
        return []

    # Track variables assigned from an LLM chat call. Whole-file scope is fine
    # for our purposes — the pattern lives in single function bodies, and a
    # rebind in another function will still match if it's a real bug.
    tracked: dict[str, int] = {}  # var name → assignment lineno
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _is_llm_call(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        tracked[target.id] = node.lineno
        elif isinstance(node, ast.AnnAssign):
            # Explicit annotation: ``response: LLMResponse = ...``
            if (
                isinstance(node.annotation, ast.Name)
                and node.annotation.id == "LLMResponse"
                and isinstance(node.target, ast.Name)
            ):
                tracked[node.target.id] = node.lineno

    if not tracked:
        return []

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # `<var>.get("content")` style
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in tracked
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in DICT_ACCESS_KEYS
            ):
                findings.append(
                    (
                        node.lineno,
                        f"{node.func.value.id}.get({node.args[0].value!r}) — "
                        f"LLMResponse is a Pydantic model; use .content / .{node.args[0].value} attribute access",
                    )
                )
        # `<var>["content"]` style
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in tracked:
                # Pull literal subscript key
                key_node = node.slice if isinstance(node.slice, ast.Constant) else None
                if key_node and key_node.value in DICT_ACCESS_KEYS:
                    findings.append(
                        (
                            node.lineno,
                            f"{node.value.id}[{key_node.value!r}] — "
                            f"LLMResponse is a Pydantic model; use .{key_node.value} attribute access",
                        )
                    )
    return findings


_HOOK = "no-llm-response-dict-access"


def _summary(n: int) -> str:
    return (
        f"\n{n} LLMResponse dict-access violation(s) found.\n"
        "LLMResponse is a Pydantic BaseModel — use attribute access (.content, .response):\n"
        "  ❌ response.get('content', '')\n"
        "  ❌ response['content']\n"
        "  ✅ response.content\n"
        "  ✅ getattr(response, 'content', '')\n"
    )


def _rel_posix(path: Path, repo_root: Path) -> str:
    """*path* relative to the repo (POSIX) when it is inside it, else as given."""
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _file_findings(path: Path, repo_root: Path) -> list[str]:
    """Finding lines for one file; an allowlisted or unreadable file has none."""
    rel = _rel_posix(path, repo_root)
    if rel in ALLOWLIST:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [format_finding(rel, lineno, msg) for lineno, msg in _scan_file(path, source)]


def _collect(args: list[str], repo_root: Path) -> tuple[int, list[str]]:
    """``(files reached, finding lines)`` for *args* (empty = whole repo)."""
    files, _ = scan_python_files(args, repo_root)
    return len(files), [line for path in files for line in _file_findings(path, repo_root)]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    # Vacuity floor (#14896): full-repo mode only -- pre-commit legitimately
    # hands this hook an argv with no Python in it. Exit 2 = the scan proved nothing.
    return run_anchored(_HOOK, _collect, args, anchor=Path(__file__), floor=PY_FLOOR, summary=_summary)


if __name__ == "__main__":
    sys.exit(main())
