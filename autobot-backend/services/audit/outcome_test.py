# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21375 / #22130 guard: no backend module writes an ``attempted`` audit row except through the shared helper.

An audit-first control records ``attempted``, changes state, then records the outcome linked to it. That pair has ONE
implementation, ``services/audit/outcome.py``. A backend module may name the ``attempted`` result only as an argument
of ``audit_secret_op`` (the route adapter onto that helper), ``record_audit_attempt`` or ``record_control_attempt``; any other
call that carries it (``audit_log``, ``record``, ``AuditEvent``, ``replace(..., outcome="attempted")``, a private
``_audit``) is a second mechanism and fails here.

Boundary: this reads EVERY non-test module under the backend (routes, services, security, subpackages), except the
implementation itself. A module still on its own writer is listed in ``_UNMIGRATED`` with the reason; the entry is
checked to be real, so it must be removed the moment the module moves.
"""

import ast
from pathlib import Path

from autobot_shared.testfile_names import is_test_filename

BACKEND_DIR = Path(__file__).resolve().parents[2]
API_DIR = BACKEND_DIR / "api"
_SHARED = frozenset({"audit_secret_op", "record_audit_attempt", "record_control_attempt"})
_IMPLEMENTATION = "services/audit/outcome.py"
_SKIPPED_PARTS = frozenset({"tests", "node_modules", "venv", ".venv", "__pycache__", "site-packages"})
#: Modules still writing their own pair, by path under the backend. The file is held by an open PR (the same-file
#: rule: one PR per file), so it moves in a follow-up, tracked on the issue named here.
_UNMIGRATED = {"security/session_share_audit.py": "held by an open PR; follow-up #22409"}


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


def _backend_modules() -> list[Path]:
    """Every non-test backend module except the helper's own implementation."""
    return [
        p
        for p in sorted(BACKEND_DIR.rglob("*.py"))
        if not is_test_filename(p.name, include_js=False)
        and not _SKIPPED_PARTS & set(p.relative_to(BACKEND_DIR).parts)
        and p.relative_to(BACKEND_DIR).as_posix() != _IMPLEMENTATION
    ]


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND_DIR).as_posix()


def test_every_attempted_row_of_a_backend_module_goes_through_the_shared_helper() -> None:
    modules = _backend_modules()
    assert len(modules) > 500, "the scan found too few backend modules: the guard would pass vacuously"
    found = {_relative(p): lines for p in modules if (lines := unshared_attempts(p.read_text(encoding="utf-8")))}
    found = {path: lines for path, lines in found.items() if path not in _UNMIGRATED}
    assert found == {}, f"modules writing an attempted row outside services/audit/outcome.py: {found}"


def test_an_unmigrated_entry_is_still_a_private_writer() -> None:
    """A listed module that no longer writes its own attempt must leave the list, or the exemption outlives it."""
    for path in _UNMIGRATED:
        assert unshared_attempts((BACKEND_DIR / path).read_text(encoding="utf-8")), f"{path} is migrated: unlist it"


def test_the_scan_sees_the_modules_that_do_use_the_helper() -> None:
    """A positive reach check: the helper's callers are real routes and services, so an empty finding is not an
    empty scan."""
    users = {
        _relative(p)
        for p in _backend_modules()
        if any(name in p.read_text(encoding="utf-8") for name in ("audit_secret_op", "record_control_attempt"))
    }
    assert {
        "api/secrets.py",
        "api/envelope_secrets_delete.py",
        "services/chat_session_owner_action.py",
        "services/install_cleanup_actions.py",
        "services/kb_approved_delete.py",
        "services/mcp_external_bridge.py",
        "services/org_tier_column_action.py",
        "services/secret_duplicate_cleanup_action.py",
        "services/secrets_maintenance.py",
        "services/verifier_audit.py",
    } <= users


