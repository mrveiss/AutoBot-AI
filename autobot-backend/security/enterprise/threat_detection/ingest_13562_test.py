# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13562 — ``ThreatDetectionEngine`` must receive real events, in its own vocabulary.

Two failures are possible here and only one of them is about reachability.

1. **Nothing calls it.** The shipped state: the class existed, two ``__init__``
   re-exports and a docstring example referenced it, and no route, service or
   task ever constructed it.
2. **Something calls it and it can never fire.** The bus says
   ``action="run_jwt.mint"``, ``outcome="denied"``;
   ``SecurityEvent.is_authentication_failure`` requires ``action ==
   "authentication"`` and ``outcome == "failure"``, by exact string. A wiring
   without the translation would deliver events forever and detect nothing,
   and every reachability check in the world would pass over it.

So the translation is asserted against the **real** ``SecurityEvent``
predicates rather than against the mapping table that produced it. Asserting
``engine_action("run_jwt.mint") == "authentication"`` only proves the table
agrees with itself; feeding the output to the consumer proves the consumer
agrees.

The reachability half reads the AST. ``analyze_audit_event`` is named in
comments and docstrings in both files it touches, so a text search for it is
satisfied by the prose — :data:`PROSE_ONLY_FIXTURE` is that case made
executable.
"""

from __future__ import annotations

import ast
import sys
import time
from pathlib import Path
from typing import Any, Dict, Set

import pytest

from security.enterprise.threat_detection.ingest import (
    _reset_engine_for_testing,
    analyze_audit_event,
    audit_event_to_engine_event,
    engine_action,
    engine_outcome,
    get_threat_detection_engine,
)
from security.enterprise.threat_detection.models import SecurityEvent
from security.enterprise.threat_detection.types import FILE_OPERATION_ACTIONS

BACKEND = Path(__file__).resolve().parents[3]
AUDIT_BUS_PATH = BACKEND / "services" / "audit" / "audit.py"
INGEST_PATH = Path(__file__).resolve().parent / "ingest.py"

ENTRY = "analyze_audit_event"


def _audit_payload(**overrides: Any) -> Dict[str, Any]:
    """An ``AuditEvent.to_dict()`` as the unified bus emits it."""
    payload: Dict[str, Any] = {
        "id": "aaaa-bbbb",
        "category": "security",
        "action": "run_jwt.mint",
        "actor_id": "operator-7",
        "resource_type": "run",
        "resource_id": "run-42",
        "metadata": {"reason": "quota"},
        "occurred_at": time.time(),
        "ip_address": "10.0.0.9",
        "session_id": "sess-1",
        "outcome": "denied",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Translation — verified against the consumer, not against the table
# ---------------------------------------------------------------------------


def test_a_denied_credential_operation_reads_as_an_authentication_failure() -> None:
    """The regression that a reachability check cannot see.

    ``run_jwt.mint`` / ``denied`` is what the bus actually writes. Delivered
    untranslated, ``BruteForceAnalyzer`` would receive it and skip it forever.
    """
    event = SecurityEvent(raw_event=audit_event_to_engine_event(_audit_payload()))

    assert event.is_authentication_event()
    assert event.is_authentication_failure()
    assert event.user_id == "operator-7"
    assert event.source_ip == "10.0.0.9"


def test_the_untranslated_bus_vocabulary_would_detect_nothing() -> None:
    """The control that gives the test above its meaning.

    Without it, the assertion is satisfiable by a mapping that was never needed.
    """
    raw = _audit_payload()
    naive = SecurityEvent(raw_event={"action": raw["action"], "outcome": raw["outcome"]})

    assert not naive.is_authentication_event()
    assert not naive.is_authentication_failure()


@pytest.mark.parametrize(
    "bus_action,expected",
    [
        ("file.upload", "file_upload"),
        ("file.delete", "file_delete"),
        ("file.download", "file_read"),
        ("file.modify", "file_write"),
    ],
)
def test_file_actions_land_inside_the_set_the_engine_matches_on(bus_action: str, expected: str) -> None:
    """``is_file_operation`` is set membership, so a near-miss is a silent zero."""
    translated = engine_action(bus_action)

    assert translated == expected
    assert translated in FILE_OPERATION_ACTIONS
    assert SecurityEvent(raw_event={"action": translated}).is_file_operation()


def test_an_unrecognised_outcome_is_a_failure_not_a_success() -> None:
    """An unknown value scoring as success is how a detector reports clean."""
    assert engine_outcome("success") == "success"
    for value in ("denied", "failed", "error", "", "something-nobody-has-written-yet"):
        assert engine_outcome(value) == "failure", value


def test_an_ordinary_event_still_reaches_the_behavioural_analyzers() -> None:
    """Not every row is an auth or file event, and the engine must still see it."""
    event = SecurityEvent(raw_event=audit_event_to_engine_event(_audit_payload(action="knowledge.add")))

    assert event.is_api_request()
    assert not event.is_authentication_event()


# ---------------------------------------------------------------------------
# Delivery — the engine is actually called with the translated event
# ---------------------------------------------------------------------------


class _RecordingEngine:
    def __init__(self) -> None:
        self.seen: list[Dict[str, Any]] = []

    async def analyze_event(self, event: Dict[str, Any]):
        self.seen.append(event)
        return None


@pytest.mark.asyncio
async def test_the_engine_receives_the_translated_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through the ingest entry point the audit bus calls."""
    _reset_engine_for_testing()
    engine = _RecordingEngine()
    monkeypatch.setattr(
        "security.enterprise.threat_detection.ingest.get_threat_detection_engine",
        lambda: _async(engine),
    )

    await analyze_audit_event(_audit_payload())

    assert len(engine.seen) == 1
    assert engine.seen[0]["action"] == "authentication"
    assert engine.seen[0]["outcome"] == "failure"
    assert engine.seen[0]["audit_action"] == "run_jwt.mint", "the original action must survive for traceability"


