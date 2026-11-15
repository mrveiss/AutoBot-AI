# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC domain errors must surface their reason, not 'Internal server error' (#12740, #21579).

An illegal work-item transition returned 422 {"detail": "Internal server error"}
even though the service had already computed the exact, useful reason —
"Cannot transition from X to Y. Allowed: [...]". Swallowing it left the UI
unable to tell the user what went wrong or what IS permitted.

422 was also the wrong code: the request is well-formed (422 implies malformed);
it conflicts with the item's current state, which is 409.

Since #21579 the reason reaches the caller through ``http_refusal``, which answers with the exception's
``public_detail``. These guards check that the handlers raise ``http_refusal(409, ...)`` and that the
two exceptions are public by construction (``PublicMessageMixin``), never ``str(exc)``.
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


def _status_of(node: ast.expr) -> int | None:
    if isinstance(node, ast.Attribute):
        return {"HTTP_409_CONFLICT": 409}.get(node.attr)
    return getattr(node, "value", None)


def _refusal_status(node: ast.AST) -> int | None:
    """Status of an ``http_refusal(<status>, exc, ...)`` call node, else None."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "http_refusal" and node.args:
        return _status_of(node.args[0])
    return None


def _helper_status(name: str) -> int | None:
    """The status the shared helper *name* in ``_common.py`` passes to ``http_refusal`` (#20478, #21579)."""
    tree = ast.parse((_API / "_common.py").read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == name:
            for node in ast.walk(fn):
                found = _refusal_status(node)
                if found is not None:
                    return found
    raise AssertionError(f"helper {name} builds no http_refusal in _common.py")


def _raises_status(handler) -> int | None:
    """Status of the handler's raise, following ``raise refused_transition(exc)``."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            found = _refusal_status(node.exc)
            if found is not None:
                return found
            if getattr(node.exc.func, "id", None) == "refused_transition":
                return _helper_status("refused_transition")
            return None
    return None


def _is_public(class_name: str) -> bool:
    """True when *class_name* in the services package lists ``PublicMessageMixin`` among its bases."""
    for path in (_API.parent / "services").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return any(getattr(b, "id", None) == "PublicMessageMixin" for b in node.bases)
    raise AssertionError(f"{class_name} not found under services/")


@pytest.mark.parametrize("module", ["work_items.py", "boards.py", "agent_api.py"])
def test_invalid_transition_returns_409_with_the_real_reason(module):
    handlers = list(_handlers_for(module, "InvalidTransition"))
    assert handlers, f"no InvalidTransition handler in {module}"
    for h in handlers:
        assert _raises_status(h) == 409, f"{module}: expected an http_refusal 409 Conflict"
    assert _is_public("InvalidTransition"), "the reason reaches the caller only through public_detail"


def test_checkout_conflict_also_surfaces_who_holds_it():
    """Same defect class: correct code, but the reason was still swallowed."""
    handlers = list(_handlers_for("work_items.py", "CheckoutConflict"))
    assert handlers
    for h in handlers:
        assert _raises_status(h) == 409
    assert _is_public("CheckoutConflict")


def test_no_domain_handler_still_returns_a_generic_message():
    """Guard against regression across BOTH modules at once."""
    for module in ("work_items.py", "boards.py", "agent_api.py"):
        for exc_name in ("InvalidTransition", "CheckoutConflict"):
            for h in _handlers_for(module, exc_name):
                assert "Internal server error" not in ast.unparse(h), f"{module}/{exc_name} still swallows"


def _route_handlers(module: str, route: str, exc_name: str):
    """Yield the ``except <exc_name>`` handlers inside the route function *route* of *module* (#21587)."""
    tree = ast.parse((_API / module).read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name == route:
            for node in ast.walk(fn):
                if isinstance(node, ast.ExceptHandler) and getattr(node.type, "id", None) == exc_name:
                    yield node


#: Each refusal the handoff, review, transition, checkout, claim and agent status routes answer, with its true code.
_ROUTE_REFUSALS = [
    ("work_items.py", "handoff_to_agent", "HandoffNotAuthorized", 403),
    ("work_items.py", "handoff_to_agent", "ValueError", 404),
    ("work_items.py", "handoff_to_human", "HandoffNotAllowed", 403),
    ("work_items.py", "handoff_to_human", "ValueError", 404),
    ("work_items.py", "review_approve", "HandoffNotAllowed", 403),
    ("work_items.py", "review_approve", "InvalidTransition", 409),
    ("work_items.py", "review_approve", "ValueError", 404),
    ("work_items.py", "review_request_changes", "HandoffNotAllowed", 403),
    ("work_items.py", "review_request_changes", "ValueError", 404),
    ("work_items.py", "transition_work_item", "InvalidTransition", 409),
    ("work_items.py", "transition_work_item", "ValueError", 404),
    ("work_items.py", "checkout_work_item", "ValueError", 404),
    ("work_items.py", "release_work_item", "ValueError", 400),
    ("work_items.py", "claim_work_item", "ValueError", 404),
    ("work_items.py", "unclaim_work_item", "ValueError", 400),
    ("work_items.py", "get_handoff_brief", "ValueError", 404),
    ("agent_api.py", "update_work_item_status", "InvalidTransition", 409),
    ("agent_api.py", "update_work_item_status", "ValueError", 404),
    ("agent_api.py", "agent_upload_attachment", "AttachmentTooLarge", 413),
]


@pytest.mark.parametrize(("module", "route", "exc_name", "code"), _ROUTE_REFUSALS)
def test_every_refusal_route_answers_its_true_code_through_the_shared_helper(module, route, exc_name, code):
    handlers = list(_route_handlers(module, route, exc_name))
    assert handlers, f"{module}:{route} has no `except {exc_name}` handler"
    for h in handlers:
        assert _raises_status(h) == code, f"{module}:{route} {exc_name}: expected an http_refusal {code}"


@pytest.mark.parametrize(
    "exc_name", ["HandoffNotAuthorized", "HandoffNotAllowed", "CompanyOsError", "AttachmentTooLarge"]
)
def test_the_handoff_refusals_are_public_so_the_caller_sees_the_reason(exc_name):
    assert _is_public(exc_name), f"{exc_name} answers a fixed text, not its reason, unless it is a PublicMessageMixin"


@pytest.mark.parametrize("module", ["work_items.py", "agent_api.py"])
def test_no_work_item_route_answers_internal_server_error_for_a_refusal(module):
    """The text is never a refusal's answer: a refused or missing item is a 4xx with a stated reason (#21587)."""
    tree = ast.parse((_API / module).read_text(encoding="utf-8"))
    offenders = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "Internal server error"]
    assert not offenders, f"{module} still answers 'Internal server error' at lines {offenders}"
