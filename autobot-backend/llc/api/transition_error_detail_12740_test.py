# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC domain errors must surface their reason, not 'Internal server error' (#12740).

An illegal work-item transition returned 422 {"detail": "Internal server error"}
even though the service had already computed the exact, useful reason —
"Cannot transition from X to Y. Allowed: [...]". Swallowing it left the UI
unable to tell the user what went wrong or what IS permitted.

422 was also the wrong code: the request is well-formed (422 implies malformed);
it conflicts with the item's current state, which is 409.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_API = pathlib.Path(__file__).resolve().parent


def _handlers_for(module: str, exc_name: str):
    """Yield every `except <exc_name>` handler body in *module*."""
    tree = ast.parse((_API / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            name = getattr(node.type, "id", None)
            if name == exc_name:
                yield node


def _raises_http(handler) -> tuple[int | None, str]:
    """Return (status_code, detail-source) from the handler's raise."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            kw = {k.arg: k.value for k in node.exc.keywords}
            status = getattr(kw.get("status_code"), "value", None)
            detail = kw.get("detail")
            return status, ast.unparse(detail) if detail is not None else ""
    return None, ""


@pytest.mark.parametrize("module", ["work_items.py", "boards.py"])
def test_invalid_transition_returns_409_with_the_real_reason(module):
    handlers = list(_handlers_for(module, "InvalidTransition"))
    assert handlers, f"no InvalidTransition handler in {module}"
    for h in handlers:
        status, detail = _raises_http(h)
        assert status == 409, f"{module}: expected 409 Conflict, got {status}"
        assert "str(exc)" in detail, f"{module}: detail must carry the reason, got {detail!r}"
        assert "Internal server error" not in detail


def test_checkout_conflict_also_surfaces_who_holds_it():
    """Same defect class: correct code, but the reason was still swallowed."""
    handlers = list(_handlers_for("work_items.py", "CheckoutConflict"))
    assert handlers
    for h in handlers:
        status, detail = _raises_http(h)
        assert status == 409
        assert "str(exc)" in detail


def test_no_domain_handler_still_returns_a_generic_message():
    """Guard against regression across BOTH modules at once."""
    for module in ("work_items.py", "boards.py"):
        for exc_name in ("InvalidTransition", "CheckoutConflict"):
            for h in _handlers_for(module, exc_name):
                _, detail = _raises_http(h)
                assert "Internal server error" not in detail, f"{module}/{exc_name} still swallows"
