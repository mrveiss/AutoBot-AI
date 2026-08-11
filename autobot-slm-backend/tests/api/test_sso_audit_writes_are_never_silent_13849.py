# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No SSO audit-log write may fail silently (#13849).

`sso_auth.py` wraps every `create_audit_log` call in a try/except so that a
failing audit database cannot break authentication — correct, and deliberate.
Seven of those handlers logged the failure. One did not:

    except Exception:
        pass          # the SAML SLO *failure* path

Its direct sibling twelve lines below — the SLO *success* path — logs it. So the
one branch where an audit record matters most was the only one that dropped both
the record and the fact that it had been dropped.

An audit trail that loses entries silently is worse than one known to be
incomplete: during a review, absence of evidence reads as evidence of absence.

Scope is this file on purpose. The umbrella (#13852) records that a repo-wide
sweep found 238 candidate silent handlers, that only 8 wrapped a persistence
call, and that 7 of those carry inline justifications — "the codebase is mostly
right about this", and a broad add-logging campaign was explicitly not proposed.
This asserts the invariant where it was actually broken.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SSO_AUTH = Path(__file__).resolve().parents[2] / "api" / "sso_auth.py"


def _tree() -> ast.Module:
    return ast.parse(_SSO_AUTH.read_text(encoding="utf-8"))


def _calls_audit_log(node: ast.AST) -> bool:
    """True if this subtree calls create_audit_log."""
    return any(
        isinstance(inner, ast.Call)
        and (
            (isinstance(inner.func, ast.Name) and inner.func.id == "create_audit_log")
            or (isinstance(inner.func, ast.Attribute) and inner.func.attr == "create_audit_log")
        )
        for inner in ast.walk(node)
    )


def _handler_is_silent(handler: ast.ExceptHandler) -> bool:
    """True if the handler neither logs nor re-raises — i.e. swallows."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}:
                return False
    return True


def _audit_write_handlers() -> list[tuple[int, ast.ExceptHandler]]:
    """Every except-handler guarding a create_audit_log call, with its line."""
    found: list[tuple[int, ast.ExceptHandler]] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Try) and _calls_audit_log(node):
            for handler in node.handlers:
                found.append((handler.lineno, handler))
    return found


def test_the_file_still_has_audit_writes_to_check():
    """Guard the guard: a rename or refactor that stops matching would make
    every assertion below pass against nothing."""
    handlers = _audit_write_handlers()
    assert len(handlers) >= 7, f"expected the file's audit-write handlers, found {len(handlers)}"


@pytest.mark.parametrize(
    "lineno,handler",
    _audit_write_handlers(),
    ids=lambda v: f"line{v}" if isinstance(v, int) else "",
)
def test_no_audit_write_failure_is_swallowed(lineno: int, handler: ast.ExceptHandler):
    """Each handler must log or re-raise — never `pass`.

    Line 476 was the exception: on the SAML SLO failure path, a failed audit
    write left no record of the failure AND no record that the record was lost.
    """
    assert not _handler_is_silent(handler), (
        f"sso_auth.py:{lineno} swallows a failed audit-log write. Losing the audit "
        "record is bad; losing the fact that it was lost is worse (#13849)"
    )


def test_the_slo_failure_path_logs_like_its_success_sibling():
    """Named explicitly — it is the incident, and its sibling is the proof the
    swallow was an oversight rather than a decision."""
    source = _SSO_AUTH.read_text(encoding="utf-8")
    assert (
        source.count("SAML SLO audit write failed") >= 2
    ), "both the SLO success and failure paths must report a failed audit write"
