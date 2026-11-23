# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21375 guard: no route module writes an ``attempted`` audit row except through the shared helper.

An audit-first route records ``attempted``, changes state, then records the outcome linked to it. That pair has ONE
implementation, ``services/audit/outcome.py``. A route module under ``api/`` may name the ``attempted`` result only as
an argument of ``audit_secret_op`` (the adapter onto that helper) or ``record_audit_attempt``; any other call that
carries it (``audit_log``, ``record``, ``AuditEvent``, ``replace(..., outcome="attempted")``, a private ``_audit``)
is a second mechanism and fails here.

Boundary: this reads ``api/`` (subpackages included) only, which is where the routes are. ``services/`` still holds approval actions with
their own ``_audit(..., "attempted")`` helpers; they are not routes and are tracked separately on the issue.
"""

import ast
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2] / "api"
_SHARED = frozenset({"audit_secret_op", "record_audit_attempt"})


def _carries_attempted(call: ast.Call) -> bool:
    values = [*call.args, *(kw.value for kw in call.keywords)]
    return any(
        (isinstance(v, ast.Constant) and v.value == "attempted") or (isinstance(v, ast.Name) and v.id == "ATTEMPTED")
        for v in values
    )


def _callee(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def unshared_attempts(source: str) -> list[int]:
    """Line numbers of calls that write ``attempted`` through anything but the shared helper."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _carries_attempted(node) and _callee(node) not in _SHARED
    ]


def _route_modules() -> list[Path]:
    return [p for p in sorted(API_DIR.rglob("*.py")) if not p.name.endswith("_test.py") and "tests" not in p.parts]


def test_every_attempted_row_of_a_route_goes_through_the_shared_helper() -> None:
    modules = _route_modules()
    assert len(modules) > 50, "the scan found no route modules: the guard would pass vacuously"
    found = {p.name: lines for p in modules if (lines := unshared_attempts(p.read_text(encoding="utf-8")))}
    assert found == {}, f"route modules writing an attempted row outside services/audit/outcome.py: {found}"


def test_the_scan_sees_the_routes_that_do_use_the_helper() -> None:
    """A positive reach check: the helper's callers are real, so an empty finding is not an empty scan."""
    users = [p.name for p in _route_modules() if "audit_secret_op" in p.read_text(encoding="utf-8")]
    assert {"secrets.py", "envelope_secrets_delete.py"} <= set(users)


def test_planted_second_mechanisms_are_caught() -> None:
    """Positive control: each way of writing its own attempt row is found; the shared helper is not."""
    planted = [
        'await audit_log("secret.delete", "attempted", durable=True)',
        'event = AuditEvent(category=c, action="x", actor_id="u", outcome="attempted")',
        "await record_committed(replace(event, outcome=ATTEMPTED))",
        'await _audit(review, "attempted", secret_id)',
    ]
    for source in planted:
        assert unshared_attempts(source) == [1], source
    assert unshared_attempts('await audit_secret_op("DELETE", ref, request, "attempted", required=True)') == []
    assert unshared_attempts("await record_audit_attempt(event)") == []


def binds_record_committed(source: str) -> bool:
    """Whether the module binds ``record_committed`` by name (a second patch seam for the one store function)."""
    return any(
        isinstance(n, ast.ImportFrom) and any(a.name == "record_committed" for a in n.names)
        for n in ast.walk(ast.parse(source))
    )


def test_outcome_reaches_the_store_through_its_module_not_a_bound_name() -> None:
    """One seam: a patch on ``services.audit.audit.record_committed`` must reach every attempt route (#21375)."""
    source = (Path(__file__).resolve().parent / "outcome.py").read_text(encoding="utf-8")
    assert not binds_record_committed(source), "outcome.py must call audit.record_committed, not bind the name"


def test_a_bound_name_is_flagged() -> None:
    """Positive control."""
    assert binds_record_committed("from services.audit.audit import record_committed")
    assert binds_record_committed("from services.audit.audit import record_committed as rc")
    assert not binds_record_committed("from services.audit import audit as audit_store")
