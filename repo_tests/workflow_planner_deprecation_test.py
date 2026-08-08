# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``orchestration.WorkflowPlanner`` is deprecated in place — hold that (#13751).

#12373/#12579 deprecated ``orchestration/workflow_executor.py`` in place and
recorded the rationale in docstrings only. Nothing held the claim, so the
statement "no production callers" could go stale in either direction: someone
wires the module and the docstring still says it is dead, or the note is dropped
while it is still true. Its planner sibling was missed entirely by that pass,
which is how #13751 arose.

These tests pin both halves of the invariant for ``WorkflowPlanner``:

* it stays unwired (an accidental call site fails here, with instructions), and
* it stays **intact and documented** — the never-delete policy means the fix for
  a failure here is never to delete the module.

Deliberately *not* scanning for the bare name ``get_plan_summary``:
``agents/overseer/overseer_agent.py`` defines an unrelated method with the same
name (no arguments, returns ``str | None``) that *is* wired via
``api/overseer_handlers.py``. A name-only scan would flag it. Reachability is
pinned through the instance attribute and the import instead, which cannot
collide.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"

_MODULE = _BACKEND / "orchestration" / "workflow_planner.py"
_PACKAGE_INIT = _BACKEND / "orchestration" / "__init__.py"

# The instance attribute Orchestrator binds the planner to. Only the assignment
# may exist; any attribute access on it would be a live call path.
_INSTANCE_ATTR = "_step_planner"

# Method names unique to WorkflowPlanner (no homonyms anywhere in the tree), so
# scanning for them by name is unambiguous.
_UNIQUE_METHOD_NAMES = ("plan_workflow_steps_with_agents", "create_plan_summary_for_approval")

# Public API that must remain present — deleting it is not an allowed fix.
_REQUIRED_METHODS = (
    "plan_workflow_steps_with_agents",
    "get_plan_summary",
    "create_plan_summary_for_approval",
    "determine_step_capabilities",
    "estimate_step_duration",
)

_WIRING_INSTRUCTIONS = (
    "If this was wired deliberately, that is a design change, not a test fix: "
    "WorkflowPlanner duplicates orchestrator.create_workflow_plan and "
    "AgentRouter.get_agent_recommendations_scored, and #13751 exists to keep a "
    "second planning path from drifting against them. Update the deprecation "
    "notes in orchestration/workflow_planner.py and orchestration/__init__.py "
    "in the same change, and adjust this test to match."
)


def _production_sources() -> List[Path]:
    """Backend .py files excluding tests and the deprecated module itself."""
    skip_names = {_MODULE.name}
    out: List[Path] = []
    for path in _BACKEND.rglob("*.py"):
        name = path.name
        if name in skip_names or name.endswith("_test.py") or name.startswith("test_"):
            continue
        if "/tests/" in path.as_posix() or "/node_modules/" in path.as_posix():
            continue
        out.append(path)
    return out


def test_planner_instance_is_constructed_but_never_called():
    """`self._step_planner.<anything>` would be a live path — none may exist."""
    offenders = []
    for path in _production_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # Matches `<expr>._step_planner.<attr>` — an access *through* the
            # attribute, as opposed to `self._step_planner = ...`.
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == _INSTANCE_ATTR
            ):
                offenders.append(f"{path.relative_to(_REPO)}:{node.lineno} -> .{_INSTANCE_ATTR}.{node.attr}")

    assert not offenders, f"WorkflowPlanner is documented as unwired but is now called: {offenders}. {_WIRING_INSTRUCTIONS}"


def test_unique_planner_methods_have_no_production_call_sites():
    """The two uniquely-named methods must appear nowhere in production code."""
    offenders = []
    for path in _production_sources():
        text = path.read_text(encoding="utf-8")
        for method in _UNIQUE_METHOD_NAMES:
            if method in text:
                offenders.append(f"{path.relative_to(_REPO)} -> {method}")

    assert not offenders, f"Deprecated WorkflowPlanner methods referenced in production: {offenders}. {_WIRING_INSTRUCTIONS}"


def test_only_known_files_reference_the_planner():
    """Reachability stays auditable: every mention is accounted for, with a reason.

    Construction happens in exactly one place. The other two are not call
    paths — a compatibility re-export and a disambiguation note — and are
    named here so a genuinely new reference stands out.
    """
    allowed = {
        "autobot-backend/orchestrator.py": "constructs it as _step_planner; never calls it",
        "autobot-backend/orchestration/__init__.py": "re-export kept for compatibility, as #12579 did for the executor",
        "autobot-backend/orchestration/workflow_planning.py": "docstring note distinguishing StrategyPlanner from it",
    }
    found = sorted(
        path.relative_to(_REPO).as_posix()
        for path in _production_sources()
        if "WorkflowPlanner" in path.read_text(encoding="utf-8")
    )

    unexpected = [p for p in found if p not in allowed]
    assert not unexpected, f"New reference(s) to deprecated WorkflowPlanner: {unexpected}. {_WIRING_INSTRUCTIONS}"

    # Also guard the other direction: if a listed file stops mentioning it, the
    # reason recorded here is stale and should be re-checked.
    vanished = [p for p in allowed if p not in found]
    assert not vanished, f"Expected reference(s) to WorkflowPlanner disappeared from {vanished}; update this allow-list."


def test_module_and_package_record_the_deprecation():
    """The rationale must stay written down — this is what #12579 lacked."""
    module_doc = ast.get_docstring(ast.parse(_MODULE.read_text(encoding="utf-8"))) or ""
    assert "DEPRECATED" in module_doc, "workflow_planner.py lost its deprecation notice"
    assert "#13751" in module_doc, "workflow_planner.py deprecation notice lost its issue reference"
    # The supersession must name the canonical replacements, not just say "dead".
    assert "create_workflow_plan" in module_doc
    assert "get_agent_recommendations_scored" in module_doc

    package_doc = ast.get_docstring(ast.parse(_PACKAGE_INIT.read_text(encoding="utf-8"))) or ""
    assert "workflow_planner" in package_doc
    assert "DEPRECATED" in package_doc.split("workflow_planner", 1)[1][:400], (
        "orchestration/__init__.py no longer marks workflow_planner deprecated"
    )


def test_deprecated_code_is_retained_in_full():
    """Never-delete policy: deprecation must not become quiet removal."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    planner = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "WorkflowPlanner"),
        None,
    )
    assert planner is not None, "WorkflowPlanner class was removed — deprecation is in place, not a deletion"

    defined = {n.name for n in planner.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = [m for m in _REQUIRED_METHODS if m not in defined]
    assert not missing, f"Deprecated-in-place module lost methods {missing}; code is retained, never deleted (#13751)"
