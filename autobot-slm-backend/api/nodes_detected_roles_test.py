# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`detected_roles` must record findings, not the probe list (#14513).

The agent probes EVERY known role and reports each one's verdict. The handler
recorded ``list(role_report.keys())``, discarding the verdict entirely, so every
node was marked as carrying everything. Observed live: two nodes running
completely different workloads reported byte-identical 20-entry lists, and the
manager's list even included ``vnc``, which it does not declare.

Because the inventory unions declared and detected roles, that promoted plain
fleet nodes into ``slm_server`` and pointed "Play 1 - Update SLM Server First"
at them.

The function is AST-extracted and executed rather than imported, following
``nodes_test.py``: ``api/nodes.py`` registers FastAPI routes at import time.
The real function body runs here — only its surroundings are skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

_NODES_PY = Path(__file__).parent / "nodes.py"
_WANTED = {"_detected_role_names"}


def _load_pure_functions() -> dict:
    tree = ast.parse(_NODES_PY.read_text(encoding="utf-8"), filename=str(_NODES_PY))
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _WANTED]
    assert len(wanted) == len(
        _WANTED
    ), f"expected {sorted(_WANTED)} in {_NODES_PY}, found {sorted(n.name for n in wanted)} — rename tracking broke"
    module = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {}
    exec(compile(module, filename=str(_NODES_PY), mode="exec"), namespace)  # noqa: S102
    return namespace


_detected_role_names = _load_pure_functions()["_detected_role_names"]


def _report(**statuses):
    """A role report as the agent sends it: every probed role, with a verdict."""
    return {name: SimpleNamespace(status=status) for name, status in statuses.items()}


def test_absent_roles_are_not_reported_as_detected():
    """The defect verbatim.

    A vnc node probes slm-backend, finds nothing, and says so. Recording the
    key anyway is what put it in slm_server.
    """
    report = _report(vnc="active", **{"slm-agent": "active", "slm-backend": "not_installed", "redis": "not_installed"})

    assert sorted(_detected_role_names(report)) == [
        "slm-agent",
        "vnc",
    ], "roles the agent reported as not_installed are still recorded as detected (#14513)"


def test_an_installed_but_stopped_role_still_counts():
    """`inactive` means present with its service down.

    Dropping those would hide installed roles from the fleet view and stop them
    receiving updates — a different bug in the opposite direction.
    """
    report = _report(**{"slm-backend": "inactive"})

    assert _detected_role_names(report) == ["slm-backend"]


def test_an_unreadable_verdict_does_not_count_as_detected():
    """This list grants group membership, so ambiguity must not promote.

    An entry with no status is exactly what `.keys()` effectively treated as
    present. Absence of a verdict is not evidence of a role.
    """
    assert _detected_role_names({"slm-backend": SimpleNamespace(status=None)}) == []
    assert _detected_role_names({"slm-backend": SimpleNamespace()}) == []


def test_a_dict_shaped_report_is_handled():
    """The wire form is a dict before pydantic parsing; both must work."""
    report = {"vnc": {"status": "active"}, "slm-backend": {"status": "not_installed"}}

    assert _detected_role_names(report) == ["vnc"]


def test_an_empty_or_missing_report_is_empty():
    assert _detected_role_names({}) == []
    assert _detected_role_names(None) == []


def test_the_whole_catalogue_does_not_become_the_node():
    """The live symptom, stated as a rule.

    Every node probes all 20 roles; a node running two of them must report two.
    """
    catalogue = [
        "ai-stack",
        "autobot-llm-cpu",
        "autobot-llm-gpu",
        "autobot_shared",
        "backend",
        "browser-service",
        "celery",
        "chromadb",
        "frontend",
        "npu-worker",
        "postgres",
        "redis",
        "scheduler",
        "slm-agent",
        "slm-backend",
        "slm-database",
        "slm-frontend",
        "slm-monitoring",
        "tts-worker",
        "vnc",
    ]
    report = _report(**{name: ("active" if name in ("vnc", "slm-agent") else "not_installed") for name in catalogue})

    detected = _detected_role_names(report)

    assert len(detected) == 2, f"probed {len(catalogue)} roles and recorded {len(detected)} as present"
    assert sorted(detected) == ["slm-agent", "vnc"]
