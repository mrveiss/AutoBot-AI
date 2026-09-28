# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workflow-event consumer may only name events its OWN producer emits (#17643).

`WorkflowLiveDashboard.vue` filtered on three names. Two -- `workflow_status_update`
and a bare `step_completed` -- are published by nobody under any spelling, so a
workflow that failed or was cancelled never left the active list without a manual
click. Only completion got through. The mismatch existed from 2026-04-01 and no
test could see it, because a filter that matches nothing is indistinguishable from
a filter that matches everything until you look at the producer.

WHY THIS GUARD IS PER TRANSPORT PAIR, NOT FRONTEND-VS-BACKEND. The issue's
original criterion -- "the frontend's event-name set is a subset of the backend's
published set" -- has no referent. There are two transports with disjoint
vocabularies:

    WorkflowLiveDashboard.vue  useEventBus subscribe `workflow:{id}`  event.event_type
                               <- api/workflow.py publish_event

    useWorkflowBuilder.ts      raw WS workflow_ws/{session_id}        data.type
                               <- services/workflow_automation/* send_json

A union guard would pass `workflow_paused` for the dashboard -- the wrong
transport, a name that can never arrive there. An `api/workflow.py`-only guard
would fail every legitimate `useWorkflowBuilder` case. So each consumer is
checked against its own producer and the two vocabularies are asserted disjoint,
which is the fact that made the union wrong in the first place.

EVERY DETECTOR HAS A CONTRAST PAIR. A detector run only against the live tree is
run against the one input it is guaranteed to agree with: it can be narrowed to
nothing later and nothing fails. Each one below gets a synthetic source it must
recognise and one it must reject. Each also gets a vacuity floor on what it
reached in the real tree, so "found no violations" cannot be returned by a
detector that read no files.
"""

from __future__ import annotations

import ast
import re

import pytest

from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-backend"
_FRONTEND = repo_root() / "autobot-frontend" / "src"

_BUS_PRODUCER = _BACKEND / "api" / "workflow.py"
_WS_PRODUCER_DIR = _BACKEND / "services" / "workflow_automation"
_BUS_CONSUMER = _FRONTEND / "components" / "workflow" / "WorkflowLiveDashboard.vue"
_WS_CONSUMER = _FRONTEND / "composables" / "useWorkflowBuilder.ts"

# The dashboard's two sets, split by what the event means for the active list.
_BUS_CONSUMER_SETS = ("TERMINAL_EVENT_TYPES", "PROGRESS_EVENT_TYPES")
_WS_CONSUMER_FUNC = "handleWebSocketMessage"

# Vacuity floors: what each detector must reach before an empty violation set
# means anything. Deliberately below today's counts -- they guard against a
# detector that stopped seeing the file, not against the tree growing.
_MIN_BUS_PRODUCED = 7
_MIN_WS_PRODUCED = 10
_MIN_BUS_CONSUMED = 5
_MIN_WS_CONSUMED = 4


# --------------------------------------------------------------------------
# Detectors: by property, never by a list of the names we expect to find.
# --------------------------------------------------------------------------


def bus_publish_names(source: str) -> set[str]:
    """Event names published via ``publish_event(channel, name, ...)``.

    Position matters and the call must resolve: a bare string literal that
    happens to sit in the file is not a publish, and this is the distinction
    that made three earlier readings of this area wrong.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "publish_event" or len(node.args) < 2:
            continue
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            names.add(second.value)
    return names


def ws_send_types(source: str) -> set[str]:
    """``"type"`` values of dict literals in the module -- the raw-WS vocabulary.

    The websocket messenger takes a plain dict, so the name is a dict VALUE
    rather than a call argument; keyed on the literal `type` key so a dict
    without one contributes nothing.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "type"):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                names.add(value.value)
    return names


def set_literal_members(source: str, set_name: str) -> set[str]:
    """String members of ``const <set_name> = new Set([...])``."""
    match = re.search(
        rf"const\s+{re.escape(set_name)}\s*=\s*new Set\(\[(.*?)\]\)",
        source,
        re.DOTALL,
    )
    if match is None:
        return set()
    return set(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))


def switch_case_labels(source: str, function_name: str) -> set[str]:
    """``case '<name>':`` labels inside one function, found by brace matching.

    Brace-matched rather than regexed to the end of file so a case in a
    neighbouring function cannot be attributed to this one.
    """
    start = source.find(f"function {function_name}")
    if start == -1:
        return set()
    open_at = source.find("{", start)
    if open_at == -1:
        return set()
    depth = 0
    end = len(source)
    for index in range(open_at, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    return set(re.findall(r"case\s+['\"]([^'\"]+)['\"]\s*:", source[open_at:end]))


# --------------------------------------------------------------------------
# Contrast fixtures. Synthetic sources only -- no path literals, which a
# repo guard would record as a tree it reads (#17571).
# --------------------------------------------------------------------------

_PUBLISHES = """
async def go(workflow_id):
    await publish_event(f"workflow:{workflow_id}", "workflow_failed", {})
"""

_MENTIONS_WITHOUT_PUBLISHING = """
def go():
    log_chat_event("workflow_failed", session_id, {})
    metadata["workflow_failed"] = True
    return "workflow_failed"
"""

_SENDS_TYPE = """
async def go(self, workflow):
    await self.messenger.send_message(workflow.session_id, {"type": "workflow_paused"})
"""

_DICT_WITHOUT_TYPE = """
def go():
    return {"status": "workflow_paused", "workflow_id": "x"}
"""

_TS_SET = "const SAMPLE_TYPES = new Set([\n  'alpha_event',\n  'beta_event',\n]);"
_TS_NO_SET = "const SAMPLE_TYPES: string[] = [];"

_TS_SWITCH = """
function handleSample(data) {
  switch (data.type) {
    case 'alpha_event':
      go();
      break;
    default:
      break;
  }
}
function handleOther(data) {
  switch (data.type) {
    case 'unrelated_event':
      break;
  }
}
"""


def _read(path):
    return path.read_text(encoding="utf-8")


def _bus_produced() -> set[str]:
    return bus_publish_names(_read(_BUS_PRODUCER))


def _ws_produced() -> set[str]:
    names: set[str] = set()
    for path in sorted(_WS_PRODUCER_DIR.glob("*.py")):
        names |= ws_send_types(_read(path))
    return names


def _bus_consumed() -> set[str]:
    source = _read(_BUS_CONSUMER)
    names: set[str] = set()
    for set_name in _BUS_CONSUMER_SETS:
        names |= set_literal_members(source, set_name)
    return names


def _ws_consumed() -> set[str]:
    return switch_case_labels(_read(_WS_CONSUMER), _WS_CONSUMER_FUNC)


# --------------------------------------------------------------------------
# Detector contrast pairs
# --------------------------------------------------------------------------


def test_publish_detector_recognises_and_rejects():
    assert bus_publish_names(_PUBLISHES) == {"workflow_failed"}
    assert bus_publish_names(_MENTIONS_WITHOUT_PUBLISHING) == set()


def test_ws_send_detector_recognises_and_rejects():
    assert ws_send_types(_SENDS_TYPE) == {"workflow_paused"}
    assert ws_send_types(_DICT_WITHOUT_TYPE) == set()


def test_set_member_detector_recognises_and_rejects():
    assert set_literal_members(_TS_SET, "SAMPLE_TYPES") == {"alpha_event", "beta_event"}
    assert set_literal_members(_TS_NO_SET, "SAMPLE_TYPES") == set()


def test_switch_detector_stays_inside_its_function():
    assert switch_case_labels(_TS_SWITCH, "handleSample") == {"alpha_event"}
    assert switch_case_labels(_TS_SWITCH, "missingFunction") == set()


# --------------------------------------------------------------------------
# Vacuity floors -- an empty violation set is only meaningful above these.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,names,floor",
    [
        ("bus producer", _bus_produced, _MIN_BUS_PRODUCED),
        ("ws producer", _ws_produced, _MIN_WS_PRODUCED),
        ("bus consumer", _bus_consumed, _MIN_BUS_CONSUMED),
        ("ws consumer", _ws_consumed, _MIN_WS_CONSUMED),
    ],
)
def test_detector_reached_its_files(label, names, floor):
    found = names()
    assert len(found) >= floor, (
        f"{label}: found {len(found)} names, floor {floor}. The detector stopped "
        f"seeing its source -- every subset assertion below is vacuous until this "
        f"passes. Found: {sorted(found)}"
    )


# --------------------------------------------------------------------------
# The contract itself, one pair at a time.
# --------------------------------------------------------------------------


def test_dashboard_names_are_all_published_on_its_channel():
    produced, consumed = _bus_produced(), _bus_consumed()
    unreachable = consumed - produced
    assert not unreachable, (
        f"WorkflowLiveDashboard.vue filters on {sorted(unreachable)}, which "
        f"api/workflow.py publishes under no spelling. A filter entry with no "
        f"producer is silent: the event never arrives and the handler never runs. "
        f"Published: {sorted(produced)}"
    )


def test_builder_cases_are_all_sent_on_its_socket():
    produced, consumed = _ws_produced(), _ws_consumed()
    unreachable = consumed - produced
    assert not unreachable, (
        f"useWorkflowBuilder.{_WS_CONSUMER_FUNC} switches on {sorted(unreachable)}, "
        f"which services/workflow_automation/* never sends. Sent: {sorted(produced)}"
    )


def test_the_shared_names_are_exactly_the_two_we_know_about():
    """The overlap between the transports is pinned, not assumed away.

    The vocabularies are NOT disjoint: `workflow_completed` and
    `workflow_cancelled` are published on the event bus by `api/workflow.py`
    AND sent on the raw session socket by `workflow_automation/executor.py`.
    Two publishers, two transports, one name each -- which is the strongest
    reason the union guard the original criterion asked for would mislead: for
    these two names a union cannot say which producer a consumer is reading.

    Pinned as an exact set rather than a maximum, so a THIRD shared name fails
    here and gets a decision (consolidate the transports, or rename) instead of
    quietly widening an overlap nobody chose. Tracked as duplication in #17676.
    """
    expected = {"workflow_cancelled", "workflow_completed"}
    shared = _bus_produced() & _ws_produced()
    assert shared == expected, (
        f"the set of event names published on BOTH transports changed: "
        f"{sorted(shared)}, was {sorted(expected)}. A new shared name means one "
        f"string now means two things on two sockets -- consolidate or rename, "
        f"and do not simply widen this pin."
    )
