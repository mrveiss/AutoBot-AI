# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Guard against the create_success_response footgun (#10234).

`utils/response_helpers.create_success_response()` returns a `DataResponse[T]`
**Pydantic model**. A route that declares ``response_model=Dict[str, Any]``
(or ``dict``) and returns the helper's result *directly* raises FastAPI
``ResponseValidationError`` → **HTTP 500 on success** (Pydantic v2 won't coerce
a model to ``dict``). It only manifests under a Dict response_model AND an
un-dumped return, so it is trivially reintroduced and silently ships broken
(no runtime test caught the original `chat_shared_links.py` regression, fixed
in #10233).

This AST guard fails CI if any route reintroduces the pattern: a
``response_model=Dict[str, Any]`` route whose ``return`` is a direct
``create_success_response(...)`` / ``create_error_response(...)`` call not
wrapped in ``.model_dump(...)``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HELPERS = {"create_success_response", "create_error_response"}
_DICT_RESPONSE_MODELS = {"Dict[str,Any]", "dict", "Dict", "dict[str,Any]"}
_API_DIR = Path(__file__).resolve().parents[2] / "api"


def _has_dict_response_model(node: ast.AST) -> bool:
    for dec in getattr(node, "decorator_list", []):
        for kw in getattr(dec, "keywords", []):
            if kw.arg == "response_model" and ast.unparse(kw.value).replace(" ", "") in _DICT_RESPONSE_MODELS:
                return True
    return False


def _returns_undumped_helper(func: ast.AST) -> list[int]:
    """Return line numbers of `return create_success_response(...)` (no .model_dump)."""
    bad = []
    for ret in (n for n in ast.walk(func) if isinstance(n, ast.Return)):
        val = ret.value
        if (
            isinstance(val, ast.Call)
            and isinstance(val.func, ast.Name)
            and val.func.id in _HELPERS
        ):
            bad.append(ret.lineno)
    return bad


def test_no_dict_response_model_returns_undumped_helper() -> None:
    offenders: list[str] = []
    for py in sorted(_API_DIR.rglob("*.py")):
        if py.stem.endswith("_test") or py.stem.startswith("test_"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not _has_dict_response_model(node):
                continue
            for lineno in _returns_undumped_helper(node):
                offenders.append(f"{py.name}:{lineno}")

    assert not offenders, (
        "create_success_response footgun (#10234): these routes declare "
        "response_model=Dict[str, Any] and return the helper directly without "
        ".model_dump(mode='json') → HTTP 500 on success:\n  " + "\n  ".join(offenders)
    )
