"""
Example: Using vLLM Prefix Caching with Optimized Prompts

This example demonstrates how to use the optimized prompt system
to achieve 3-4x throughput improvements with vLLM prefix caching.

Requirements:
- vLLM installed: pip install vllm
- vLLM enabled in config/config.yaml: llm.vllm.enabled = true
"""

import asyncio
import logging
import time

# These imports come from the AutoBot project when running in context
from llm_interface import LLMInterface, LLMRequest  # noqa: F401
from prompt_optimizer import (  # noqa: F401
    get_agent_tier,
    get_base_prompt_for_agent,
    get_cache_hit_expectation,
    get_optimized_prompt,
    get_tier_statistics,
)

logger = logging.getLogger(__name__)

# Frontend engineering tasks for single agent workflow example
FRONTEND_TASKS = [
    "Review this React component for performance issues",
    "Optimize the Redux store structure",
    "Add TypeScript types to API client",
    "Implement responsive design for mobile",
    "Fix accessibility issues in navigation",
    "Add unit tests for utility functions",
    "Optimize bundle size with code splitting",
    "Implement error boundary components",
    "Add loading states to async operations",
    "Review CSS-in-JS performance",
]


async def _execute_task_with_cache_tracking(llm, request, task_index, first_task_time):
    """Execute a single LLM task and log cache performance.

    Helper for example_single_agent_workflow (#825).

    Returns:
        The first_task_time (set on first task, passed through after).
    """
    try:
        response = await llm.chat_completion(request)

        cached_tokens = response.metadata.get("cached_tokens", 0)
        total_tokens = response.usage.get("prompt_tokens", 0)
        cache_hit_rate = (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0

        logger.info(f"  Response: {response.content[:100]}...")
        logger.info(f"  Cache Hit Rate: {cache_hit_rate:.1f}%")
        logger.info(f"  Processing Time: {response.processing_time:.2f}s")

        if task_index == 1:
            first_task_time = response.processing_time
        else:
            speedup = first_task_time / response.processing_time
            logger.info(f"  Speedup vs First Task: {speedup:.2f}x")

        logger.info("")

    except Exception as e:
        logger.error(f"  Error: {e}\n")

    return first_task_time


async def example_single_agent_workflow():
    """Example 1: Single Agent Type (Maximum Cache Hit Rate).

    Scenario: 10 tasks with frontend-engineer agent type.
    Expected: 95% cache hit rate, 3.8x speedup on tasks 2-10.
    """
    logger.info("=== Example 1: Single Agent Workflow ===\n")

    llm = LLMInterface()

    agent_type = "frontend-engineer"
    tier = get_agent_tier(agent_type)
    cache_rate = get_cache_hit_expectation(agent_type)

    logger.info(f"Agent: {agent_type}")
    logger.info(f"Tier: {tier.name}")
    logger.info(f"Expected Cache Hit Rate: {cache_rate}\n")

    start_time = time.time()
    first_task_time = 0.0

    for i, task in enumerate(FRONTEND_TASKS, 1):
        prompt = get_optimized_prompt(
            base_prompt_key=get_base_prompt_for_agent(agent_type),
            session_id=f"session_{i}",
            user_name="Alice",
            user_role="Developer",
            available_tools=["file_read", "file_write", "code_review"],
            recent_context=(
                f"Previous task: " f"{FRONTEND_TASKS[i-2] if i > 1 else 'None'}"
            ),
        )

        request = LLMRequest(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": task},
            ],
            model_name="meta-llama/Llama-3.2-3B-Instruct",
            provider="vllm",
            max_tokens=512,
        )

        logger.info(f"Task {i}: {task[:50]}...")
        first_task_time = await _execute_task_with_cache_tracking(
            llm, request, i, first_task_time
        )

    total_time = time.time() - start_time
    logger.info(f"Total Time: {total_time:.2f}s")
    logger.info(f"Average Time per Task: " f"{total_time / len(FRONTEND_TASKS):.2f}s\n")