def test_planted_second_mechanisms_are_caught() -> None:
    """Positive control: each way of writing its own attempt row is found; the shared helper is not."""
    planted = [
        'await audit_log("secret.delete", "attempted", durable=True)',
        'event = AuditEvent(category=c, action="x", actor_id="u", outcome="attempted")',
        "await record_committed(replace(event, outcome=ATTEMPTED))",
        'await _audit(review, "attempted", secret_id)',
        'await _audit(approval, _AUDIT, "attempted", phase="intent", paths=names)',
        'await audit("attempted", {**intent, "phase": "intent"})',
        'await _audit_tool_call("attempted", user_id, name, details, session_id)',
        'await audit_log(action.value, result="attempted", user_id=actor, durable=True)',
    ]
    for source in planted:
        assert unshared_attempts(source) == [1], source
    assert unshared_attempts('await audit_secret_op("DELETE", ref, request, "attempted", required=True)') == []
    assert unshared_attempts("await record_audit_attempt(event)") == []
    assert unshared_attempts('await record_control_attempt("session.owner_assign", user_id=actor, details=details)') == []


def test_a_planted_private_writer_in_a_service_module_fails_the_scan(tmp_path: Path) -> None:
    """Positive control on the scan itself: a service-shaped module with its own attempt writer is reported."""
    planted = tmp_path / "services" / "planted_action.py"
    planted.parent.mkdir()
    planted.write_text(
        "async def _audit(approval, result):\n    ...\n\n"
        "async def run(approval):\n    await _audit(approval, 'attempted')\n",
        encoding="utf-8",
    )
    assert unshared_attempts(planted.read_text(encoding="utf-8")) == [5]


def test_the_secrets_route_names_attempted_only_where_the_guard_allows() -> None:
    """Positive control on the real module: it compares against ``attempted`` but never passes it to a writer."""
    source = (API_DIR / "secrets_audit.py").read_text(encoding="utf-8")
    assert "ATTEMPTED" in source and unshared_attempts(source) == []


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


# -- the service-side pair (#22130) --------------------------------------------------------------------------------


async def test_record_attempt_writes_the_attempted_row_and_record_outcome_links_to_it() -> None:
    from services.audit.outcome import SUCCESS, record_control_attempt, record_control_outcome
    from tests.helpers.audit_double import AuditDouble

    audit = AuditDouble()
    with audit.patch():
        attempt = await record_control_attempt("session.owner_assign", user_id="alice", resource="s1", details={"stage": "a"})
        assert attempt is not None and await record_control_outcome(attempt, SUCCESS, details={"stage": "b"})
    assert audit.results == ["attempted", "success"]
    assert audit.events[1].metadata["attempt_id"] == attempt.id and audit.events[1].id != attempt.id
    assert [d["stage"] for d in audit.details] == ["a", "b"]  # the outcome's fields are added to the attempt's
    assert audit.events[1].occurred_at >= attempt.occurred_at


async def test_an_unwritable_attempt_is_none_so_the_caller_changes_nothing() -> None:
    from services.audit.outcome import record_control_attempt
    from tests.helpers.audit_double import AuditDouble, unwritable_attempt

    for written in (unwritable_attempt, OSError("store down")):
        with AuditDouble(written).patch():
            assert await record_control_attempt("session.owner_assign", user_id="alice") is None


async def test_an_unwritable_outcome_is_logged_not_raised(caplog) -> None:
    from services.audit.outcome import FAILED, OUTCOME_MISSING_MARKER, record_control_attempt, record_control_outcome
    from tests.helpers.audit_double import AuditDouble

    audit = AuditDouble()
    with audit.patch():
        attempt = await record_control_attempt("session.owner_assign", user_id="alice")
    audit.written = False
    with audit.patch(), caplog.at_level("ERROR"):
        assert await record_control_outcome(attempt, FAILED, "ValueError") is False
    assert OUTCOME_MISSING_MARKER in caplog.text
    assert audit.events[-1].metadata["failure"] == "ValueError"
