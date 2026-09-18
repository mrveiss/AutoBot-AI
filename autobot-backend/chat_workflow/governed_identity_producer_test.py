# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An executor identity reaches a run only from the trusted overlay, never from a context claim (#16950).

``build_governed_identity`` trusts the ``agent_id`` in the dict it is handed. No
peer's context reaches it today, but nothing structural stopped a future path from
forwarding one, and an executor id resolves to no boundary at all. The rule now:

- a claim may name a bounded profile, which only restricts its own run (GH#11186's
  self-restriction, kept);
- only ``session_role.apply_role`` may pin an executor, and it marks the pin;
- an unpinned executor claim gets the default boundary, as an unknown id does.
"""

import ast
import os
from pathlib import Path

from chat_workflow.models import build_governed_identity
from chat_workflow.session_role import PINNED_ROLE_CONTEXT_KEY, apply_role
from orchestration.agent_registry import resolve_forbidden_tools

_EXECUTOR = "system_agent"


def _governed_as(context):
    agent_context, _, _ = build_governed_identity(context, "s")
    return agent_context.agent_id if agent_context else None


class TestTheOverlayIsTheOnlyPinner:
    def test_a_pinned_role_is_marked_as_the_overlays(self):
        assert apply_role({}, "research_agent")[PINNED_ROLE_CONTEXT_KEY] == "research_agent"

    def test_a_client_supplied_pin_is_removed(self):
        forged = {"agent_id": _EXECUTOR, PINNED_ROLE_CONTEXT_KEY: _EXECUTOR}

        assert PINNED_ROLE_CONTEXT_KEY not in apply_role(forged, None)

    def test_a_clients_self_restriction_is_kept(self):
        """GH#11186: with no server role, a client may still bound its own run by naming a profile."""
        assert apply_role({"agent_id": "research_agent"}, None)["agent_id"] == "research_agent"


class TestAnExecutorClaim:
    def test_an_unpinned_claim_gets_the_default_boundary(self):
        governed = _governed_as({"agent_id": _EXECUTOR})

        assert governed != _EXECUTOR
        assert resolve_forbidden_tools(governed), "the default boundary, not none"

    def test_the_control_the_executor_itself_has_no_boundary(self):
        """Why the claim matters: honoured, it would lift every boundary."""
        assert resolve_forbidden_tools(_EXECUTOR) == frozenset()

    def test_a_pin_the_overlay_made_is_honoured(self):
        assert _governed_as(apply_role({}, _EXECUTOR)) == _EXECUTOR

    def test_a_forged_pin_does_not_survive_the_overlay(self):
        forged = {"agent_id": _EXECUTOR, PINNED_ROLE_CONTEXT_KEY: _EXECUTOR}

        assert _governed_as(apply_role(forged, None)) != _EXECUTOR

    def test_a_bounded_claim_is_honoured(self):
        assert _governed_as({"agent_id": "research_agent"}) == "research_agent"


# --- every producer of a governed identity is a reviewed one --------------------

_BACKEND = Path(__file__).resolve().parents[1]

#: Each caller passes either a context that went through ``_apply_session_role``
#: (manager, graph) or a dict it built server-side from a validated id (delegation).
#: A new caller must show the same before it is added here.
_KNOWN_CALLERS = {"chat_workflow/manager.py", "chat_workflow/graph.py", "chat_workflow/delegation.py"}


def _calls_builder(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == "build_governed_identity"
        for node in ast.walk(tree)
    )


def _is_test_file(name: str) -> bool:
    """The repository's test-file naming (pytest.ini ``python_files``), not a substring.

    ``"test" in name`` would also skip a production module such as ``attestation.py``,
    and the guard would then pass without having looked at it.
    """
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _production_modules():
    """Every non-test module under autobot-backend. ``os.walk`` does not follow symlinks (``backend -> .``)."""
    for root, dirs, files in os.walk(_BACKEND):
        dirs[:] = [d for d in dirs if d not in {"tests", "node_modules", "__pycache__"}]
        for name in files:
            if name.endswith(".py") and not _is_test_file(name):
                yield Path(root) / name


def test_a_production_module_whose_name_contains_test_is_still_scanned():
    assert not _is_test_file("attestation.py")
    assert _is_test_file("governed_identity_producer_test.py") and _is_test_file("test_governed_execution.py")


def test_every_caller_of_the_builder_is_a_reviewed_one():
    callers = {
        str(path.relative_to(_BACKEND))
        for path in _production_modules()
        if _calls_builder(path.read_text(encoding="utf-8", errors="replace"))
    }

    assert callers == _KNOWN_CALLERS, f"new or missing producers of a governed identity: {callers ^ _KNOWN_CALLERS}"


def test_the_scan_finds_a_call():
    """Negative control: the predicate must fire on the shape it guards."""
    assert _calls_builder("x = build_governed_identity(ctx, sid)")
    assert _calls_builder("x = models.build_governed_identity(ctx, sid)")
    assert not _calls_builder("x = build_other(ctx)")