async def example_mixed_agent_workflow():
    """
    Example 2: Mixed Agent Types (Good Cache Hit Rate)

    Scenario: User executes tasks with different agent types (same tier)
    Expected: 75% cache hit rate, 3x speedup overall
    """
    logger.info("=== Example 2: Mixed Agent Workflow ===\n")

    # Initialize LLM interface
    llm = LLMInterface()

    # Mix of Tier 1 agents (all share same base prompt)
    agent_tasks = [
        ("frontend-engineer", "Add responsive design to dashboard"),
        ("backend-engineer", "Optimize database query performance"),
        ("frontend-engineer", "Implement state management with Vuex"),
        ("database-engineer", "Create migration for new user fields"),
        ("frontend-engineer", "Add WebSocket real-time updates"),
        ("backend-engineer", "Implement caching layer with Redis"),
        ("testing-engineer", "Write E2E tests for login flow"),
        ("frontend-engineer", "Fix CSS layout issues on mobile"),
        ("backend-engineer", "Add rate limiting to API endpoints"),
        ("documentation-engineer", "Update API documentation"),
    ]

    start_time = time.time()

    for i, (agent_type, task) in enumerate(agent_tasks, 1):
        prompt = get_optimized_prompt(
            base_prompt_key=get_base_prompt_for_agent(agent_type),
            session_id=f"mixed_session_{i}",
            user_name="Bob",
            available_tools=["file_read", "file_write", "database_query"],
        )

        request = LLMRequest(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": task},
            ],
            provider="vllm",
            max_tokens=512,
        )

        logger.info(f"Task {i} ({agent_type}): {task}")

        try:
            response = await llm.chat_completion(request)

            cached_tokens = response.metadata.get("cached_tokens", 0)
            total_tokens = response.usage.get("prompt_tokens", 0)
            cache_hit_rate = (
                (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0
            )

            logger.info(f"  Cache Hit Rate: {cache_hit_rate:.1f}%")
            logger.info(f"  Processing Time: {response.processing_time:.2f}s\n")

        except Exception as e:
            logger.error(f"  Error: {e}\n")

    total_time = time.time() - start_time
    logger.info(f"Total Time: {total_time:.2f}s\n")


def example_tier_statistics():
    """
    Example 3: Agent Tier Statistics

    Shows classification of all agents and expected cache performance
    """
    logger.info("=== Example 3: Agent Tier Statistics ===\n")

    stats = get_tier_statistics()

    for tier, data in stats.items():
        logger.info(f"{tier.name}:")
        logger.info(f"  Agent Count: {data['count']}")
        logger.info(f"  Cache Hit Rate: {data['cache_hit_rate']}")
        logger.info(f"  Base Prompt: {data['base_prompt']}")

        if data["agents"]:
            logger.info("  Agents:")
            for agent in data["agents"]:
                logger.info(f"    - {agent}")

        logger.info("")


def example_performance_comparison():
    """
    Example 4: Performance Comparison (With vs Without Caching)

    Shows the performance difference between:
    1. Traditional prompts (no caching optimization)
    2. Optimized prompts (prefix caching enabled)
    """
    logger.info("=== Example 4: Performance Comparison ===\n")

    # Example uses frontend-engineer agent type for comparison
    logger.info("Scenario: 10 sequential frontend engineering tasks\n")

    logger.info("WITHOUT Optimization:")
    logger.info("  - Each request processes full prompt (12,800 tokens)")
    logger.info("  - Processing time: ~6 seconds per request")
    logger.info("  - Total time: ~60 seconds for 10 tasks")
    logger.info("")

    logger.info("WITH Optimization (vLLM Prefix Caching):")
    logger.info("  - First request: Full prompt (12,800 tokens) - 6 seconds")
    logger.info(
        "  - Requests 2-10: Only dynamic suffix (200 tokens) - 1.7 seconds each"
    )
    logger.info("  - Total time: ~17 seconds for 10 tasks")
    logger.info("")

    logger.info("Performance Improvement:")
    logger.info("  - 3.5x faster overall")
    logger.info("  - 95% cache hit rate")
    logger.info("  - 43 seconds saved per 10-task workflow")
    logger.info("")


async def main():
    """Run all examples"""

    # Example 3: Show tier statistics (doesn't require vLLM)
    example_tier_statistics()

    # Example 4: Show theoretical performance comparison
    example_performance_comparison()

    # Examples 1 & 2 require vLLM to be installed and enabled
    try:
        logger.info("NOTE: Examples 1 & 2 require vLLM to be installed and enabled")
        logger.info("      Install with: pip install vllm")
        logger.info("      Enable in config/config.yaml: llm.vllm.enabled = true\n")

        # Uncomment to run live examples (requires vLLM setup):
        # await example_single_agent_workflow()
        # await example_mixed_agent_workflow()

    except Exception as e:
        logger.info(f"Could not run live examples: {e}")
        logger.info("Run examples 1 & 2 after installing vLLM\n")


if __name__ == "__main__":
    asyncio.run(main())
