#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator, TaskComplexity


def test_plan_workflow_steps():
    orchestrator = Orchestrator()

    # Test each complexity level
    complexities = [
        TaskComplexity.SIMPLE,
        TaskComplexity.RESEARCH,
        TaskComplexity.INSTALL,
        TaskComplexity.COMPLEX,
    ]

    for complexity in complexities:
        try:
            steps = orchestrator.plan_workflow_steps("test message", complexity)
            print(f"{complexity.value}: {len(steps)} steps")  # noqa: print
        except Exception as e:
            print(f"{complexity.value}: ERROR - {e}")  # noqa: print
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    test_plan_workflow_steps()
