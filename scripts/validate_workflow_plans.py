#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Validate the Workflow Planner example plans against the real status gate (#20034, FR-1.3 of #19934).

FR-1.3 names ``tools/validate.py``; ``tools/`` here holds lint checkers and codemods, and a
script that loads backend models belongs beside the other repo CLIs in ``scripts/``.

The rules are not restated: each plan is parsed into ``CompanyWorkflowPlan`` and handed to
``evaluate_plan_gate`` (``plan_gate.py``), the function the service runs on every write. A plan
passes when it parses, the gate finds nothing missing, and the status it declares is the status
the gate earns. ``negative_control`` plants a missing handoff and must see the gate object, so
an all-green run means the rule is live; a plan with no handoff has none to plant, so it is not
applicable there. A file that cannot be read as a plan is a named failure, never a traceback.

Exit code:
  0 - every plan passes and the negative control fired
  1 - a plan fails, or the negative control did not fire
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "autobot-backend"
EXAMPLES_DIR = REPO_ROOT / "docs" / "examples" / "workflow-plans"
HANDOFF_RULE = "handoffs mismatch"

for _p in (str(REPO_ROOT), str(BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from llc.services.company_os.plan_gate import evaluate_plan_gate  # noqa: E402
from llc.services.company_os.plan_types import CompanyWorkflowPlan, WorkflowPlanStatus  # noqa: E402

_RANK = {status: i for i, status in enumerate(WorkflowPlanStatus)}


def plan_problems(plan: CompanyWorkflowPlan) -> List[str]:
    """Why the real gate does not earn exactly the status this plan declares; empty when it does.

    Only the declared status is judged: ``missing`` also lists what the *next* rung lacks, which a
    plan that earned its declared status is allowed to have. Gaps are reported only when the gate
    earns less than the plan declares.
    """
    report = evaluate_plan_gate(plan)
    if report.status is plan.status:
        return []
    problems = [f"declares {plan.status.value!r} but the gate earns {report.status.value!r}"]
    if _RANK[report.status] < _RANK[plan.status]:
        problems += [f"{m.gate}: {m.message}" for m in report.missing]
    return problems


def load_plan(path: Path) -> CompanyWorkflowPlan:
    return CompanyWorkflowPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))


def negative_control(plan: CompanyWorkflowPlan) -> Optional[bool]:
    """True when the gate flags the plan once its handoffs are removed; False if it does not object.

    None when the plan has no handoff: there is none to remove, so the control does not apply (a valid
    single-lane plan has no handoff by construction).
    """
    if not plan.handoffs:
        return None
    planted = plan.model_copy(update={"handoffs": []})
    return any(HANDOFF_RULE in p for p in plan_problems(planted))


def _read_failure(path: Path, exc: Exception) -> str:
    reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return f"{path.name}: cannot be read as a workflow plan ({type(exc).__name__}: {reason})"


def _plan_failures(path: Path) -> List[str]:
    """Why one file fails: it is unreadable or malformed, the gate disagrees, or the control did not fire."""
    try:
        plan = load_plan(path)
    except (OSError, ValueError) as exc:  # ValueError covers bad JSON, bad encoding and pydantic's ValidationError
        return [_read_failure(path, exc)]
    failures = [f"{path.name}: {p}" for p in plan_problems(plan)]
    if negative_control(plan) is False:
        failures.append(f"{path.name}: negative control did not fire (planted missing handoff accepted)")
    return failures


def validate_dir(directory: Path) -> List[str]:
    """Every failure across the example plans in ``directory``; empty when all pass."""
    paths = sorted(directory.glob("*.json"))
    if not paths:
        return [f"no example plans in {directory}"]
    return [line for path in paths for line in _plan_failures(path)]


def main(argv: List[str]) -> int:
    directory = Path(argv[1]) if len(argv) > 1 else EXAMPLES_DIR
    failures = validate_dir(directory)
    for line in failures:
        print(f"FAIL {line}")
    if not failures:
        print(f"OK all example plans in {directory.name} pass the gate")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
