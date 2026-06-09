# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC domain exceptions (GH#8215)."""


class BudgetExhausted(Exception):
    """Raised when an agent's budget_spent exceeds budget_limit."""

    def __init__(self, agent_id: str, spent: float, limit: float) -> None:
        self.agent_id = agent_id
        self.spent = spent
        self.limit = limit
        super().__init__(f"Agent {agent_id} budget exhausted: spent={spent:.6f} limit={limit:.6f}")


class ApiKeyNotFound(Exception):
    """Raised when an API key is not found or not owned by the requesting agent."""


class WipLimitExceeded(Exception):
    """Raised when moving a work item into a column would exceed its WIP limit."""

    def __init__(self, column_name: str, wip_limit: int, current_count: int) -> None:
        self.column_name = column_name
        self.wip_limit = wip_limit
        self.current_count = current_count
        super().__init__(
            f"Column '{column_name}' is at WIP limit ({wip_limit}); " f"currently has {current_count} item(s)."
        )


class ProviderRateLimited(Exception):
    """Raised by an adapter when the LLM provider rejects a request due to rate or quota limits.

    The heartbeat scheduler catches this and schedules an exponential-backoff retry
    rather than marking the run as a permanent failure.  The work item checkout is
    preserved so the agent resumes exactly where it left off when limits reset.

    Args:
        provider: Short name of the provider (e.g. ``"anthropic"``, ``"openai"``).
        retry_after_seconds: Hint from the provider (e.g. Retry-After header).
            Zero means unknown — the scheduler will use its own backoff table.
    """

    def __init__(self, provider: str = "", retry_after_seconds: int = 0) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        msg = f"Provider {provider!r} rate-limited"
        if retry_after_seconds:
            msg += f"; retry after {retry_after_seconds}s"
        super().__init__(msg)
