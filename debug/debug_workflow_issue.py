#!/usr/bin/env python3
"""
Debug the specific issue where plan_workflow_steps works in isolation
but fails when called through the API workflow
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator, TaskComplexity

logger = logging.getLogger(__name__)


async def debug_workflow_planning_issue():
    logger.info("Debugging workflow planning issue...")

    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    logger.info("1. Direct test of plan_workflow_steps:")
    direct_steps = orchestrator.plan_workflow_steps(
        user_message, TaskComplexity.COMPLEX
    )
    logger.info("   Direct call returned %s steps", len(direct_steps))

    logger.info("2. Test through classify_request_complexity:")
    complexity = await orchestrator.classify_request_complexity(user_message)
    logger.info("   Classification returned: %s", complexity)

    logger.info("3. Test plan_workflow_steps with classified complexity:")
    classified_steps = orchestrator.plan_workflow_steps(user_message, complexity)
    logger.info("   With classified complexity: %s steps", len(classified_steps))

    logger.info("4. Test should_use_workflow_orchestration:")
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    logger.info("   Should orchestrate: %s", should_orchestrate)

    logger.info("5. Test create_workflow_response (the problematic method):")
    try:
        workflow_response = await orchestrator.create_workflow_response(user_message)
        steps = workflow_response.get("workflow_steps", [])
        logger.info("   create_workflow_response returned %s steps", len(steps))

        # Check if steps are the right type
        if steps:
            logger.info("   First step type: %s", type(steps[0]))
            if hasattr(steps[0], "id"):
                logger.info("   First step ID: %s", steps[0].id)
            else:
                logger.info("   First step content: %s", steps[0])
    except Exception as e:
        logger.error("   create_workflow_response failed: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(debug_workflow_planning_issue())