@pytest.mark.asyncio
async def test_an_engine_that_cannot_be_built_never_breaks_the_audit_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A detector fault suppressing the audit trail is worse than a missed detection.

    ``None`` in ``sys.modules`` is how CPython represents a module whose import
    failed, so this reproduces an environment without scikit-learn rather than
    simulating one.
    """
    _reset_engine_for_testing()
    monkeypatch.setitem(sys.modules, "security.enterprise.threat_detection.engine", None)

    assert await get_threat_detection_engine() is None
    assert await analyze_audit_event(_audit_payload()) is None

    _reset_engine_for_testing()


async def _async(value: Any) -> Any:
    return value


# ---------------------------------------------------------------------------
# Reachability — read from the AST, never from the source text
# ---------------------------------------------------------------------------


def _called_names(tree: ast.AST) -> Set[str]:
    called: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            called.add(func.id)
        elif isinstance(func, ast.Attribute):
            called.add(func.attr)
    return called


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


PROSE_ONLY_FIXTURE = '''
"""The bus hands every row to analyze_audit_event."""

# await analyze_audit_event(event.to_dict())  # re-enable when sklearn ships

NOTE = "analyze_audit_event is the #13562 entry point"


async def record(event):
    return None
'''

REAL_CALL_FIXTURE = """
async def record(event):
    await analyze_audit_event(event.to_dict())
"""


def test_the_detector_finds_a_real_call() -> None:
    """Known positive — without it the assertions below measure nothing."""
    assert ENTRY in _called_names(ast.parse(REAL_CALL_FIXTURE))


def test_a_name_that_appears_only_in_prose_is_not_a_call() -> None:
    """A grep passes this module. It calls nothing."""
    assert PROSE_ONLY_FIXTURE.count(ENTRY) == 3
    assert ENTRY not in _called_names(ast.parse(PROSE_ONLY_FIXTURE))


def test_the_audit_bus_write_path_calls_the_ingest_entry_point() -> None:
    """#13562's defect as a property: the engine now has a production caller."""
    tree = _parse(AUDIT_BUS_PATH)
    record = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "record"
    )

    assert "_analyse_for_threats" in _called_names(record)
    assert ENTRY in _called_names(_function(tree, "_analyse_for_threats"))


def test_every_bus_producer_reaches_that_write_path() -> None:
    """One call site covers the bus only if the producers really funnel through it."""
    tree = _parse(AUDIT_BUS_PATH)

    # Both halves of this assertion used to read `emit`, so the second was dead
    # (CodeRabbit). Chasing that turned up the larger problem: `audit.py`
    # defines `emit` TWICE and the pin was reading the shadowed one.
    shadowed_emit = _function(tree, "emit")
    effective_emit = _effective_function(tree, "emit")
    assert shadowed_emit is not effective_emit, (
        "audit.py no longer defines `emit` twice — simplify this test rather "
        "than leaving an override check that no longer describes the module"
    )

    # The first definition writes directly; the override delegates to
    # `emit_compliance`, which reaches `_emit_real` below. Both are asserted
    # because either one changing would break the bus for a different caller.
    assert "record" in _called_names(shadowed_emit)
    assert "emit_compliance" in _called_names(
        effective_emit
    ), "the `emit` callers actually get must still funnel into the bus"

    assert "record" in _called_names(_function(tree, "emit_knowledge"))
    for shim in ("emit_security", "emit_compliance"):
        assert "_emit_real" in _called_names(_function(tree, shim)), shim

    # `audit_record` is a producer too, and nothing asserted its path.
    assert "emit_security" in _called_names(_function(tree, "audit_record"))


def test_the_ingest_entry_point_constructs_the_engine() -> None:
    """The class had no constructor call anywhere; now exactly one path has it."""
    tree = _parse(INGEST_PATH)

    assert "ThreatDetectionEngine" in _called_names(_function(tree, "get_threat_detection_engine"))
    assert "analyze_event" in _called_names(_function(tree, ENTRY))


def _function(tree: ast.AST, name: str):
    """The FIRST definition of *name*. See `_effective_function` before using it."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined")


def _effective_function(tree: ast.AST, name: str):
    """The definition that WINS at import time: the last one in the module.

    `audit.py` defines `emit` twice -- once at module scope and again as an
    intentional override (`# noqa: F811`). A pin that reads the first one is
    asserting about a function no caller can reach: correct about the AST node
    it inspected, and about the wrong question.
    """
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if not found:
        raise AssertionError(f"{name} is not defined")
    return found[-1]
